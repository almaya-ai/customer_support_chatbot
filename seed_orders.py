"""Seed missing order records using a gcloud access token read from stdin."""

import json
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from store import ORDERS


def main(project, database, token):
    root = f"https://firestore.googleapis.com/v1/projects/{quote(project, safe='')}/databases/{quote(database, safe='')}"
    for owner, order in ORDERS.items():
        payload = {"fields": {field: {"stringValue": value} for field, value in order.items()}}
        request = Request(
            f"{root}/documents/orders?documentId={owner}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=25):
                print(f"Seeded {owner}")
        except HTTPError as error:
            if error.code != 409:
                raise
            print(f"Order for {owner} already exists")


if __name__ == "__main__":
    main(*sys.argv[1:3], sys.stdin.read().strip())
