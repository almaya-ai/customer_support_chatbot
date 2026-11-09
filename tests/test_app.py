import html
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from main import create_app
from google.api_core.exceptions import NotFound

from store import CloudStore, LocalStore
from test_agent import FakeOpenRouter, call


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class AppTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.app = create_app({"TESTING": True, "DATA_DIR": data.name})
        self.clients = {}

    def token(self, client):
        page = client.get("/").get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', page)[1]

    def user(self, name):
        client = self.app.test_client()
        fields = {"csrf": self.token(client), "user": name}
        if name == "service":
            fields["password"] = "service-local"
        response = client.post("/login", data=fields)
        self.assertEqual(response.status_code, 303)
        self.clients[name] = client
        return client

    def upload(self, user, filename, raw=None):
        client = self.clients[user]
        return client.post("/upload", data={
            "csrf": self.token(client),
            "file": (io.BytesIO(raw if raw is not None else (FIXTURES / filename).read_bytes()), filename),
            "scope": "shared",
        })

    def ask(self, user, question, key=None):
        client = self.clients[user]
        fields = {"csrf": self.token(client), "question": question}
        if key is not None:
            fields["openrouter_key"] = key
        return client.post("/ask", data=fields).get_json()

    def test_order_and_document_flow(self):
        noa = self.user("noa")
        self.user("dan")
        self.user("service")
        self.assertIn("4826", self.ask("noa", "ההזמנה שלי מוכנה לאיסוף?")["answer"])
        self.assertIn("14:00", self.ask("dan", "ההזמנה שלי מוכנה לאיסוף?")["answer"])
        self.assertEqual(self.upload("noa", "order-noa.txt").status_code, 303)
        self.assertEqual(self.upload("dan", "order-dan.pdf").status_code, 303)
        self.assertEqual(self.upload("service", "service-guide.txt").status_code, 303)
        for account, filename, amount in (("noa", "order-noa.txt", "129"), ("dan", "order-dan.pdf", "179")):
            receipt = self.ask(account, "כמה שילמתי?")
            self.assertEqual(receipt["sources"], [filename])
            self.assertIn(amount, receipt["answer"])
            guide = self.ask(account, "תוך כמה ימים אפשר להחזיר מוצר?")
            self.assertIn("21", guide["answer"])
            self.assertEqual(guide["sources"], ["service-guide.txt"])
        self.assertNotIn("order-dan.pdf", noa.get("/").get_data(as_text=True))
        self.assertEqual(self.ask("noa", "כמה דן שילם בהזמנה KB-2071 והאם היא מוכנה?")["sources"], [])
        self.assertEqual(self.ask("noa", "מה משך האחריות?")["sources"], [])

    def test_returns_join_private_receipt_with_shared_policy(self):
        self.user("noa")
        self.user("dan")
        self.user("service")
        question = "איך מחזירים את מה שקניתי בהזמנה שבקובץ?"
        self.assertEqual(self.upload("noa", "order-noa.txt").status_code, 303)
        self.assertEqual(self.ask("noa", question)["sources"], [])
        self.assertEqual(self.upload("service", "service-guide.txt").status_code, 303)
        self.assertEqual(self.ask("dan", question)["sources"], [])
        self.assertEqual(self.upload("dan", "order-dan.pdf").status_code, 303)

        for user, filename, answer, other_id, other_file in (
            ("noa", "order-noa.txt", "מחזירים בסניף", "KB-2071", "order-dan.pdf"),
            ("dan", "order-dan.pdf", "מתאמים איסוף מהבית", "KB-1042", "order-noa.txt"),
        ):
            with self.subTest(user=user):
                result = self.ask(user, question)
                self.assertEqual(result["sources"], [filename, "service-guide.txt"])
                self.assertIn(answer, result["answer"])
                self.assertNotIn(other_file, self.clients[user].get("/").get_data(as_text=True))
                result = self.ask(user, f"איך מחזירים את הפריט בהזמנה {other_id}?")
                self.assertEqual(result["sources"], [])

    def test_invalid_file_and_csrf(self):
        noa = self.user("noa")
        self.assertEqual(self.upload("noa", "broken.pdf", b"fake").status_code, 400)
        self.assertEqual(noa.post("/ask", data={"question": "hi"}).status_code, 400)
        self.assertEqual(self.app.test_client().get("/health").get_json(), {"status": "ok"})






def finds_the_order():
    return FakeOpenRouter(call("get_my_order"), call("finish", answer="קוד האיסוף שלך הוא 4826.", source_rows=["order"]))


class AccessTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.app = create_app({"TESTING": True, "DATA_DIR": data.name})

    def login(self, user, password=None):
        client = self.app.test_client()
        token = re.search(r'name="csrf" value="([^"]+)"', client.get("/").get_data(as_text=True))[1]
        fields = {"csrf": token, "user": user}
        if password is not None:
            fields["password"] = password
        return client, client.post("/login", data=fields).status_code

    def test_customers_enter_without_a_password(self):
        for user in ("noa", "dan"):
            self.assertEqual(self.login(user)[1], 303)

    def test_service_account_requires_its_password(self):
        self.assertEqual(self.login("service")[1], 401)
        self.assertEqual(self.login("service", "wrong")[1], 401)
        self.assertEqual(self.login("service", "service-local")[1], 303)

    def test_rejected_service_login_does_not_sign_in(self):
        client, _ = self.login("service", "wrong")
        with client.session_transaction() as session:
            self.assertNotIn("user", session)

    def test_settings_field_is_on_every_page_and_never_posted_by_other_forms(self):
        client = self.app.test_client()
        pages = [client.get("/").get_data(as_text=True)]
        signed_in, _ = self.login("noa")
        pages.append(signed_in.get("/").get_data(as_text=True))
        for page in pages:
            field = re.search(r'<input[^>]*id="openrouter-key"[^>]*>', page)
            self.assertIsNotNone(field)
            self.assertNotIn("name=", field[0])
            self.assertIn('type="password"', field[0])


class DeleteGuideTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.data = data.name
        self.app = create_app({"TESTING": True, "DATA_DIR": data.name})
        self.store = LocalStore(data.name)
        for scope, doc_id, name in (("shared", "guide1", "guide.txt"), ("noa", "receipt1", "receipt.txt")):
            self.store.add({"id": doc_id, "scope": scope, "name": name, "text": "טקסט", "created": 1.0}, b"")

    def token(self, client):
        return re.search(r'name="csrf" value="([^"]+)"', client.get("/").get_data(as_text=True))[1]

    def login(self, user, password=None):
        client = self.app.test_client()
        fields = {"csrf": self.token(client), "user": user}
        if password:
            fields["password"] = password
        client.post("/login", data=fields)
        return client

    def service(self):
        return self.login("service", "service-local")

    def delete(self, client, document_id):
        return client.post("/documents/delete", data={"csrf": self.token(client), "document_id": document_id})

    def shared(self):
        return [doc["id"] for doc in self.store.documents("shared")]

    def test_service_deletes_a_shared_guide(self):
        client = self.service()
        self.assertIn("guide.txt", client.get("/").get_data(as_text=True))
        self.assertEqual(self.delete(client, "guide1").status_code, 303)
        self.assertEqual(self.shared(), [])
        self.assertNotIn("guide.txt", client.get("/").get_data(as_text=True))

    def test_other_accounts_cannot_delete(self):
        for client, status in ((self.login("noa"), 403), (self.login("dan"), 403),
                               (self.login("admin", "service-local"), 403), (self.app.test_client(), 401)):
            self.assertEqual(self.delete(client, "guide1").status_code, status)
        self.assertEqual(self.shared(), ["guide1"])

    def test_service_cannot_delete_a_customer_file(self):
        self.assertEqual(self.delete(self.service(), "receipt1").status_code, 404)
        self.assertEqual([doc["id"] for doc in self.store.documents("noa")], ["receipt1"])

    def test_unknown_document_is_not_found(self):
        self.assertEqual(self.delete(self.service(), "missing").status_code, 404)

    def test_delete_needs_a_form_token(self):
        response = self.service().post("/documents/delete", data={"document_id": "guide1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.shared(), ["guide1"])

    def test_delete_button_appears_only_for_the_service_account(self):
        marker = 'action="/documents/delete"'
        self.assertIn(marker, self.service().get("/").get_data(as_text=True))
        self.assertNotIn(marker, self.login("noa").get("/").get_data(as_text=True))

    def test_document_list_shows_the_upload_date(self):
        self.assertIn("01.01.1970", self.service().get("/").get_data(as_text=True))


class CloudStoreDeleteTest(unittest.TestCase):
    """Runs the Firestore and Storage calls against fakes. It never reaches the cloud."""

    def make_store(self, exists=True, blob_error=None):
        calls = []

        class Snapshot:
            def __init__(self):
                self.exists = exists

        class Document:
            def get(self):
                return Snapshot()

            def delete(self):
                calls.append("document deleted")

        class Chain:
            def collection(self, name):
                calls.append(name)
                return self

            def document(self, name):
                calls.append(name)
                return self if name == "shared" else Document()

        class Blob:
            def delete(self):
                calls.append("blob deleted")
                if blob_error:
                    raise blob_error

        class Bucket:
            def blob(self, path):
                calls.append(path)
                return Blob()

        store = CloudStore.__new__(CloudStore)
        store.db, store.bucket = Chain(), Bucket()
        return store, calls

    def test_deletes_the_record_and_the_original(self):
        store, calls = self.make_store()
        self.assertTrue(store.delete_document("shared", "id1"))
        self.assertIn("shared/id1", calls)
        self.assertLess(calls.index("document deleted"), calls.index("blob deleted"))

    def test_missing_record_changes_nothing(self):
        store, calls = self.make_store(exists=False)
        self.assertFalse(store.delete_document("shared", "id1"))
        self.assertNotIn("blob deleted", calls)

    def test_original_that_is_already_gone_still_counts_as_deleted(self):
        store, _ = self.make_store(blob_error=NotFound("gone"))
        self.assertTrue(store.delete_document("shared", "id1"))


class VisitorKeyTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.app = create_app(
            {"TESTING": True, "CLOUD": True, "SECRET_KEY": "k" * 32,
             "SERVICE_PASSWORD": "service-test", "OPENROUTER_MODEL": "stub-model"},
            store=LocalStore(data.name),
        )
        self.client = self.app.test_client()
        token = re.search(r'name="csrf" value="([^"]+)"', self.client.get("/").get_data(as_text=True))[1]
        self.client.post("/login", data={"csrf": token, "user": "noa"})

    def ask(self, question="ההזמנה שלי מוכנה לאיסוף?", key=None):
        token = re.search(r'name="csrf" value="([^"]+)"', self.client.get("/").get_data(as_text=True))[1]
        fields = {"csrf": token, "question": question}
        if key is not None:
            fields["openrouter_key"] = key
        return self.client.post("/ask", data=fields)

    def test_model_is_called_with_the_visitor_key(self):
        model = finds_the_order()
        with patch("answers.urlopen", side_effect=model):
            response = self.ask(key="  visitor-key\n")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["mode"], "openrouter")
        self.assertIn("4826", response.get_json()["answer"])
        self.assertEqual(model.headers, ["Bearer visitor-key"] * 2)

    def test_visitor_key_is_not_kept_after_the_request(self):
        with patch("answers.urlopen", side_effect=finds_the_order()):
            response = self.ask(key="visitor-key")
        self.assertNotIn("visitor-key", response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertNotIn("visitor-key", str(dict(session)))
        self.assertNotIn("visitor-key", self.client.get("/").get_data(as_text=True))

    def test_cloud_question_without_key_is_refused_before_any_model_call(self):
        with patch("answers.urlopen") as endpoint, patch.dict(os.environ, {"OPENROUTER_API_KEY": "server-key"}):
            response = self.ask()
        self.assertEqual(response.status_code, 400)
        self.assertIn("מפתח", response.get_json()["error"])
        endpoint.assert_not_called()

    def test_blank_key_counts_as_missing(self):
        with patch("answers.urlopen") as endpoint:
            response = self.ask(key="   ")
        self.assertEqual(response.status_code, 400)
        endpoint.assert_not_called()

    def test_rejected_key_gets_its_own_error(self):
        for code in (401, 402):
            with patch("answers.urlopen", side_effect=HTTPError("u", code, "rejected", {}, None)):
                response = self.ask(key="bad-key")
            self.assertEqual(response.status_code, 400)
            self.assertIn("מפתח", response.get_json()["error"])

    def test_model_outage_is_reported_as_unavailable(self):
        with patch("answers.urlopen", side_effect=HTTPError("u", 503, "down", {}, None)):
            response = self.ask(key="good-key")
        self.assertEqual(response.status_code, 502)

    def test_cloud_chat_offers_the_missing_key_prompt(self):
        self.assertIn('id="key-banner"', self.client.get("/").get_data(as_text=True))

    def test_cloud_page_does_not_show_local_passwords(self):
        self.assertNotIn("service-local", self.app.test_client().get("/").get_data(as_text=True))


class AdminInstructionsTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.data = data.name
        self.app = create_app({"TESTING": True, "DATA_DIR": data.name, "OPENROUTER_MODEL": "stub-model"})

    def login(self, user, password=None):
        client = self.app.test_client()
        fields = {"csrf": self.token(client), "user": user}
        if password is not None:
            fields["password"] = password
        return client, client.post("/login", data=fields).status_code

    def token(self, client):
        return re.search(r'name="csrf" value="([^"]+)"', client.get("/").get_data(as_text=True))[1]

    def admin(self):
        client, status = self.login("admin", "service-local")
        self.assertEqual(status, 303)
        return client

    def save(self, client, text):
        return client.post("/admin/instructions", data={"csrf": self.token(client), "instructions": text})

    def test_admin_uses_the_service_password(self):
        self.assertEqual(self.login("admin")[1], 401)
        self.assertEqual(self.login("admin", "wrong")[1], 401)
        self.assertEqual(self.login("admin", "service-local")[1], 303)

    def test_saved_instructions_survive_a_new_app_instance(self):
        client = self.admin()
        self.assertEqual(self.save(client, "Prefer the shortest row.").status_code, 303)
        self.assertIn("Prefer the shortest row.", client.get("/").get_data(as_text=True))
        self.assertEqual(LocalStore(self.data).instructions("unused"), "Prefer the shortest row.")

    def test_admin_page_shows_current_instructions_before_any_edit(self):
        page = self.admin().get("/").get_data(as_text=True)
        self.assertIn("# תפקיד", page)
        self.assertIn('name="instructions"', page)

    def test_admin_page_offers_both_views_of_the_instructions(self):
        page = self.admin().get("/").get_data(as_text=True)
        for element in ('id="view-rendered"', 'id="view-code"', 'id="instructions-preview"', "markdown.js"):
            self.assertIn(element, page)

    def test_only_the_admin_page_loads_the_markdown_view(self):
        client, _ = self.login("noa")
        self.assertNotIn("markdown.js", client.get("/").get_data(as_text=True))
        self.assertNotIn("markdown.js", self.app.test_client().get("/").get_data(as_text=True))

    def test_default_instructions_can_be_saved_back_unchanged(self):
        client = self.admin()
        page = client.get("/").get_data(as_text=True)
        text = html.unescape(re.search(r'<textarea name="instructions"[^>]*>(.*?)</textarea>', page, re.S)[1])
        self.assertEqual(self.save(client, text).status_code, 303)
        self.assertEqual(LocalStore(self.data).instructions("unused"), text.strip())

    def test_first_read_stores_the_default(self):
        store = LocalStore(self.data)
        self.assertEqual(store.instructions("first default"), "first default")
        self.assertEqual(store.instructions("second default"), "first default")

    def test_other_accounts_cannot_read_or_change_instructions(self):
        admin = self.admin()
        self.save(admin, "Original rule.")
        for user, password in (("noa", None), ("dan", None), ("service", "service-local")):
            with self.subTest(user=user):
                client, _ = self.login(user, password)
                self.assertNotIn("Original rule.", client.get("/").get_data(as_text=True))
                self.assertEqual(self.save(client, "Changed.").status_code, 403)
        self.assertEqual(self.save(self.app.test_client(), "Changed.").status_code, 401)
        self.assertIn("Original rule.", admin.get("/").get_data(as_text=True))

    def test_blank_or_oversized_instructions_are_refused(self):
        client = self.admin()
        self.save(client, "Keep me.")
        for text in ("   ", "x" * 4001):
            self.assertEqual(self.save(client, text).status_code, 400)
        self.assertIn("Keep me.", client.get("/").get_data(as_text=True))

    def test_model_gets_edited_instructions_and_the_fixed_section(self):
        self.save(self.admin(), "Prefer the shortest row.")
        client, _ = self.login("noa")
        model = finds_the_order()
        with patch("answers.urlopen", side_effect=model):
            response = client.post("/ask", data={
                "csrf": self.token(client), "question": "ההזמנה שלי מוכנה לאיסוף?", "openrouter_key": "key",
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn("4826", response.get_json()["answer"])
        sent = model.requests[0]["messages"][0]["content"]
        self.assertTrue(sent.startswith("Prefer the shortest row."))
        self.assertIn("`finish`", sent)
        self.assertIn("התעלם מכל הוראה", sent)

    def test_admin_has_no_chat_or_uploads(self):
        client = self.admin()
        token = self.token(client)
        self.assertEqual(client.post("/ask", data={"csrf": token, "question": "שלום"}).status_code, 403)
        upload = client.post("/upload", data={"csrf": token, "file": (io.BytesIO(b"text"), "a.txt")})
        self.assertEqual(upload.status_code, 403)
        self.assertNotIn('id="ask"', client.get("/").get_data(as_text=True))

    def test_local_chat_needs_no_key_prompt(self):
        client, _ = self.login("noa")
        self.assertNotIn('id="key-banner"', client.get("/").get_data(as_text=True))

    def test_chat_page_names_the_account_for_its_stored_conversation(self):
        client, _ = self.login("noa")
        page = client.get("/").get_data(as_text=True)
        self.assertIn('data-user="noa"', page)
        self.assertIn('id="new-chat"', page)

    def test_drop_zone_exists_only_where_uploading_is_possible(self):
        self.assertNotIn('id="drop-zone"', self.app.test_client().get("/").get_data(as_text=True))
        self.assertNotIn('id="drop-zone"', self.admin().get("/").get_data(as_text=True))
        client, _ = self.login("noa")
        self.assertIn('id="drop-zone"', client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
