import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import create_app
from store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
FAKE_GCLOUD = """#!/usr/bin/env python3
import os, sys
with open(os.environ["GCLOUD_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
print("ENABLED")
"""


class CloudConfigTest(unittest.TestCase):
    def test_cloud_requires_a_session_key(self):
        with self.assertRaises(RuntimeError):
            create_app({"CLOUD": True, "SECRET_KEY": None, "SERVICE_PASSWORD": "service-test"})

    def test_cloud_rejects_a_short_session_key(self):
        with self.assertRaises(RuntimeError):
            create_app({"CLOUD": True, "SECRET_KEY": "short", "SERVICE_PASSWORD": "service-test"})

    def test_cloud_requires_a_service_password(self):
        with self.assertRaises(RuntimeError):
            create_app({"CLOUD": True, "SECRET_KEY": "k" * 32, "SERVICE_PASSWORD": ""})

    def test_service_password_comes_from_app_settings(self):
        settings = json.dumps({"session_key": "k" * 32, "service_password": "from-settings"})
        with tempfile.TemporaryDirectory() as data, patch.dict(
            os.environ, {"K_SERVICE": "test", "APP_SETTINGS": settings}
        ):
            client = create_app(store=LocalStore(data)).test_client()
            page = client.get("/", base_url="https://localhost").get_data(as_text=True)
            token = re.search(r'name="csrf" value="([^"]+)"', page)[1]
            response = client.post(
                "/login", base_url="https://localhost",
                data={"csrf": token, "user": "service", "password": "from-settings"},
            )
        self.assertEqual(response.status_code, 303)


class DeployScriptTest(unittest.TestCase):
    """Runs a copy of deploy.sh against a fake gcloud. It never reaches the cloud."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "bin").mkdir()
        fake = self.root / "bin" / "gcloud"
        fake.write_text(FAKE_GCLOUD)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        (self.root / "deploy.sh").write_text((ROOT / "deploy.sh").read_text())
        (self.root / "seed_orders.py").write_text("")
        self.log = self.root / "gcloud.log"
        env = {key: value for key, value in os.environ.items()
               if key not in {"PROJECT", "REGION", "OPENROUTER_SECRET", "SETTINGS_SECRET"}}
        env.update(PATH=f'{self.root / "bin"}:{os.environ["PATH"]}', GCLOUD_LOG=str(self.log),
                   PROJECT="test-project", OPENROUTER_MODEL="stub/model")
        self.run_result = subprocess.run(
            ["bash", str(self.root / "deploy.sh")], env=env, capture_output=True, text=True, timeout=60,
        )
        self.calls = self.log.read_text().splitlines()

    def deploy_call(self):
        return next(call for call in self.calls if " run deploy " in f" {call} ")

    def test_script_finishes(self):
        self.assertEqual(self.run_result.returncode, 0, self.run_result.stderr)

    def test_service_is_public(self):
        flags = self.deploy_call().split()
        self.assertIn("--allow-unauthenticated", flags)
        self.assertNotIn("--no-allow-unauthenticated", flags)

    def test_only_the_settings_secret_is_mounted(self):
        flags = self.deploy_call().split()
        self.assertEqual(flags[flags.index("--set-secrets") + 1], "APP_SETTINGS=support-app-settings:latest")

    def test_no_openrouter_secret_is_touched(self):
        self.assertEqual([call for call in self.calls if "openrouter" in call.split(" run deploy ")[0].lower()], [])


if __name__ == "__main__":
    unittest.main()
