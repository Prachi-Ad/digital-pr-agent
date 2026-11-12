"""Shared budget store tests.

The paid-call counters can live in one store (Upstash/Vercel KV) instead of each
instance's memory. These tests run a fake Redis REST endpoint and assert the
behaviour that makes the cap real:

* a cold start does not reset the daily count,
* the ceiling is enforced on the shared number, not a per-instance one,
* a refused request does not charge the store,
* an unreachable store fails closed (no paid call runs uncapped),
* without configuration the guard falls back to memory and says so.

Run from the repository root with:
    python -m unittest discover -s vercel-app/tests -v
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("BRAND_DOMAIN", "vistasocial.com")

CAPS = {
    "DEMO_IP_REQUESTS_PER_10_MIN": "5",
    "DEMO_IP_REQUESTS_PER_DAY": "10",
    "DEMO_CLIENT_REQUESTS_PER_DAY": "5",
    "DEMO_DAILY_REQUEST_CAP": "20",
}

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _security as sec  # noqa: E402
from _store import StoreError as StoreFailure  # noqa: E402,F401
from fastapi import HTTPException  # noqa: E402
from test_guards import SECRET, PASSWORD, make_request, reset_counters  # noqa: E402


class FakeRedis:
    """Minimal Upstash REST surface: GET, INCR, EXPIRE, /pipeline."""

    def __init__(self):
        self.data: dict[str, int] = {}
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def do_POST(self):
                length = int(self.headers.get("content-length") or 0)
                payload = json.loads(self.rfile.read(length) or b"[]")
                with outer.lock:
                    if self.path.rstrip("/") == "/pipeline":
                        results = [outer.run(item) for item in payload]
                        body = json.dumps(results)
                    else:
                        body = json.dumps({"result": outer.run(payload)})
                raw = body.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def run(self, command):
        op = str(command[0]).upper()
        key = str(command[1]) if len(command) > 1 else ""
        if op == "GET":
            return {"result": self.data.get(key)}
        if op == "INCR":
            self.data[key] = int(self.data.get(key) or 0) + 1
            return {"result": self.data[key]}
        if op == "EXPIRE":
            return {"result": 1}
        return {"error": f"unsupported command {op}"}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class SharedStoreTestCase(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ.update(CAPS)
        os.environ["DEMO_SIGNING_SECRET"] = SECRET
        os.environ["SITE_PASSWORD"] = PASSWORD
        reset_counters()
        self.redis = FakeRedis()
        os.environ["UPSTASH_REDIS_REST_URL"] = self.redis.url
        os.environ["UPSTASH_REDIS_REST_TOKEN"] = "test-token"

    def tearDown(self):
        self.redis.close()
        os.environ.clear()
        os.environ.update(self._env)
        reset_counters()

    def assert_refused(self, request, status):
        with self.assertRaises(HTTPException) as caught:
            sec.guard(request)
        self.assertEqual(caught.exception.status_code, status)


class TestSharedCounter(SharedStoreTestCase):
    def test_cold_start_does_not_reset_the_daily_count(self):
        request = make_request(ip="198.51.100.10", client="browser-shared")
        sec.guard(request)
        self.assertEqual(sec.remaining_quota(request)["perClientDay"], 4)

        # Simulate a fresh instance: every in-memory counter is gone.
        reset_counters()
        self.assertEqual(sec.remaining_quota(request)["perClientDay"], 4)
        self.assertEqual(sec.remaining_quota(request)["budgetStore"], "shared")

    def test_daily_ceiling_is_enforced_on_the_shared_number(self):
        os.environ["DEMO_CLIENT_REQUESTS_PER_DAY"] = "2"
        request = make_request(ip="198.51.100.11", client="browser-two")
        sec.guard(request)
        reset_counters()  # new instance, same store
        sec.guard(request)
        reset_counters()
        self.assert_refused(request, 429)

    def test_global_ceiling_is_shared_across_instances(self):
        os.environ["DEMO_DAILY_REQUEST_CAP"] = "2"
        os.environ["DEMO_CLIENT_REQUESTS_PER_DAY"] = "50"
        first = make_request(ip="198.51.100.12", client="browser-a")
        second = make_request(ip="198.51.100.13", client="browser-b")
        sec.guard(first)
        reset_counters()
        sec.guard(second)
        reset_counters()
        self.assert_refused(make_request(ip="198.51.100.14", client="browser-c"), 429)

    def test_refused_request_does_not_charge_the_store(self):
        os.environ["DEMO_IP_REQUESTS_PER_10_MIN"] = "1"
        request = make_request(ip="198.51.100.15", client="browser-window")
        sec.guard(request)
        before = dict(self.redis.data)
        self.assert_refused(request, 429)
        self.assertEqual(self.redis.data, before)

    def test_remaining_quota_matches_the_store(self):
        request = make_request(ip="198.51.100.16", client="browser-quota")
        sec.guard(request)
        quota = sec.remaining_quota(request)
        self.assertEqual(quota["perClientDay"], 4)
        self.assertEqual(quota["today"], 4)
        self.assertEqual(quota["remaining"], 4)
        self.assertEqual(quota["budgetStore"], "shared")


class TestSharedStoreFailures(SharedStoreTestCase):
    def test_unreachable_store_fails_closed(self):
        # Nothing listens on port 9; the guard must refuse rather than run uncapped.
        os.environ["UPSTASH_REDIS_REST_URL"] = "http://127.0.0.1:9"
        self.assert_refused(make_request(ip="198.51.100.20"), 503)

    def test_health_degrades_instead_of_failing(self):
        os.environ["UPSTASH_REDIS_REST_URL"] = "http://127.0.0.1:9"
        quota = sec.remaining_quota(make_request(ip="198.51.100.21"))
        self.assertEqual(quota["budgetStore"], "degraded")
        self.assertIn("remaining", quota)


class TestMemoryFallback(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ.update(CAPS)
        os.environ["DEMO_SIGNING_SECRET"] = SECRET
        os.environ["SITE_PASSWORD"] = PASSWORD
        for name in (
            "UPSTASH_REDIS_REST_URL",
            "UPSTASH_REDIS_REST_TOKEN",
            "KV_REST_API_URL",
            "KV_REST_API_TOKEN",
        ):
            os.environ.pop(name, None)
        reset_counters()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        reset_counters()

    def test_no_store_means_memory_mode(self):
        request = make_request(ip="198.51.100.30")
        quota = sec.remaining_quota(request)
        self.assertEqual(quota["budgetStore"], "memory")
        sec.guard(request)
        self.assertEqual(sec.remaining_quota(request)["perClientDay"], 4)


if __name__ == "__main__":
    unittest.main()
