"""The same storage interface backs the local and Cloud Run services."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path


ORDERS = {
    "noa": {
        "id": "KB-1042",
        "text": "הקומקום מוכן לאיסוף בסניף הרימון. קוד האיסוף הוא 4826.",
    },
    "dan": {
        "id": "KB-2071",
        "text": "המנורה בדרך לסניף הזית וצפויה להיות מוכנה ב-10 בנובמבר 2026 ב-14:00. טרם הונפק קוד איסוף.",
    },
}


class LocalStore:
    def __init__(self, location):
        self.location = Path(location)
        self.location.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, scope TEXT, meta TEXT, data BLOB)")
            db.execute("CREATE TABLE IF NOT EXISTS orders (owner TEXT PRIMARY KEY, data TEXT)")
            db.executemany("INSERT OR IGNORE INTO orders VALUES (?, ?)", [
                (owner, json.dumps(order)) for owner, order in ORDERS.items()
            ])

    def connect(self):
        return sqlite3.connect(self.location / "support.sqlite3", timeout=10)

    def order(self, owner):
        with closing(self.connect()) as db:
            row = db.execute("SELECT data FROM orders WHERE owner=?", (owner,)).fetchone()
        return json.loads(row[0]) if row else None

    def documents(self, scope):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT meta FROM documents WHERE scope=? ORDER BY rowid DESC LIMIT 24", (scope,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def add(self, meta, data):
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO documents VALUES (?, ?, ?, ?)", (meta["id"], meta["scope"], json.dumps(meta), data))


class CloudStore:
    def __init__(self, project, database, bucket):
        from google.cloud import firestore, storage

        self.db = firestore.Client(project=project, database=database)
        self.bucket = storage.Client(project=project).bucket(bucket)

    def order(self, owner):
        return self.db.collection("orders").document(owner).get().to_dict()

    def documents(self, scope):
        collection = self.db.collection("scopes").document(scope).collection("documents")
        return [snap.to_dict() for snap in collection.order_by("created", direction="DESCENDING").limit(24).stream()]

    def add(self, meta, data):
        blob = self.bucket.blob(f'{meta["scope"]}/{meta["id"]}')
        blob.upload_from_string(data, content_type="application/octet-stream", if_generation_match=0, timeout=15)
        document = self.db.collection("scopes").document(meta["scope"]).collection("documents").document(meta["id"])
        # An ambiguous Firestore timeout can mean the write succeeded. Keep the
        # private object for reconciliation instead of deleting a valid upload.
        document.create(meta, timeout=12)
