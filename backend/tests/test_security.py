import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main, security
from app.database import Base, get_session
from app.models import Account, RegistrationRequest, Role

STRONG = "Vq4-Lm9-Zk2-Rt7-x"
ADMIN_PASSWORD = "legacy-admin-long-secret-1"


class PasswordPolicyTests(unittest.TestCase):
    def test_policy(self):
        self.assertIsNone(security.password_problem(STRONG, "anna"))
        for weak, user in (
            ("short1!", ""),                      # too short
            ("password1234", ""),                 # common
            ("Password123456", ""),               # common with digits
            ("welcome123", ""),                   # common (and short)
            ("anna-secret-2026", "anna"),         # contains the username
            ("123456789012345", ""),              # only digits
            ("aaaaaaaaaaaaaaaa", ""),             # hardly any different characters
        ):
            self.assertIsNotNone(security.password_problem(weak, user), weak)


class SecurityApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SESSION_SECRET": "test-security-secret-long-enough-123",
            "ADMIN_USERNAME": "legacy-admin",
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
        })
        self.env.start()
        main.ADMIN_THROTTLE.clear()
        self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)

        def override():
            with Session(self.engine) as session:
                yield session

        main.app.dependency_overrides[get_session] = override
        main.app.dependency_overrides[main.optional_session] = override
        self.client = TestClient(main.app)
        with Session(self.engine) as session:
            parent = Role(name="parent")
            session.add(parent)
            session.add(Account(username="parent-a", password_hash=main.PASSWORD_HASHER.hash(STRONG), roles=[parent]))
            session.commit()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.pop(get_session, None)
        main.app.dependency_overrides.pop(main.optional_session, None)
        self.engine.dispose()
        self.env.stop()

    def entry(self, username, password):
        return self.client.post("/api/auth/entry", json={"username": username, "password": password})

    # ---- brute force protection -------------------------------------------------------
    def test_admin_password_guessing_is_locked_out(self):
        for _ in range(main.PORTAL_LOGIN_MAX_FAILURES):
            self.assertEqual(self.entry("legacy-admin", "wrong-guess").status_code, 401)
        locked = self.entry("legacy-admin", ADMIN_PASSWORD)  # even the right password waits
        self.assertEqual(locked.status_code, 429)

    def test_one_address_cannot_try_many_user_names(self):
        limit = main.PORTAL_LOGIN_MAX_FAILURES * 4
        for number in range(limit):
            self.assertEqual(self.entry(f"user-{number}", "wrong-guess").status_code, 401)
        self.assertEqual(self.entry("parent-a", STRONG).status_code, 429)

    def test_legacy_admin_login_is_throttled_too(self):
        for _ in range(main.ADMIN_LOGIN_LIMIT):
            self.assertEqual(self.client.post("/api/auth/login", json={"username": "legacy-admin", "password": "nope"}).status_code, 401)
        self.assertEqual(
            self.client.post("/api/auth/login", json={"username": "legacy-admin", "password": ADMIN_PASSWORD}).status_code, 429
        )

    def test_short_admin_password_is_refused_on_the_live_server(self):
        with patch.dict(os.environ, {"RENDER": "true", "ADMIN_PASSWORD": "admin"}):
            self.assertEqual(self.entry("legacy-admin", "admin").status_code, 503)
            self.assertEqual(self.client.post("/api/auth/login", json={"username": "legacy-admin", "password": "admin"}).status_code, 503)

    # ---- change own password ----------------------------------------------------------
    def test_user_changes_own_password(self):
        first = self.entry("parent-a", STRONG).json()["access_token"]
        second = self.entry("parent-a", STRONG).json()["access_token"]
        headers = {"Authorization": "Bearer " + second}
        url = "/api/platform/auth/change-password"
        wrong = self.client.post(url, headers=headers, json={"current_password": "not-it-at-all", "new_password": "Brand-New-Pass-77"})
        self.assertEqual(wrong.status_code, 400)
        weak = self.client.post(url, headers=headers, json={"current_password": STRONG, "new_password": "password1234"})
        self.assertEqual(weak.status_code, 422)
        same = self.client.post(url, headers=headers, json={"current_password": STRONG, "new_password": STRONG})
        self.assertEqual(same.status_code, 422)
        ok = self.client.post(url, headers=headers, json={"current_password": STRONG, "new_password": "Brand-New-Pass-77"})
        self.assertEqual(ok.status_code, 200)
        # other sessions end, this one stays, the new password works and the old one does not
        self.assertEqual(self.client.get("/api/platform/auth/me", headers={"Authorization": "Bearer " + first}).status_code, 401)
        self.assertEqual(self.client.get("/api/platform/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.entry("parent-a", STRONG).status_code, 401)
        self.assertEqual(self.entry("parent-a", "Brand-New-Pass-77").status_code, 200)

    def test_password_change_guessing_is_throttled(self):
        headers = {"Authorization": "Bearer " + self.entry("parent-a", STRONG).json()["access_token"]}
        for _ in range(main.PORTAL_LOGIN_MAX_FAILURES):
            self.client.post("/api/platform/auth/change-password", headers=headers,
                             json={"current_password": "nope-nope-nope", "new_password": "Brand-New-Pass-77"})
        blocked = self.client.post("/api/platform/auth/change-password", headers=headers,
                                   json={"current_password": STRONG, "new_password": "Brand-New-Pass-77"})
        self.assertEqual(blocked.status_code, 429)

    def test_weak_passwords_are_refused_for_new_accounts(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        token = self.client.post("/api/auth/login", json={"username": "legacy-admin", "password": ADMIN_PASSWORD}).json()["access_token"]
        weak = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers={"Authorization": "Bearer " + token},
            json={"username": "tess", "password": "tess-password-1"},
        )
        self.assertEqual(weak.status_code, 422)

    # ---- registration form bot traps ----------------------------------------------------
    def request_body(self, **extra):
        body = {"guardian_name": "Mona Parent", "email": "mona@example.com", "phone": "123456789", "child_name": "Sam"}
        body.update(extra)
        return body

    def stored(self):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(RegistrationRequest))

    def test_bots_get_a_friendly_answer_but_nothing_is_stored(self):
        self.assertEqual(self.client.post("/api/platform/registration-requests", json=self.request_body(website="http://spam.example")).status_code, 202)
        self.assertEqual(self.client.post("/api/platform/registration-requests", json=self.request_body(form_age_ms=400)).status_code, 202)
        self.assertEqual(self.stored(), 0)
        real = self.client.post("/api/platform/registration-requests", json=self.request_body(form_age_ms=15000))
        self.assertEqual(real.status_code, 202)
        self.assertEqual(self.stored(), 1)

    def test_one_address_can_only_send_a_few_requests(self):
        for number in range(main.REGISTRATION_REQUESTS_PER_ADDRESS):
            response = self.client.post("/api/platform/registration-requests", json=self.request_body(email=f"p{number}@example.com", form_age_ms=9000))
            self.assertEqual(response.status_code, 202)
        blocked = self.client.post("/api/platform/registration-requests", json=self.request_body(email="more@example.com", form_age_ms=9000))
        self.assertEqual(blocked.status_code, 429)

    # ---- headers --------------------------------------------------------------------------
    def test_security_headers(self):
        headers = self.client.get("/healthz").headers
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["x-frame-options"], "DENY")
        self.assertEqual(headers["referrer-policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        secure = self.client.get("/healthz", headers={"x-forwarded-proto": "https"}).headers
        self.assertIn("max-age", secure["strict-transport-security"])


if __name__ == "__main__":
    unittest.main()
