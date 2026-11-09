import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from answers import MAX_AGENT_STEPS
from main import create_app


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MISSING = "המידע הזה לא זמין במקורות שלך."


def call(name, **arguments):
    return {"name": name, "arguments": arguments}


class FakeOpenRouter:
    """Answers with scripted steps in the OpenRouter response shape and records every request."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []
        self.headers = []

    def __call__(self, request, timeout=None):
        self.requests.append(json.loads(request.data))
        self.headers.append(request.get_header("Authorization"))
        step = self.steps.pop(0) if self.steps else call("list_documents")
        if isinstance(step, str):
            message = {"role": "assistant", "content": step}
        else:
            calls = step if isinstance(step, list) else [step]
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{len(self.requests)}_{index}", "type": "function", "function": {
                    "name": item["name"],
                    "arguments": item["raw"] if "raw" in item else json.dumps(item["arguments"]),
                }} for index, item in enumerate(calls)
            ]}
        return io.StringIO(json.dumps({"choices": [{"message": message, "finish_reason": "tool_calls"}]}))

    def tool_results(self):
        """Every tool result the model saw in its last request."""
        return [m["content"] for m in self.requests[-1]["messages"] if m["role"] == "tool"]

    def everything_sent(self):
        return json.dumps(self.requests, ensure_ascii=False)


def documents_in(text):
    return {doc["name"]: doc["document_id"] for doc in json.loads(text)["documents"]}


class AgentTest(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.app = create_app({"TESTING": True, "DATA_DIR": data.name, "OPENROUTER_MODEL": "stub-model"})
        self.noa = self.login("noa")
        self.dan = self.login("dan")
        self.service = self.login("service", "service-local")
        self.upload(self.noa, "order-noa.txt")
        self.upload(self.dan, "order-dan.pdf")
        self.upload(self.service, "service-guide.txt")

    def token(self, client):
        return re.search(r'name="csrf" value="([^"]+)"', client.get("/").get_data(as_text=True))[1]

    def login(self, user, password=None):
        client = self.app.test_client()
        fields = {"csrf": self.token(client), "user": user}
        if password:
            fields["password"] = password
        self.assertEqual(client.post("/login", data=fields).status_code, 303)
        return client

    def upload(self, client, name):
        response = client.post("/upload", data={
            "csrf": self.token(client), "file": (io.BytesIO((FIXTURES / name).read_bytes()), name),
        })
        self.assertEqual(response.status_code, 303)

    def ask(self, client, question, model, key="visitor-key"):
        with patch("answers.urlopen", side_effect=model):
            return client.post("/ask", data={
                "csrf": self.token(client), "question": question, "openrouter_key": key,
            })

    def row_id(self, document_text, words):
        """Find a row by content in what a read_document call would return."""
        return next(row["id"] for row in json.loads(document_text)["rows"] if words in row["text"])

    def read_ids(self, client, question, name):
        """Run the first two steps for real to learn the ids this session assigns."""
        model = FakeOpenRouter(call("list_documents"), call("finish", answer_rows=[]))
        self.ask(client, question, model)
        return documents_in(model.tool_results()[0])[name]

    def test_question_with_a_spelling_mistake_still_reaches_the_documents(self):
        question = "מה מידיניות ההחזרת שלכם"
        document = self.read_ids(self.noa, question, "service-guide.txt")
        probe = FakeOpenRouter(call("read_document", document_id=document), call("finish", answer_rows=[]))
        self.ask(self.noa, question, probe)
        row = self.row_id(probe.tool_results()[0], "21 יום")

        model = FakeOpenRouter(call("list_documents"), call("read_document", document_id=document),
                               call("finish", answer_rows=[row]))
        result = self.ask(self.noa, question, model).get_json()
        self.assertEqual(result["answer"], "אפשר לבקש החזרה בתוך 21 יום ממסירת ההזמנה.")
        self.assertEqual(result["sources"], ["service-guide.txt"])
        self.assertEqual(result["mode"], "openrouter")
        self.assertEqual(len(model.requests), 3)

    def test_model_receives_the_tools_and_the_visitor_key(self):
        model = FakeOpenRouter(call("finish", answer_rows=[]))
        self.ask(self.noa, "שלום", model)
        names = {tool["function"]["name"] for tool in model.requests[0]["tools"]}
        self.assertEqual(names, {"get_my_order", "list_documents", "read_document", "finish"})
        self.assertEqual(model.headers[0], "Bearer visitor-key")

    def test_order_comes_only_from_the_signed_in_customer(self):
        model = FakeOpenRouter(call("get_my_order"), call("finish", answer_rows=["order"]))
        result = self.ask(self.noa, "ההזמנה מוכנה?", model).get_json()
        self.assertIn("4826", result["answer"])
        self.assertEqual(result["sources"], ["מערכת החנות | KB-1042"])
        self.assertNotIn("KB-2071", model.everything_sent())

    def test_supporting_row_adds_a_source_without_being_displayed(self):
        question = "איך מחזירים את מה שקניתי בהזמנה שבקובץ?"
        listing = FakeOpenRouter(call("list_documents"), call("finish", answer_rows=[]))
        self.ask(self.noa, question, listing)
        ids = documents_in(listing.tool_results()[0])
        probe = FakeOpenRouter([call("read_document", document_id=ids["order-noa.txt"]),
                                call("read_document", document_id=ids["service-guide.txt"])],
                               call("finish", answer_rows=[]))
        self.ask(self.noa, question, probe)
        receipt, guide = probe.tool_results()
        category = self.row_id(receipt, "home-accessories")
        rule = self.row_id(guide, "מחזירים בסניף")

        model = FakeOpenRouter([call("read_document", document_id=ids["order-noa.txt"]),
                                call("read_document", document_id=ids["service-guide.txt"])],
                               call("finish", answer_rows=[rule], supporting_rows=[category]))
        result = self.ask(self.noa, question, model).get_json()
        self.assertIn("מחזירים בסניף", result["answer"])
        self.assertNotIn("home-accessories", result["answer"])
        self.assertEqual(result["sources"], ["order-noa.txt", "service-guide.txt"])

    def test_tools_expose_only_this_account_and_shared_documents(self):
        model = FakeOpenRouter(call("list_documents"), call("finish", answer_rows=[]))
        self.ask(self.noa, "מה יש לי?", model)
        self.assertEqual(set(documents_in(model.tool_results()[0])), {"order-noa.txt", "service-guide.txt"})
        self.assertNotIn("order-dan.pdf", model.everything_sent())

    def test_unknown_document_gets_an_error_result_and_no_content(self):
        model = FakeOpenRouter(call("read_document", document_id="d99"), call("finish", answer_rows=[]))
        result = self.ask(self.noa, "תקרא משהו", model)
        self.assertEqual(result.status_code, 200)
        self.assertIn("error", json.loads(model.tool_results()[0]))
        self.assertNotIn("179", model.everything_sent())

    def test_row_that_was_never_read_is_rejected(self):
        for row in ("order", "d1:0", "invented"):
            with self.subTest(row=row):
                model = FakeOpenRouter(call("finish", answer_rows=[row]))
                self.assertEqual(self.ask(self.noa, "מה יש לי?", model).status_code, 502)

    def test_too_many_answer_rows_are_rejected(self):
        document = self.read_ids(self.noa, "מה יש לי?", "service-guide.txt")
        probe = FakeOpenRouter(call("read_document", document_id=document), call("finish", answer_rows=[]))
        self.ask(self.noa, "מה יש לי?", probe)
        rows = [row["id"] for row in json.loads(probe.tool_results()[0])["rows"]][:3]
        model = FakeOpenRouter(call("read_document", document_id=document), call("finish", answer_rows=rows))
        self.assertEqual(self.ask(self.noa, "מה יש לי?", model).status_code, 502)

    def test_empty_finish_means_the_information_is_missing(self):
        result = self.ask(self.noa, "מה משך האחריות?", FakeOpenRouter(call("finish", answer_rows=[]))).get_json()
        self.assertEqual(result["answer"], MISSING)
        self.assertEqual(result["sources"], [])

    def test_loop_stops_and_forces_a_finish(self):
        model = FakeOpenRouter()  # keeps calling list_documents forever
        response = self.ask(self.noa, "מה יש לי?", model)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(model.requests), MAX_AGENT_STEPS)
        self.assertEqual(model.requests[-1]["tool_choice"]["function"]["name"], "finish")

    def test_plain_text_reply_is_rejected(self):
        self.assertEqual(self.ask(self.noa, "שלום", FakeOpenRouter("הנה תשובה חופשית")).status_code, 502)

    def test_malformed_tool_arguments_get_an_error_result(self):
        broken = {"name": "read_document", "raw": "{not json"}
        model = FakeOpenRouter(broken, call("finish", answer_rows=[]))
        self.assertEqual(self.ask(self.noa, "שלום", model).status_code, 200)
        self.assertIn("error", json.loads(model.tool_results()[0]))

    def test_unknown_tool_gets_an_error_result(self):
        model = FakeOpenRouter(call("delete_everything"), call("finish", answer_rows=[]))
        self.assertEqual(self.ask(self.noa, "שלום", model).status_code, 200)
        self.assertIn("error", json.loads(model.tool_results()[0]))

    def test_tool_results_are_linked_to_their_calls(self):
        model = FakeOpenRouter(call("list_documents"), call("finish", answer_rows=[]))
        self.ask(self.noa, "שלום", model)
        messages = model.requests[-1]["messages"]
        assistant = next(m for m in messages if m["role"] == "assistant")
        tool = next(m for m in messages if m["role"] == "tool")
        self.assertEqual(tool["tool_call_id"], assistant["tool_calls"][0]["id"])

    def test_other_customers_order_never_reaches_the_model(self):
        for client, question in ((self.noa, "איך מחזירים את הפריט בהזמנה KB-2071?"),
                                 (self.dan, "מה קוד האיסוף של נועה?")):
            model = FakeOpenRouter()
            result = self.ask(client, question, model).get_json()
            self.assertEqual(result["answer"], MISSING)
            self.assertEqual(model.requests, [])

    def test_answer_reports_what_the_agent_checked(self):
        model = FakeOpenRouter(call("get_my_order"), call("finish", answer_rows=[]))
        self.assertEqual(self.ask(self.noa, "שלום", model).get_json()["checked"], ["מערכת החנות | KB-1042"])

    def test_rejected_key_still_gets_its_own_error(self):
        def refuse(request, timeout=None):
            raise HTTPError("u", 401, "rejected", {}, None)
        self.assertEqual(self.ask(self.noa, "שלום", refuse).status_code, 400)


if __name__ == "__main__":
    unittest.main()
