"""Spend-path tests: auth, origin, tokens, and the research budget.

The other test file covers sanitising and prompt rules. Nothing covered the
guard that decides whether a paid call runs, so this file pins the behaviour
that actually costs money:

* a request without a session, token, or valid origin is refused,
* a refused request charges nothing (it used to consume the global counter),
* the 10-minute window and the daily ceiling are reported separately,
* a caller that has exhausted one limit does not burn the others.

Run from the repository root with:
    python -m unittest discover -s vercel-app/tests -v
"""

import base64
import hashlib
import hmac
import os
import sys
import time
import unittest

os.environ.setdefault("BRAND_DOMAIN", "vistasocial.com")
# Deterministic guards: 3 calls per 10 minutes, 10 per IP per day,
# 5 per browser per day, 20 per instance per day.
os.environ["DEMO_IP_REQUESTS_PER_10_MIN"] = "3"
os.environ["DEMO_IP_REQUESTS_PER_DAY"] = "10"
os.environ["DEMO_CLIENT_REQUESTS_PER_DAY"] = "5"
os.environ["DEMO_DAILY_REQUEST_CAP"] = "20"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import _security as sec  # noqa: E402
from fastapi import HTTPException  # noqa: E402

SECRET = "g" * 48
PASSWORD = "unit-test-password"
ORIGIN = "https://pr.prachiadmane.com"


class FakeRequest:
    """The two attributes guard() reads, with a dict-like get()."""

    def __init__(self, cookies=None, headers=None):
        self.cookies = cookies or {}
        self.headers = headers or {}


def make_token(lifetime=120):
    expires_at = int(time.time()) + lifetime
    digest = hmac.new(
        SECRET.encode("utf-8"), f"v1.{expires_at}".encode("utf-8"), hashlib.sha256
    ).digest()
    signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"v1.{expires_at}.{signature}"


def reset_counters():
    for window in (sec._ip_window, sec._ip_day, sec._global_day, sec._client_day):
        with window._lock:
            window._hits.clear()


def make_request(ip="203.0.113.10", token=None, client="browser-1", origin=ORIGIN):
    cookies = {"pr_auth": sec._expected_auth_value(), "pr_client": client}
    headers = {"origin": origin, "x-real-ip": ip}
    value = make_token() if token is None else token
    if value:
        headers["authorization"] = f"Bearer {value}"
    return FakeRequest(cookies=cookies, headers=headers)


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)
        os.environ["DEMO_SIGNING_SECRET"] = SECRET
        os.environ["SITE_PASSWORD"] = PASSWORD
        reset_counters()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)
        reset_counters()

    def assert_refused(self, request, status):
        with self.assertRaises(HTTPException) as caught:
            sec.guard(request)
        self.assertEqual(caught.exception.status_code, status)

    def quota(self, request):
        return sec.remaining_quota(request)


class TestGuardAuth(GuardTestCase):
    def test_rejects_without_session_cookie(self):
        request = make_request()
        request.cookies = {"pr_client": "browser-1"}
        self.assert_refused(request, 401)

    def test_rejects_wrong_cookie_value(self):
        request = make_request()
        request.cookies["pr_auth"] = "not-the-right-value"
        self.assert_refused(request, 401)

    def test_rejects_missing_token(self):
        self.assert_refused(make_request(token=""), 401)

    def test_rejects_expired_token(self):
        self.assert_refused(make_request(token=make_token(lifetime=-120)), 401)

    def test_rejects_token_from_another_secret(self):
        good = make_token()
        prefix, expires, _ = good.split(".")
        forged = f"{prefix}.{expires}." + "A" * 43
        self.assert_refused(make_request(token=forged), 401)

    def test_rejects_foreign_origin(self):
        self.assert_refused(make_request(origin="https://evil.example"), 403)

    def test_rejects_missing_origin(self):
        self.assert_refused(make_request(origin=""), 403)

    def test_rejects_oversized_body_header(self):
        request = make_request()
        request.headers["content-length"] = str(sec.MAX_BODY_BYTES + 1)
        self.assert_refused(request, 413)

    def test_fails_closed_without_signing_secret(self):
        os.environ["DEMO_SIGNING_SECRET"] = "short"
        self.assert_refused(make_request(), 503)

    def test_accepts_a_correct_request(self):
        sec.guard(make_request())  # must not raise


class TestGuardDoesNotChargeRefusedRequests(GuardTestCase):
    def test_foreign_origin_charges_nothing(self):
        ip = "203.0.113.20"
        request = make_request(ip=ip)
        before = self.quota(request)
        self.assert_refused(make_request(ip=ip, origin="https://evil.example"), 403)
        after = self.quota(request)
        self.assertEqual(before["remaining"], after["remaining"])
        self.assertEqual(before["globalDay"], after["globalDay"])

    def test_exhausted_client_limit_does_not_burn_the_global_budget(self):
        # Raise the IP window so the per-browser ceiling is the limit under test.
        os.environ["DEMO_IP_REQUESTS_PER_10_MIN"] = "50"
        ip = "203.0.113.21"
        request = make_request(ip=ip, client="browser-exhaust")
        for _ in range(5):  # DEMO_CLIENT_REQUESTS_PER_DAY
            sec.guard(request)
        self.assert_refused(request, 429)
        # Five paid calls, so the shared counter must read exactly five.
        with sec._global_day._lock:
            self.assertEqual(len(sec._global_day._hits["global"]), 5)


class TestBudgetReporting(GuardTestCase):
    def test_window_and_day_are_reported_separately(self):
        request = make_request(ip="203.0.113.30")
        fresh = self.quota(request)
        self.assertEqual(fresh["perSession"], 3)
        self.assertEqual(fresh["perClientDay"], 5)
        self.assertEqual(fresh["today"], 5)

        sec.guard(request)
        after_one = self.quota(request)
        # One call used: 2 left in the 10-minute window, 4 left today.
        self.assertEqual(after_one["perSession"], 2)
        self.assertEqual(after_one["today"], 4)
        self.assertEqual(after_one["remaining"], 2)

    def test_short_term_window_blocks_before_the_daily_ceiling(self):
        request = make_request(ip="203.0.113.31")
        for _ in range(3):  # DEMO_IP_REQUESTS_PER_10_MIN
            sec.guard(request)
        limited = self.quota(request)
        self.assertEqual(limited["perSession"], 0)
        self.assertGreater(limited["today"], 0)
        self.assert_refused(request, 429)

    def test_each_browser_has_its_own_client_budget(self):
        shared_ip = "203.0.113.40"
        first = make_request(ip=shared_ip, client="browser-a")
        for _ in range(3):
            sec.guard(first)
        # Same IP, different browser: the shared window is drained, not the
        # per-browser budget, so this reports the window rather than zero.
        second = make_request(ip=shared_ip, client="browser-b")
        self.assertEqual(self.quota(second)["perSession"], 0)
        self.assertEqual(self.quota(second)["perClientDay"], 5)


if __name__ == "__main__":
    unittest.main()
