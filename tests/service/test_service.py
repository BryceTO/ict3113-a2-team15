"""Service behaviour tests for POST /tickets (single + cascade), GET /search, GET /stats, GET /health.

No real Ollama and no extra packages: a fake Ollama HTTP server runs in a thread, and requests are
sent straight to the FastAPI app (ASGI) so the logging middleware is exercised too.

Run inside the service image (from the repo root, PowerShell):
    docker compose run --rm --no-deps -v "${PWD}/tests:/app/tests" triage python -m unittest discover -s tests/service -v
"""
import asyncio
import importlib
import json
import logging
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "service"))
if os.path.isdir(SERVICE_DIR):
    sys.path.insert(0, SERVICE_DIR)        # running from the repo
sys.path.insert(0, os.getcwd())             # running inside the image (/app/main.py)


# ---------------------------------------------------------------- fake Ollama
class FakeOllama:
    def __init__(self):
        self.answers = {}      # model -> str, or callable(prompt) -> str
        self.fail = set()      # models whose /api/generate returns HTTP 500
        self.calls = []        # every /api/generate payload, in order
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/ps":
                    loaded = sorted({c["model"] for c in fake.calls})
                    return self._send(200, {"models": [{"name": m} for m in loaded]})
                self._send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/show":
                    return self._send(200, {"capabilities": ["completion"]})
                if self.path == "/api/generate":
                    fake.calls.append(body)
                    m = body["model"]
                    if m in fake.fail:
                        return self._send(500, {"error": "boom"})
                    a = fake.answers[m]
                    a = a(body["prompt"]) if callable(a) else a
                    return self._send(200, {"response": a, "load_duration": 1000,
                                            "prompt_eval_count": 50, "eval_count": 3})
                self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


FAKE = FakeOllama()
TMP = tempfile.mkdtemp()
_n = [0]


def load_service(**env):
    """Import a fresh copy of main.py with the given configuration."""
    for k in ("MODE", "MODEL", "SMALL_MODEL", "LARGE_MODEL", "RULE", "RULE_SETTING"):
        os.environ.pop(k, None)
    _n[0] += 1
    os.environ.update(env)
    os.environ.update(OLLAMA_URL=FAKE.url, RUN_ID=f"test{_n[0]}",
                      DB_PATH=os.path.join(TMP, f"t{_n[0]}.db"),
                      LOG_PATH=os.path.join(TMP, f"t{_n[0]}.log"))
    log = logging.getLogger("requests")
    for h in list(log.handlers):   # close the previous run's log file
        h.close()
        log.removeHandler(h)
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def call(app, method, path, body=None, query=""):
    """Minimal ASGI client: returns (status, json_body, headers)."""
    raw = json.dumps(body).encode() if body is not None else b""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
             "query_string": query.encode(), "client": ("test", 1), "server": ("test", 80),
             "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                         (b"content-length", str(len(raw)).encode())]}
    out = []

    async def run():
        sent = False
        forever = asyncio.Event()

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": raw, "more_body": False}
            await forever.wait()

        async def send(msg):
            out.append(msg)

        await app(scope, receive, send)

    asyncio.run(run())
    start = next(m for m in out if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in out if m["type"] == "http.response.body")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return start["status"], (json.loads(data) if data else None), headers


def log_lines(svc):
    with open(svc.LOG_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def last_ticket_log(svc):
    return [l for l in log_lines(svc) if l["endpoint"] == "POST /tickets"][-1]


def post(svc, text, row=None):
    body = {"narrative": text}
    if row is not None:
        body["row_id"] = row
    return call(svc.app, "POST", "/tickets", body)


CASCADE = dict(MODE="cascade", SMALL_MODEL="small:1b", LARGE_MODEL="large:4b")


class Base(unittest.TestCase):
    def setUp(self):
        FAKE.calls.clear()
        FAKE.fail.clear()
        FAKE.answers.clear()
        FAKE.answers.update({"small:1b": "Credit card", "large:4b": "Mortgage", "single:4b": "Debt collection"})


# ------------------------------------------------------------ single mode (A1 behaviour)
class SingleMode(Base):
    def test_response_shape_storage_and_log(self):
        svc = load_service(MODE="single", MODEL="single:4b")
        status, body, headers = post(svc, "Collector keeps calling", row=15001)
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"id", "category"})          # A1 response contract
        self.assertEqual(body["category"], "Debt collection")
        self.assertEqual(headers["x-request-id"], body["id"])
        log = last_ticket_log(svc)
        self.assertEqual((log["status"], log["row_id"], log["final_model"], log["escalated"]),
                         (200, 15001, "single:4b", False))
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {"Debt collection": 1})

    def test_empty_narrative_is_422_and_logged(self):
        svc = load_service(MODE="single", MODEL="single:4b")
        self.assertEqual(post(svc, "   ")[0], 422)
        self.assertEqual(last_ticket_log(svc)["status"], 422)
        self.assertEqual(FAKE.calls, [])

    def test_backend_error_is_502_logged_and_not_stored(self):
        svc = load_service(MODE="single", MODEL="single:4b")
        FAKE.fail.add("single:4b")
        self.assertEqual(post(svc, "x")[0], 502)
        log = last_ticket_log(svc)
        self.assertEqual((log["status"], log["error_stage"]), (502, "model"))
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {})

    def test_no_result_caching(self):
        svc = load_service(MODE="single", MODEL="single:4b")
        post(svc, "same ticket")
        post(svc, "same ticket")
        self.assertEqual(len(FAKE.calls), 2)


