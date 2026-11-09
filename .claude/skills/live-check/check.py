"""Check the deployed service with the active gcloud identity."""

import json
import os
import subprocess
from urllib.request import Request, urlopen


def gcloud(*args):
    return subprocess.check_output(["gcloud", *args], text=True).strip()


def main():
    project = os.environ["PROJECT"]
    region = os.getenv("REGION", "europe-west1")
    url = gcloud("run", "services", "describe", "customer-support-chatbot",
                 "--project", project, "--region", region, "--format=value(status.url)")
    token = gcloud("auth", "print-identity-token")
    request = Request(f"{url}/healthz", headers={"Authorization": f"Bearer {token}"})
    with urlopen(request, timeout=20) as response:
        if json.load(response) != {"status": "ok"} or response.headers.get("Cache-Control") != "no-store":
            raise SystemExit("Unexpected health response")
    print(f"Cloud Run health check passed: {url}")


if __name__ == "__main__":
    main()
