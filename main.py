"""Flask entry point for the customer support service."""

import hmac
import json
import os
import time
from datetime import timedelta
from urllib.error import HTTPError, URLError
from uuid import uuid4

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from answers import (
    DEFAULT_INSTRUCTIONS, FIXED_INSTRUCTIONS, MISSING, evidence, extract, mentions_other_customer, run_agent,
)
from store import CloudStore, LocalStore


USERS = {"noa": "נועה | לקוחה", "dan": "דן | לקוח", "service": "מיכל | נציגת שירות", "admin": "אדמין"}
PASSWORD_USERS = {"service", "admin"}
MAX_INSTRUCTIONS = 4000
MAX_UPLOAD = 2 * 1024 * 1024


def create_app(config=None, store=None):
    app = Flask(__name__)
    cloud = bool(os.getenv("K_SERVICE"))
    settings = json.loads(os.getenv("APP_SETTINGS", "{}"))
    app.config.update(
        CLOUD=cloud,
        SECRET_KEY=settings.get("session_key") or (None if cloud else os.urandom(32)),
        SERVICE_PASSWORD=settings.get("service_password") or ("" if cloud else "service-local"),
        OPENROUTER_MODEL=os.getenv("OPENROUTER_MODEL", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=cloud,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        MAX_CONTENT_LENGTH=MAX_UPLOAD + 16_384,
        DATA_DIR=os.getenv("LOCAL_DATA_DIR", "var"),
    )
    if config:
        app.config.update(config)
    if app.config["CLOUD"] and (len(app.config["SECRET_KEY"] or "") < 32 or not app.config["SERVICE_PASSWORD"]):
        raise RuntimeError("Configure a session key and a service password in APP_SETTINGS.")
    if store is None:
        store = (
            CloudStore(os.environ["PROJECT"], os.environ["FIRESTORE_DATABASE"], os.environ["BUCKET_NAME"])
            if app.config["CLOUD"] else LocalStore(app.config["DATA_DIR"])
        )

    @app.context_processor
    def show_revision():
        return {"revision": os.getenv("K_REVISION", "local")}

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.before_request
    def protect_posts():
        if request.method == "POST":
            expected = session.get("csrf", "")
            supplied = request.form.get("csrf", "")
            if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
                abort(400, "הטופס פג. רעננו את הדף ונסו שוב.")

    def csrf():
        if "csrf" not in session:
            session["csrf"] = uuid4().hex
        return session["csrf"]

    def signed_in():
        user = session.get("user")
        if user not in USERS:
            abort(401)
        return user

    def chat_user():
        user = signed_in()
        if user == "admin":
            abort(403, "לאדמין אין גישה לצ׳אט או להעלאת קבצים.")
        return user

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/")
    def home():
        user = session.get("user")
        docs = [(doc["name"], doc["scope"] == "shared") for scope in (user, "shared")
                for doc in store.documents(scope)] if user in USERS and user != "admin" else []
        instructions = store.instructions(DEFAULT_INSTRUCTIONS) if user == "admin" else None
        return render_template("page.html", users=USERS, user=user, csrf=csrf(), documents=docs,
                               local=not app.config["CLOUD"], uploaded=request.args.get("uploaded") == "1",
                               instructions=instructions, fixed_instructions=FIXED_INSTRUCTIONS,
                               max_instructions=MAX_INSTRUCTIONS, saved=request.args.get("saved") == "1")

    @app.post("/login")
    def login():
        user = request.form.get("user")
        supplied = request.form.get("password", "").encode()
        expected = app.config["SERVICE_PASSWORD"].encode()
        if user not in USERS or (user in PASSWORD_USERS and not hmac.compare_digest(supplied, expected)):
            return render_template("page.html", users=USERS, csrf=csrf(), local=not app.config["CLOUD"],
                                   error="שם המשתמש או הסיסמה שגויים."), 401
        session.clear()
        session["user"] = user
        session.permanent = True
        return redirect(url_for("home"), code=303)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"), code=303)

    @app.post("/admin/instructions")
    def save_instructions():
        if signed_in() != "admin":
            abort(403, "רק אדמין יכול לערוך את הוראות המערכת.")
        text = request.form.get("instructions", "").strip()
        if not 1 <= len(text) <= MAX_INSTRUCTIONS:
            abort(400, f"כתבו הוראות באורך של עד {MAX_INSTRUCTIONS} תווים.")
        store.set_instructions(text)
        return redirect(url_for("home", saved=1), code=303)

    @app.post("/upload")
    def upload():
        user = chat_user()
        file = request.files.get("file")
        name = file.filename if file else ""
        if not name or len(name) > 160 or "/" in name or "\\" in name or any(ord(char) < 32 for char in name):
            abort(400, "בחרו קובץ עם שם תקין.")
        data = file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            abort(413, "אפשר להעלות עד 2 MB.")
        try:
            content = extract(name, data)
        except ValueError as exc:
            abort(400, str(exc))
        store.add({
            "id": uuid4().hex, "scope": "shared" if user == "service" else user,
            "name": name, "text": content, "created": time.time(),
        }, data)
        return redirect(url_for("home", uploaded=1), code=303)

    @app.post("/ask")
    def ask():
        user = chat_user()
        question = request.form.get("question", "").strip()
        if not 1 <= len(question) <= 500:
            return jsonify(error="כתבו שאלה של עד 500 תווים."), 400
        key = request.form.get("openrouter_key", "").strip()
        if app.config["CLOUD"] and not key:
            return jsonify(error="כדי לשאול, הזינו מפתח OpenRouter בהגדרות שבראש הדף."), 400
        model = app.config["OPENROUTER_MODEL"]
        if mentions_other_customer(user, question, store):
            return jsonify(answer=MISSING, sources=[], checked=[], mode="search")
        if key and model:
            try:
                result = run_agent(user, question, store, key, model, store.instructions(DEFAULT_INSTRUCTIONS))
            except (URLError, TimeoutError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                if isinstance(exc, HTTPError) and exc.code in (401, 402):
                    app.logger.warning("OpenRouter rejected the visitor key: %s", exc.code)
                    return jsonify(error="מפתח OpenRouter נדחה או שאין בו יתרה. בדקו אותו בהגדרות."), 400
                app.logger.warning("The agent could not finish: %s", type(exc).__name__)
                return jsonify(error="החיבור למודל לא זמין כרגע. נסו שוב."), 502
            return jsonify(answer="\n".join(row["text"] for row in result["rows"]) or MISSING,
                           sources=result["sources"], checked=result["checked"], mode="openrouter")
        choices = evidence(user, question, store)
        sources = {}
        for row in choices[:2]:
            if "receipt_source" in row:
                sources[row["receipt_source"]] = None
            sources[row["source"]] = None
        return jsonify(answer="\n".join(row["text"] for row in choices[:2]) or MISSING, sources=list(sources),
                       checked=[], mode="local" if choices else "search")

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(413)
    def show_error(error):
        return render_template("error.html", error=error), error.code

    return app