# ------------------------------------------------------------ cascade
class CascadeCategoryRule(Base):
    def test_accept_small_answer(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Credit card;Mortgage")
        status, body, _ = post(svc, "card fee", row=15002)
        self.assertEqual((status, body["category"]), (200, "Credit card"))
        self.assertEqual(set(body), {"id", "category"})          # caller can't tell which model
        log = last_ticket_log(svc)
        self.assertEqual((log["routing"], log["escalated"], log["escalation_reason"], log["final_model"]),
                         ("decided", False, "category_accepted", "small:1b"))
        self.assertNotIn("large_ms", log)
        self.assertEqual([c["model"] for c in FAKE.calls], ["small:1b"])

    def test_escalate_large_answer_is_final_and_stored(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Mortgage")
        status, body, _ = post(svc, "card fee")
        self.assertEqual((status, body["category"]), (200, "Mortgage"))
        log = last_ticket_log(svc)
        self.assertEqual((log["escalated"], log["escalation_reason"], log["small_category"],
                          log["large_category"], log["final_model"], log["category"]),
                         (True, "category_not_accepted", "Credit card", "Mortgage", "large:4b", "Mortgage"))
        for k in ("small_ms", "large_ms", "ollama_ms"):
            self.assertIn(k, log)
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {"Mortgage": 1})   # one stored result
        self.assertEqual([c["model"] for c in FAKE.calls], ["small:1b", "large:4b"])

    def test_unclassified_small_answer_always_escalates(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Credit card")
        FAKE.answers["small:1b"] = "no idea"
        post(svc, "x")
        log = last_ticket_log(svc)
        self.assertEqual((log["small_category"], log["escalated"], log["escalation_reason"]),
                         ("Unclassified", True, "unclassified"))

    def test_small_backend_error_routing_not_reached(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Credit card")
        FAKE.fail.add("small:1b")
        self.assertEqual(post(svc, "x")[0], 502)
        log = last_ticket_log(svc)
        self.assertEqual((log["routing"], log["error_stage"]), ("not_reached", "small"))
        self.assertNotIn("escalated", log)
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {})

    def test_large_backend_error_after_decision(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Mortgage")
        FAKE.fail.add("large:4b")
        self.assertEqual(post(svc, "x")[0], 502)
        log = last_ticket_log(svc)
        self.assertEqual((log["routing"], log["escalated"], log["error_stage"]), ("decided", True, "large"))
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {})

    def test_same_prompt_and_options_for_both_models(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Mortgage")
        post(svc, "identical text")
        small, large = FAKE.calls
        self.assertEqual(small["prompt"], large["prompt"])
        self.assertEqual(small["options"], large["options"])
        single = load_service(MODE="single", MODEL="single:4b")
        FAKE.calls.clear()
        post(single, "identical text")
        self.assertEqual(FAKE.calls[0]["prompt"], small["prompt"])   # classification prompt unchanged

    def test_invalid_config_refuses_to_start(self):
        for bad in (dict(MODE="cascade"),
                    dict(**CASCADE, RULE="category", RULE_SETTING="Not a category"),
                    dict(**CASCADE, RULE="nonsense"),
                    dict(MODE="weird")):
            with self.assertRaises(SystemExit):
                load_service(**bad)


class CascadeOtherRules(Base):
    def test_length_rule(self):
        svc = load_service(**CASCADE, RULE="length", RULE_SETTING="10")
        post(svc, "short")
        self.assertEqual(last_ticket_log(svc)["escalated"], False)
        post(svc, "this narrative is longer than ten characters")
        self.assertEqual(last_ticket_log(svc)["escalation_reason"], "too_long")

    def test_confidence_rule_extra_call_is_timed(self):
        svc = load_service(**CASCADE, RULE="confidence")
        FAKE.answers["small:1b"] = lambda p: ("HIGH" if "sure" in p else "LOW") if "Confidence:" in p else "Credit card"
        post(svc, "I am sure")
        log = last_ticket_log(svc)
        self.assertEqual((log["escalated"], log["confidence_answer"]), (False, "HIGH"))
        self.assertIn("confidence_ms", log)
        post(svc, "hmm")
        log = last_ticket_log(svc)
        self.assertEqual((log["escalated"], log["final_model"]), (True, "large:4b"))


# ------------------------------------------------------------ other endpoints
class OtherEndpoints(Base):
    def test_search_and_stats_regression(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Credit card")
        post(svc, "my credit card was charged twice")
        FAKE.answers["small:1b"] = "Debt collection"
        post(svc, "a debt collector called")
        status, body, _ = call(svc.app, "GET", "/search", query="q=collector")
        self.assertEqual((status, body["count"]), (200, 1))
        self.assertEqual(body["results"][0]["category"], "Mortgage")        # escalated answer stored
        self.assertEqual(call(svc.app, "GET", "/stats")[1], {"Credit card": 1, "Mortgage": 1})
        self.assertEqual(call(svc.app, "GET", "/search", query="q=")[0], 422)

    def test_health_reports_residency(self):
        svc = load_service(**CASCADE, RULE="category", RULE_SETTING="Credit card")
        body = call(svc.app, "GET", "/health")[1]
        self.assertEqual((body["mode"], body["all_configured_loaded"]), ("cascade", False))
        FAKE.answers["small:1b"] = "Mortgage"
        post(svc, "x")      # escalates -> both models called
        body = call(svc.app, "GET", "/health")[1]
        self.assertEqual(body["configured_models"], ["small:1b", "large:4b"])
        self.assertTrue(body["all_configured_loaded"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
