"""Check that the deployed public service answers on its health route."""

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
    with urlopen(Request(f"{url}/health"), timeout=20) as response:
        if json.load(response) != {"status": "ok"} or response.headers.get("Cache-Control") != "no-store":
            raise SystemExit("Unexpected health response")
    print(f"Cloud Run health check passed: {url}")


if __name__ == "__main__":
    main()
