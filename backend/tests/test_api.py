import copy
import hashlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.models import (
    Account,
    Child,
    GuardianInvitation,
    Permission,
    Role,
)


class FakeStore:
    def __init__(self):
        self.data = {"settings": {}, "gallery": [], "news": []}
        self.files = {}
        self.sha = "test-sha"

    async def get_content(self):
        return copy.deepcopy(self.data), self.sha

    async def put_content(self, data, sha, message):
        self.data = copy.deepcopy(data)
        self.sha = f"{self.sha}-next"

    async def put_file(self, name, contents, message):
        self.files[name] = contents

    async def get_file(self, name):
        class FakeResponse:
            content = self.files[name]

        return FakeResponse()

    async def delete_file(self, name):
        self.files.pop(name, None)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "Qx789cbe040784-9",
                "SESSION_SECRET": "test-session-secret-long-enough",
            },
        )
        self.env.start()
        self.original_store = main.store
        self.fake_store = FakeStore()
        main.store = self.fake_store
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Qx789cbe040784-9"},
        )
        self.assertEqual(response.status_code, 200)
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def tearDown(self):
        self.client.close()
        main.store = self.original_store
        self.env.stop()

    def test_admin_routes_require_login(self):
        response = self.client.get("/api/admin/content")
        self.assertEqual(response.status_code, 401)

    def test_default_admin_username_can_access_admin_routes(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_PASSWORD": "Qx789cbe040784-9",
                "SESSION_SECRET": "test-session-secret-long-enough",
            },
            clear=True,
        ):
            login = self.client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "Qx789cbe040784-9"},
            )
            self.assertEqual(login.status_code, 200)
            content = self.client.get(
                "/api/admin/content",
                headers={"Authorization": "Bearer " + login.json()["access_token"]},
            )
            self.assertEqual(content.status_code, 200)

    def test_invalid_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 401)

    def test_upload_gallery_asset_and_delete(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        response = self.client.post(
            "/api/admin/gallery",
            headers=self.headers,
            data={"kind": "image", "caption": "Test"},
            files={"file": ("test.png", png, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertEqual(item["caption"], "Test")
        self.assertIn(item["asset"], self.fake_store.files)

        asset = self.client.get("/api/assets/" + item["asset"])
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.content, png)

        deleted = self.client.delete(
            "/api/admin/gallery/" + item["id"], headers=self.headers
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn(item["asset"], self.fake_store.files)

    def test_news_can_be_created_and_removed(self):
        response = self.client.post(
            "/api/admin/news",
            headers=self.headers,
            data={"tag": "خبر", "title": "عنوان", "text": "نص الخبر"},
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertEqual(self.fake_store.data["news"][0]["id"], item["id"])

        deleted = self.client.delete(
            "/api/admin/news/" + item["id"], headers=self.headers
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.fake_store.data["news"], [])

    def test_settings_are_validated_and_stored(self):
        response = self.client.put(
            "/api/admin/settings",
            headers=self.headers,
            json={
                "whatsapp": "963985122704",
                "facebook": "https://facebook.com/example",
                "hideDefaultGallery": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.fake_store.data["settings"]["hideDefaultGallery"])

        invalid = self.client.put(
            "/api/admin/settings",
            headers=self.headers,
            json={"whatsapp": "123"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_health_endpoint(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.json(), {"status": "ok"})

    def test_session_tokens_expire_and_reject_tampering(self):
        token = main.create_session_token("admin", "secret", now=1000)
        self.assertEqual(main.verify_session_token(token, "secret", now=1001), "admin")
        self.assertIsNone(
            main.verify_session_token(
                token, "secret", now=1000 + main.SESSION_TTL_SECONDS
            )
        )
        self.assertIsNone(main.verify_session_token(token + "x", "secret", now=1001))


class PlatformApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SESSION_SECRET": "test-platform-session-secret-long-enough",
                "ADMIN_USERNAME": "legacy-admin",
                "ADMIN_PASSWORD": "Qx9edbcb5679ea-9",
            },
        )
        self.env.start()
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

        def override_get_session():
            with Session(self.engine) as session:
                yield session

        main.app.dependency_overrides[get_session] = override_get_session
        main.app.dependency_overrides[main.optional_session] = override_get_session
        self.client = TestClient(main.app)
        with Session(self.engine) as session:
            permissions = [
                Permission(name="accounts.manage"),
                Permission(name="children.manage"),
                Permission(name="reports.read"),
            ]
            admin = Role(name="admin", permissions=permissions[:2])
            parent = Role(name="parent", permissions=[permissions[2]])
            session.add_all([admin, parent])
            session.add(
                Account(
                    username="platform-admin",
                    password_hash=main.PASSWORD_HASHER.hash("Qx8f83978c4138-9"),
                    roles=[admin],
                )
            )
            session.commit()
        login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "platform-admin", "password": "Qx8f83978c4138-9"},
        )
        self.assertEqual(login.status_code, 200)
        self.admin_headers = {
            "Authorization": "Bearer " + login.json()["access_token"]
        }
        legacy_login = self.client.post(
            "/api/auth/login",
            json={"username": "legacy-admin", "password": "Qx9edbcb5679ea-9"},
        )
        self.assertEqual(legacy_login.status_code, 200)
        self.legacy_admin_headers = {
            "Authorization": "Bearer " + legacy_login.json()["access_token"]
        }

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.pop(get_session, None)
        main.app.dependency_overrides.pop(main.optional_session, None)
        self.engine.dispose()
        self.env.stop()

    def test_registration_request_approval_issues_one_time_code(self):
        body = {
            "guardian_name": "Mona Parent",
            "email": "Mona@Example.com",
            "phone": "+963 11 1234567",
            "child_name": "Sam",
            "child_birth_date": "2021-05-04",
            "relationship_to_child": "mother",
            "notes": "",
            "preferred_language": "ar",
        }
        created = self.client.post("/api/platform/registration-requests", json=body)
        self.assertEqual(created.status_code, 202)
        duplicate = self.client.post("/api/platform/registration-requests", json=body)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            self.client.get("/api/admin/platform/registration-requests").status_code, 401
        )
        listed = self.client.get(
            "/api/admin/platform/registration-requests", headers=self.legacy_admin_headers
        ).json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["status"], "pending")
        self.assertEqual(listed[0]["email"], "mona@example.com")

        decision = self.client.post(
            f"/api/admin/platform/registration-requests/{listed[0]['id']}/decision",
            headers=self.legacy_admin_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(decision.status_code, 200)
        code = decision.json()["registration_code"]
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        again = self.client.post(
            f"/api/admin/platform/registration-requests/{listed[0]['id']}/decision",
            headers=self.legacy_admin_headers,
            json={"decision": "reject"},
        )
        self.assertEqual(again.status_code, 409)

        signup = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={
                "invitation_code": code.lower().replace("-", " "),
                "username": "mona",
                "password": "Qxdaa9b450839c-9",
            },
        )
        self.assertEqual(signup.status_code, 202)
        login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "mona", "password": "Qxdaa9b450839c-9"},
        )
        self.assertEqual(login.status_code, 200)
        after = self.client.get(
            "/api/admin/platform/registration-requests", headers=self.legacy_admin_headers
        ).json()[0]
        self.assertTrue(after["registered"])
        accounts = self.client.get(
            "/api/admin/platform/accounts", headers=self.legacy_admin_headers
        ).json()
        mona = next(account for account in accounts if account["username"] == "mona")
        self.assertEqual(mona["guardian_name"], "Mona Parent")
        self.assertEqual(mona["child_name"], "Sam")
        reuse = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={"invitation_code": code, "username": "mona2", "password": "Qxdaa9b450839c-9"},
        )
        self.assertEqual(reuse.status_code, 400)

    def test_unified_entry_routes_by_role(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "entry-teacher", "password": "Qx68cf697c6244-9"},
        )
        teacher = self.client.post(
            "/api/auth/entry",
            json={"username": "entry-teacher", "password": "Qx68cf697c6244-9"},
        )
        self.assertEqual(teacher.status_code, 200)
        self.assertEqual(teacher.json()["role"], "teacher")
        admin = self.client.post(
            "/api/auth/entry",
            json={"username": "legacy-admin", "password": "Qx9edbcb5679ea-9"},
        )
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()["role"], "admin")
        wrong = self.client.post(
            "/api/auth/entry", json={"username": "legacy-admin", "password": "nope"}
        )
        self.assertEqual(wrong.status_code, 401)

    def test_teacher_can_publish_website_content_but_not_manage_accounts(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "publisher", "password": "Qx876d5ef354db-9"},
        )
        login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "publisher", "password": "Qx876d5ef354db-9"},
        )
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        original_store = main.store
        main.store = FakeStore()
        try:
            content = self.client.get("/api/admin/content", headers=headers)
            self.assertEqual(content.status_code, 200)
            news = self.client.post(
                "/api/admin/news",
                headers=headers,
                data={"tag": "News", "title": "Hello", "text": "From a teacher"},
            )
            self.assertIn(news.status_code, (200, 201))
        finally:
            main.store = original_store
        self.assertEqual(
            self.client.put(
                "/api/admin/settings", headers=headers, json={"whatsapp": "963985122704"}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/admin/platform/accounts", headers=headers).status_code,
            401,
        )

    def test_wrong_registration_codes_are_rate_limited(self):
        for _ in range(main.CODE_ATTEMPT_LIMIT):
            wrong = self.client.post(
                "/api/platform/auth/redeem-invitation",
                json={"invitation_code": "AAAA-AAAA", "username": "x-user", "password": "Qx934b82a62c0f-9"},
            )
            self.assertEqual(wrong.status_code, 400)
        blocked = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={"invitation_code": "AAAA-AAAA", "username": "x-user", "password": "Qx934b82a62c0f-9"},
        )
        self.assertEqual(blocked.status_code, 429)

    def test_admin_can_edit_reissue_and_delete_registration_requests(self):
        body = {
            "guardian_name": "Edit Parent",
            "email": "edit@example.com",
            "phone": "123456789",
            "child_name": "Old Name",
        }
        self.client.post("/api/platform/registration-requests", json=body)
        listing = lambda: self.client.get(
            "/api/admin/platform/registration-requests", headers=self.legacy_admin_headers
        ).json()
        item = listing()[0]
        edited = self.client.patch(
            f"/api/admin/platform/registration-requests/{item['id']}",
            headers=self.legacy_admin_headers,
            json={**body, "guardian_name": "Fixed Parent", "child_name": "New Name"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["guardian_name"], "Fixed Parent")
        first = self.client.post(
            f"/api/admin/platform/registration-requests/{item['id']}/decision",
            headers=self.legacy_admin_headers,
            json={"decision": "approve"},
        ).json()["registration_code"]
        second = self.client.post(
            f"/api/admin/platform/registration-requests/{item['id']}/new-code",
            headers=self.legacy_admin_headers,
        )
        self.assertEqual(second.status_code, 200)
        new_code = second.json()["registration_code"]
        self.assertNotEqual(first, new_code)
        old_try = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={"invitation_code": first, "username": "edit-parent", "password": "Qx90fbb488d489-9"},
        )
        self.assertEqual(old_try.status_code, 400)
        deleted = self.client.delete(
            f"/api/admin/platform/registration-requests/{item['id']}",
            headers=self.legacy_admin_headers,
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(listing(), [])
        with Session(self.engine) as session:
            self.assertIsNone(session.scalar(select(Child).where(Child.display_name == "New Name")))

    def test_admin_assigns_teacher_and_publishes_report_to_parent(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        self.client.post(
            "/api/platform/registration-requests",
            json={
                "guardian_name": "Flow Parent",
                "email": "flow@example.com",
                "phone": "123456789",
                "child_name": "Flow Child",
            },
        )
        item = self.client.get(
            "/api/admin/platform/registration-requests", headers=self.legacy_admin_headers
        ).json()[0]
        code = self.client.post(
            f"/api/admin/platform/registration-requests/{item['id']}/decision",
            headers=self.legacy_admin_headers,
            json={"decision": "approve"},
        ).json()["registration_code"]
        self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={"invitation_code": code, "username": "flow-parent", "password": "Qxcd893cdb89f1-9"},
        )
        teacher = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "flow-teacher", "password": "Qxb2dee1d8a558-9"},
        ).json()
        children = self.client.get(
            "/api/admin/platform/children", headers=self.legacy_admin_headers
        ).json()
        child = next(c for c in children if c["display_name"] == "Flow Child")
        self.assertEqual(child["parents"], ["flow-parent"])
        assigned = self.client.post(
            f"/api/admin/platform/children/{child['id']}/teachers",
            headers=self.legacy_admin_headers,
            json={"teacher_id": teacher["id"]},
        )
        self.assertEqual(assigned.status_code, 201)

        teacher_token = self.client.post(
            "/api/platform/auth/login",
            json={"username": "flow-teacher", "password": "Qxb2dee1d8a558-9"},
        ).json()["access_token"]
        parent_token = self.client.post(
            "/api/platform/auth/login",
            json={"username": "flow-parent", "password": "Qxcd893cdb89f1-9"},
        ).json()["access_token"]
        report = self.client.post(
            "/api/platform/teacher/reports",
            headers={"Authorization": "Bearer " + teacher_token},
            json={"child_id": child["id"], "title": "Today", "body": "A good day", "submit_for_review": True},
        )
        self.assertEqual(report.status_code, 201)
        parent_headers = {"Authorization": "Bearer " + parent_token}
        before = self.client.get(f"/api/platform/children/{child['id']}/reports", headers=parent_headers)
        self.assertEqual(before.json(), [])
        pending = self.client.get(
            "/api/admin/platform/reports", headers=self.legacy_admin_headers
        ).json()
        self.assertEqual(pending[0]["child_name"], "Flow Child")
        self.assertEqual(pending[0]["author"], "flow-teacher")
        published = self.client.patch(
            f"/api/admin/platform/reports/{pending[0]['id']}",
            headers=self.legacy_admin_headers,
            json={"status": "published"},
        )
        self.assertEqual(published.status_code, 200)
        after = self.client.get(f"/api/platform/children/{child['id']}/reports", headers=parent_headers)
        self.assertEqual([r["title"] for r in after.json()], ["Today"])

    def test_admin_can_create_another_admin_with_full_access(self):
        created = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "second-admin", "role": "admin", "password": "Qx5a1b9c7d3e2f-9"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["roles"], ["admin"])
        entry = self.client.post(
            "/api/auth/entry", json={"username": "second-admin", "password": "Qx5a1b9c7d3e2f-9"}
        )
        self.assertEqual(entry.status_code, 200)
        self.assertEqual(entry.json()["portals"], ["admin"])
        headers = {"Authorization": "Bearer " + entry.json()["access_token"]}
        # The new admin manages accounts like the server admin and can add further admins.
        self.assertEqual(self.client.get("/api/admin/platform/accounts", headers=headers).status_code, 200)
        third = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=headers,
            json={"username": "third-admin", "role": "admin", "password": "Qx7c2d4e6f8a1-9"},
        )
        self.assertEqual(third.status_code, 201)
        # Safety: an admin cannot strip their own admin role or disable their own account.
        own = created.json()["id"]
        self.assertEqual(
            self.client.patch(f"/api/admin/platform/accounts/{own}", headers=headers, json={"roles": ["teacher"]}).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(f"/api/admin/platform/accounts/{own}/status", headers=headers, json={"status": "disabled"}).status_code,
            409,
        )

    def test_non_admin_cannot_create_admin(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "just-teacher", "password": "Qx3e5f7a9b1c-9"},
        )
        login = self.client.post(
            "/api/platform/auth/login", json={"username": "just-teacher", "password": "Qx3e5f7a9b1c-9"}
        )
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        denied = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=headers,
            json={"username": "sneaky", "role": "admin", "password": "Qx9b1c3d5e7f-9"},
        )
        self.assertEqual(denied.status_code, 401)

    def _post_setup(self):
        """Two children, one teacher assigned to the first only, and two parents (one per child)."""
        from datetime import datetime, timezone
        from app.models import parent_child_links
        with Session(self.engine) as session:
            teacher_role = Role(name="teacher")
            session.add(teacher_role)
            parent_role = session.scalar(select(Role).where(Role.name == "parent"))
            first = Child(display_name="Child One")
            second = Child(display_name="Child Two")
            teacher = Account(username="post-teacher", password_hash=main.PASSWORD_HASHER.hash("Qx2b4d6f8a0c-9"), roles=[teacher_role])
            parent_one = Account(username="parent-one", password_hash=main.PASSWORD_HASHER.hash("Qx3c5e7a9b1d-9"), roles=[parent_role])
            parent_two = Account(username="parent-two", password_hash=main.PASSWORD_HASHER.hash("Qx4d6f8b0c2e-9"), roles=[parent_role])
            session.add_all([first, second, teacher, parent_one, parent_two])
            session.flush()
            from app.models import teacher_child_links
            session.execute(teacher_child_links.insert().values(account_id=teacher.id, child_id=first.id, assigned_at=datetime.now(timezone.utc)))
            session.execute(parent_child_links.insert().values(account_id=parent_one.id, child_id=first.id, confirmed_at=datetime.now(timezone.utc)))
            session.execute(parent_child_links.insert().values(account_id=parent_two.id, child_id=second.id, confirmed_at=datetime.now(timezone.utc)))
            session.commit()
            ids = {"first": str(first.id), "second": str(second.id)}

        def headers(name, password):
            login = self.client.post("/api/platform/auth/login", json={"username": name, "password": password})
            self.assertEqual(login.status_code, 200)
            return {"Authorization": "Bearer " + login.json()["access_token"]}

        return (
            ids,
            headers("post-teacher", "Qx2b4d6f8a0c-9"),
            headers("parent-one", "Qx3c5e7a9b1d-9"),
            headers("parent-two", "Qx4d6f8b0c2e-9"),
        )

    def test_teacher_posts_general_for_all_and_private_for_one_childs_parents(self):
        ids, teacher, parent_one, parent_two = self._post_setup()
        general = self.client.post(
            "/api/platform/teacher/posts", headers=teacher,
            data={"scope": "general", "title": "Trip on Friday", "body": "Bring a hat."},
            files=[("files", ("plan.pdf", b"%PDF-1.4 plan", "application/pdf"))],
        )
        self.assertEqual(general.status_code, 201)
        self.assertEqual(general.json()["scope"], "general")
        self.assertEqual(len(general.json()["files"]), 1)
        private = self.client.post(
            "/api/platform/teacher/posts", headers=teacher,
            data={"scope": "child", "child_id": ids["first"], "title": "Grade", "body": "Very good work."},
            files=[("files", ("grade.pdf", b"%PDF-1.4 grade", "application/pdf"))],
        )
        self.assertEqual(private.status_code, 201)
        self.assertEqual(private.json()["child_name"], "Child One")
        # Every parent sees the general post, but only the first child's parent sees the private one.
        one = self.client.get("/api/platform/parent/posts", headers=parent_one).json()
        two = self.client.get("/api/platform/parent/posts", headers=parent_two).json()
        self.assertEqual(sorted(post["title"] for post in one), ["Grade", "Trip on Friday"])
        self.assertEqual([post["title"] for post in two], ["Trip on Friday"])
        self.assertNotIn("author_username", one[0])
        # File access follows the same rule.
        private_file = private.json()["files"][0]["id"]
        general_file = general.json()["files"][0]["id"]
        url = lambda post, file: f"/api/platform/parent/posts/{post['id']}/files/{file}"
        self.assertEqual(self.client.get(url(private.json(), private_file), headers=parent_one).status_code, 200)
        self.assertEqual(self.client.get(url(private.json(), private_file), headers=parent_two).status_code, 404)
        self.assertEqual(self.client.get(url(general.json(), general_file), headers=parent_two).status_code, 200)
        self.assertEqual(self.client.get(url(general.json(), private_file), headers=parent_one).status_code, 404)
        # The post attachments stay out of the teacher's personal file list.
        self.assertEqual(self.client.get("/api/platform/teacher/content", headers=teacher).json(), [])

    def test_private_post_needs_an_assigned_child_and_rejects_bad_input(self):
        ids, teacher, parent_one, _parent_two = self._post_setup()
        unassigned = self.client.post(
            "/api/platform/teacher/posts", headers=teacher,
            data={"scope": "child", "child_id": ids["second"], "title": "Nope", "body": "x"},
        )
        self.assertEqual(unassigned.status_code, 404)
        self.assertEqual(self.client.post("/api/platform/teacher/posts", headers=teacher, data={"scope": "child", "title": "No child", "body": "x"}).status_code, 422)
        self.assertEqual(self.client.post("/api/platform/teacher/posts", headers=teacher, data={"scope": "everyone", "title": "t", "body": "x"}).status_code, 422)
        self.assertEqual(self.client.post("/api/platform/teacher/posts", headers=teacher, data={"scope": "general", "title": "Empty", "body": ""}).status_code, 422)
        bad_file = self.client.post(
            "/api/platform/teacher/posts", headers=teacher, data={"scope": "general", "title": "Bad", "body": "x"},
            files=[("files", ("run.exe", b"MZ", "application/octet-stream"))],
        )
        self.assertEqual(bad_file.status_code, 415)
        # Parents cannot post.
        self.assertEqual(self.client.post("/api/platform/teacher/posts", headers=parent_one, data={"scope": "general", "title": "t", "body": "x"}).status_code, 403)

    def test_post_can_be_deleted_by_author_or_admin_only(self):
        _ids, teacher, parent_one, _parent_two = self._post_setup()
        post = self.client.post("/api/platform/teacher/posts", headers=teacher, data={"scope": "general", "title": "Temp", "body": "x"}).json()
        self.assertEqual(self.client.delete(f"/api/platform/teacher/posts/{post['id']}", headers=parent_one).status_code, 404)
        listed = self.client.get("/api/platform/admin/posts", headers=self.admin_headers)
        self.assertEqual([item["title"] for item in listed.json()], ["Temp"])
        self.assertEqual(self.client.delete(f"/api/platform/admin/posts/{post['id']}", headers=self.admin_headers).status_code, 204)
        self.assertEqual(self.client.get("/api/platform/parent/posts", headers=parent_one).json(), [])
        mine = self.client.post("/api/platform/teacher/posts", headers=teacher, data={"scope": "general", "title": "Mine", "body": "x"}).json()
        self.assertEqual(self.client.delete(f"/api/platform/teacher/posts/{mine['id']}", headers=teacher).status_code, 204)

    def test_admin_creates_parent_account_and_links_children(self):
        child = self.client.post("/api/platform/children", headers=self.admin_headers, json={"display_name": "Linked child"}).json()
        other = self.client.post("/api/platform/children", headers=self.admin_headers, json={"display_name": "Other child"}).json()
        created = self.client.post(
            "/api/admin/platform/teacher-accounts", headers=self.legacy_admin_headers,
            json={"username": "made-parent", "role": "parent", "child_id": child["id"], "password": "Qx6a8c0e2g4i-9"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["roles"], ["parent"])
        login = self.client.post("/api/auth/entry", json={"username": "made-parent", "password": "Qx6a8c0e2g4i-9"})
        self.assertEqual(login.json()["portals"], ["parent"])
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        self.assertEqual([c["display_name"] for c in self.client.get("/api/platform/children", headers=headers).json()], ["Linked child"])
        # An unknown child is refused; a second child can be linked and unlinked later.
        bad = self.client.post(
            "/api/admin/platform/teacher-accounts", headers=self.legacy_admin_headers,
            json={"username": "bad-parent", "role": "parent", "child_id": "00000000-0000-0000-0000-000000000000", "password": "Qx7b9d1f3h5j-9"},
        )
        self.assertEqual(bad.status_code, 404)
        base = f"/api/admin/platform/children/{other['id']}/parents"
        self.assertEqual(self.client.post(base, headers=self.legacy_admin_headers, json={"parent_id": created.json()["id"]}).status_code, 201)
        self.assertEqual(self.client.post(base, headers=self.legacy_admin_headers, json={"parent_id": created.json()["id"]}).status_code, 409)
        names = sorted(c["display_name"] for c in self.client.get("/api/platform/children", headers=headers).json())
        self.assertEqual(names, ["Linked child", "Other child"])
        listed = self.client.get("/api/admin/platform/children", headers=self.legacy_admin_headers).json()
        self.assertEqual([p["username"] for p in next(c for c in listed if c["id"] == other["id"])["parent_accounts"]], ["made-parent"])
        self.assertEqual(self.client.delete(f"{base}/{created.json()['id']}", headers=self.legacy_admin_headers).status_code, 204)
        self.assertEqual([c["display_name"] for c in self.client.get("/api/platform/children", headers=headers).json()], ["Linked child"])

    def test_admin_edits_account_and_resets_password(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        created = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "old-name", "password": "Qxcf40b2e53679-9"},
        ).json()
        other = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "taken-name", "password": "Qxd08ac0636475-9"},
        ).json()
        base = f"/api/admin/platform/accounts/{created['id']}"
        token = self.client.post(
            "/api/platform/auth/login", json={"username": "old-name", "password": "Qxcf40b2e53679-9"}
        ).json()["access_token"]
        self.assertEqual(
            self.client.patch(base, headers=self.legacy_admin_headers, json={"username": "taken-name"}).status_code, 409
        )
        renamed = self.client.patch(
            base, headers=self.legacy_admin_headers, json={"username": "New-Name", "preferred_language": "en"}
        )
        self.assertEqual(renamed.json()["username"], "new-name")
        self.assertEqual(  # open sessions end when the name changes
            self.client.get("/api/platform/auth/me", headers={"Authorization": "Bearer " + token}).status_code, 401
        )
        # a generated password is returned once and works; the stored value is only a hash
        reset = self.client.post(f"{base}/reset-password", headers=self.legacy_admin_headers, json={}).json()
        self.assertTrue(reset["generated"])
        self.assertGreaterEqual(len(reset["password"]), 12)
        with Session(self.engine) as session:
            stored = session.scalar(select(Account.password_hash).where(Account.username == "new-name"))
            self.assertNotIn(reset["password"], stored)
        self.assertEqual(
            self.client.post("/api/platform/auth/login", json={"username": "new-name", "password": "Qxcf40b2e53679-9"}).status_code, 401
        )
        self.assertEqual(
            self.client.post("/api/platform/auth/login", json={"username": "new-name", "password": reset["password"]}).status_code, 200
        )
        # a password chosen by the admin; too short is refused; other roles cannot do this
        chosen = self.client.post(f"{base}/reset-password", headers=self.legacy_admin_headers, json={"password": "Qx42a4e1000524-9"})
        self.assertFalse(chosen.json()["generated"])
        self.assertEqual(
            self.client.post(f"{base}/reset-password", headers=self.legacy_admin_headers, json={"password": "short"}).status_code, 422
        )
        self.assertEqual(self.client.post(f"{base}/reset-password", json={}).status_code, 401)
        self.assertEqual(other["username"], "taken-name")

    def test_account_can_hold_several_roles(self):
        with Session(self.engine) as session:
            session.add_all([Role(name="teacher"), Role(name="accountant")])
            session.commit()
        created = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={"username": "double-role", "password": "Qxaceda26a0992-9"},
        ).json()
        base = f"/api/admin/platform/accounts/{created['id']}"
        login = lambda: self.client.post(
            "/api/auth/entry", json={"username": "double-role", "password": "Qxaceda26a0992-9"}
        ).json()
        self.assertEqual(login()["portals"], ["teacher"])
        both = self.client.patch(base, headers=self.legacy_admin_headers, json={"roles": ["teacher", "accountant"]})
        self.assertEqual(both.status_code, 200)
        self.assertEqual(both.json()["roles"], ["accountant", "teacher"])
        entry = login()
        self.assertEqual(entry["portals"], ["teacher", "accountant"])
        headers = {"Authorization": "Bearer " + entry["access_token"]}
        # one token works for what both roles allow
        self.assertEqual(self.client.get("/api/admin/fees", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/accounting/salaries", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/content", headers=headers).status_code, 503)  # passed the guard (no GitHub here)
        # roles can be reduced again, but never to nothing or to unknown roles
        self.assertEqual(self.client.patch(base, headers=self.legacy_admin_headers, json={"roles": []}).status_code, 422)
        self.assertEqual(self.client.patch(base, headers=self.legacy_admin_headers, json={"roles": ["manager"]}).status_code, 422)
        only = self.client.patch(base, headers=self.legacy_admin_headers, json={"roles": ["teacher"]})
        self.assertEqual(only.json()["roles"], ["teacher"])
        self.assertEqual(self.client.get("/api/admin/fees", headers=headers).status_code, 403)

    def test_rejected_registration_request_gets_no_code(self):
        self.client.post(
            "/api/platform/registration-requests",
            json={
                "guardian_name": "Other Parent",
                "email": "other@example.com",
                "phone": "123456789",
                "child_name": "Kid",
            },
        )
        item = self.client.get(
            "/api/admin/platform/registration-requests", headers=self.legacy_admin_headers
        ).json()[0]
        rejected = self.client.post(
            f"/api/admin/platform/registration-requests/{item['id']}/decision",
            headers=self.legacy_admin_headers,
            json={"decision": "reject"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertNotIn("registration_code", rejected.json())
        self.assertEqual(rejected.json()["request"]["status"], "rejected")

    def test_staff_invitation_creates_parent_link_and_is_one_time(self):
        child_response = self.client.post(
            "/api/platform/children",
            headers=self.admin_headers,
            json={"display_name": "Private child"},
        )
        self.assertEqual(child_response.status_code, 201)
        child = child_response.json()
        other_child = self.client.post(
            "/api/platform/children",
            headers=self.admin_headers,
            json={"display_name": "Unrelated child"},
        )
        self.assertEqual(other_child.status_code, 201)
        invitation_response = self.client.post(
            f"/api/platform/children/{child['id']}/guardian-invitations",
            headers=self.admin_headers,
            json={"expires_in_hours": 24},
        )
        self.assertEqual(invitation_response.status_code, 201)
        code = invitation_response.json()["invitation_code"]

        with Session(self.engine) as session:
            stored_invitation = session.scalar(select(GuardianInvitation))
            self.assertIsNotNone(stored_invitation)
            assert stored_invitation is not None
            self.assertEqual(
                stored_invitation.token_hash, hashlib.sha256(code.encode()).hexdigest()
            )
            self.assertNotEqual(stored_invitation.token_hash, code)

        signup = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={
                "invitation_code": code,
                "username": "guardian-one",
                "password": "Qx53aa7cd18bad-9",
                "preferred_language": "ar",
            },
        )
        self.assertEqual(signup.status_code, 202)
        self.assertNotIn("access_token", signup.json())
        pending_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "guardian-one", "password": "Qx53aa7cd18bad-9"},
        )
        self.assertEqual(pending_login.status_code, 403)
        self.assertIn("awaiting administrator approval", pending_login.json()["detail"])
        accounts = self.client.get(
            "/api/admin/platform/accounts", headers=self.legacy_admin_headers
        )
        self.assertEqual(accounts.status_code, 200)
        parent_account = next(
            account for account in accounts.json() if account["username"] == "guardian-one"
        )
        self.assertEqual(parent_account["approval_status"], "pending")
        approved = self.client.patch(
            f"/api/admin/platform/accounts/{parent_account['id']}/status",
            headers=self.legacy_admin_headers,
            json={"status": "active"},
        )
        self.assertEqual(approved.status_code, 200)
        parent_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "guardian-one", "password": "Qx53aa7cd18bad-9"},
        )
        self.assertEqual(parent_login.status_code, 200)
        parent_headers = {
            "Authorization": "Bearer " + parent_login.json()["access_token"]
        }
        children_response = self.client.get(
            "/api/platform/children", headers=parent_headers
        )
        self.assertEqual(children_response.json(), [child])
        self.assertEqual(children_response.headers["cache-control"], "no-store")
        self.assertNotEqual(other_child.json()["id"], child["id"])
        profile = self.client.get("/api/platform/auth/me", headers=parent_headers)
        self.assertEqual(profile.json()["roles"], ["parent"])
        self.assertEqual(profile.headers["cache-control"], "no-store")

        reuse = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={
                "invitation_code": code,
                "username": "guardian-two",
                "password": "Qx780f21acdc18-9",
            },
        )
        self.assertEqual(reuse.status_code, 400)

    def test_admin_creates_and_approves_teacher_then_disables_session(self):
        with Session(self.engine) as session:
            session.add(Role(name="teacher"))
            session.commit()
        created = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.legacy_admin_headers,
            json={
                "username": "new-teacher",
                "password": "Qxb5031ed354c6-9",
                "preferred_language": "ar",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["approval_status"], "active")
        listed = self.client.get(
            "/api/admin/platform/accounts", headers=self.legacy_admin_headers
        ).json()
        self.assertIn("new-teacher", [account["username"] for account in listed])
        login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "new-teacher", "password": "Qxb5031ed354c6-9"},
        )
        self.assertEqual(login.status_code, 200)
        teacher_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        disabled = self.client.patch(
            f"/api/admin/platform/accounts/{created.json()['id']}/status",
            headers=self.legacy_admin_headers,
            json={"status": "disabled"},
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(
            self.client.get("/api/platform/auth/me", headers=teacher_headers).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/platform/auth/login",
                json={
                    "username": "new-teacher",
                    "password": "Qxb5031ed354c6-9",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/admin/platform/accounts/{created.json()['id']}/status",
                headers=self.admin_headers,
                json={"status": "active"},
            ).status_code,
            200,  # a platform account with the admin role is an admin too
        )

    def test_parent_cannot_create_children_or_invitations(self):
        with Session(self.engine) as session:
            admin = session.scalar(
                select(Account).where(Account.username == "platform-admin")
            )
            assert admin is not None
            child = Child(
                display_name="Private child",
                created_by_id=admin.id,
            )
            session.add(child)
            session.commit()
            child_id = child.id
            parent_role = session.scalar(select(Role).where(Role.name == "parent"))
            session.add(
                Account(
                    username="parent-one",
                    password_hash=main.PASSWORD_HASHER.hash("Qxa58f753c6368-9"),
                    roles=[parent_role],
                )
            )
            session.commit()
        login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "parent-one", "password": "Qxa58f753c6368-9"},
        )
        parent_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        response = self.client.post(
            "/api/platform/children",
            headers=parent_headers,
            json={"display_name": "Unauthorized child"},
        )
        self.assertEqual(response.status_code, 403)
        invitation = self.client.post(
            f"/api/platform/children/{child_id}/guardian-invitations",
            headers=parent_headers,
            json={},
        )
        self.assertEqual(invitation.status_code, 403)

    def test_portal_login_is_rate_limited_and_logout_revokes_session(self):
        for _ in range(main.PORTAL_LOGIN_MAX_FAILURES):
            response = self.client.post(
                "/api/platform/auth/login",
                json={"username": "missing-user", "password": "Qx6809ffccad03-9"},
            )
            self.assertEqual(response.status_code, 401)
        limited = self.client.post(
            "/api/platform/auth/login",
            json={"username": "missing-user", "password": "Qx6809ffccad03-9"},
        )
        self.assertEqual(limited.status_code, 429)

        logout = self.client.post(
            "/api/platform/auth/logout", headers=self.admin_headers
        )
        self.assertEqual(logout.status_code, 200)
        profile = self.client.get(
            "/api/platform/auth/me", headers=self.admin_headers
        )
        self.assertEqual(profile.status_code, 401)

    def test_teacher_reports_require_assignment_and_review_before_parent_access(self):
        child_response = self.client.post(
            "/api/platform/children",
            headers=self.admin_headers,
            json={"display_name": "Assigned child"},
        )
        other_child_response = self.client.post(
            "/api/platform/children",
            headers=self.admin_headers,
            json={"display_name": "Unassigned child"},
        )
        self.assertEqual(child_response.status_code, 201)
        self.assertEqual(other_child_response.status_code, 201)
        child = child_response.json()
        other_child = other_child_response.json()

        with Session(self.engine) as session:
            teacher_role = Role(name="teacher")
            manager_role = Role(name="manager")
            session.add_all([teacher_role, manager_role])
            session.add_all(
                [
                    Account(
                        username="teacher-one",
                        password_hash=main.PASSWORD_HASHER.hash(
                            "Qx1a115ff15e66-9"
                        ),
                        roles=[teacher_role],
                    ),
                    Account(
                        username="manager-one",
                        password_hash=main.PASSWORD_HASHER.hash(
                            "Qxfb3e4c8f4b69-9"
                        ),
                        roles=[manager_role],
                    ),
                ]
            )
            session.commit()
            teacher = session.scalar(
                select(Account).where(Account.username == "teacher-one")
            )
            assert teacher is not None
            teacher_id = teacher.id
        assignment = self.client.post(
            f"/api/platform/children/{child['id']}/teachers",
            headers=self.admin_headers,
            json={"teacher_id": str(teacher_id)},
        )
        self.assertEqual(assignment.status_code, 201)
        teacher_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "teacher-one", "password": "Qx1a115ff15e66-9"},
        )
        teacher_headers = {
            "Authorization": "Bearer " + teacher_login.json()["access_token"]
        }
        self.assertEqual(
            self.client.get(
                "/api/platform/teacher/children", headers=teacher_headers
            ).json(),
            [child],
        )
        report = self.client.post(
            "/api/platform/teacher/reports",
            headers=teacher_headers,
            json={
                "child_id": child["id"],
                "title": "Art time",
                "body": "We painted flowers today.",
                "submit_for_review": True,
            },
        )
        self.assertEqual(report.status_code, 201)
        self.assertEqual(report.json()["status"], "submitted")
        unassigned_report = self.client.post(
            "/api/platform/teacher/reports",
            headers=teacher_headers,
            json={
                "child_id": other_child["id"],
                "title": "Not allowed",
                "body": "This child was not assigned.",
                "submit_for_review": True,
            },
        )
        self.assertEqual(unassigned_report.status_code, 404)

        invitation = self.client.post(
            f"/api/platform/children/{child['id']}/guardian-invitations",
            headers=self.admin_headers,
            json={},
        )
        parent_signup = self.client.post(
            "/api/platform/auth/redeem-invitation",
            json={
                "invitation_code": invitation.json()["invitation_code"],
                "username": "linked-parent",
                "password": "Qx0065e03f1197-9",
            },
        )
        self.assertEqual(parent_signup.status_code, 202)
        parent_pending = self.client.post(
            "/api/platform/auth/login",
            json={"username": "linked-parent", "password": "Qx0065e03f1197-9"},
        )
        self.assertEqual(parent_pending.status_code, 403)
        account_list = self.client.get(
            "/api/admin/platform/accounts", headers=self.legacy_admin_headers
        )
        parent_account = next(
            account
            for account in account_list.json()
            if account["username"] == "linked-parent"
        )
        self.assertEqual(
            self.client.patch(
                f"/api/admin/platform/accounts/{parent_account['id']}/status",
                headers=self.legacy_admin_headers,
                json={"status": "active"},
            ).status_code,
            200,
        )
        parent_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "linked-parent", "password": "Qx0065e03f1197-9"},
        )
        parent_headers = {
            "Authorization": "Bearer " + parent_login.json()["access_token"]
        }
        self.assertEqual(
            self.client.get(
                f"/api/platform/children/{child['id']}/reports",
                headers=parent_headers,
            ).json(),
            [],
        )
        self.assertEqual(
            self.client.get(
                f"/api/platform/children/{other_child['id']}/reports",
                headers=parent_headers,
            ).status_code,
            404,
        )

        manager_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "manager-one", "password": "Qxfb3e4c8f4b69-9"},
        )
        manager_headers = {
            "Authorization": "Bearer " + manager_login.json()["access_token"]
        }
        review_queue = self.client.get(
            "/api/platform/review/reports", headers=manager_headers
        )
        self.assertEqual(len(review_queue.json()), 1)
        rejected = self.client.patch(
            f"/api/platform/review/reports/{report.json()['id']}",
            headers=manager_headers,
            json={"status": "rejected"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "rejected")
        revised = self.client.patch(
            f"/api/platform/teacher/reports/{report.json()['id']}",
            headers=teacher_headers,
            json={
                "title": "Art time - revised",
                "body": "We painted flowers and made cards today.",
                "submit_for_review": True,
            },
        )
        self.assertEqual(revised.status_code, 200)
        self.assertEqual(revised.json()["status"], "submitted")
        self.assertEqual(revised.json()["title"], "Art time - revised")
        published = self.client.patch(
            f"/api/platform/review/reports/{report.json()['id']}",
            headers=manager_headers,
            json={"status": "published"},
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["body"], "We painted flowers and made cards today.")
        parent_reports = self.client.get(
            f"/api/platform/children/{child['id']}/reports",
            headers=parent_headers,
        )
        self.assertEqual([item["id"] for item in parent_reports.json()], [report.json()["id"]])

    def test_teacher_uploads_are_private_and_report_attachments_are_author_scoped(self):
        with Session(self.engine) as session:
            teacher_role = Role(name="teacher")
            parent_role = session.scalar(select(Role).where(Role.name == "parent"))
            assert parent_role is not None
            teacher = Account(
                username="content-teacher",
                password_hash=main.PASSWORD_HASHER.hash("Qx1a115ff15e66-9"),
                roles=[teacher_role],
            )
            other_teacher = Account(
                username="other-content-teacher",
                password_hash=main.PASSWORD_HASHER.hash("Qx5d3d349c303c-9"),
                roles=[teacher_role],
            )
            parent = Account(
                username="content-parent",
                password_hash=main.PASSWORD_HASHER.hash("Qxa58f753c6368-9"),
                roles=[parent_role],
            )
            session.add_all([teacher, other_teacher, parent])
            session.commit()
            teacher_id = teacher.id

        teacher_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "content-teacher", "password": "Qx1a115ff15e66-9"},
        )
        teacher_headers = {
            "Authorization": "Bearer " + teacher_login.json()["access_token"]
        }
        parent_login = self.client.post(
            "/api/platform/auth/login",
            json={"username": "content-parent", "password": "Qxa58f753c6368-9"},
        )
        parent_headers = {
            "Authorization": "Bearer " + parent_login.json()["access_token"]
        }
        other_teacher_login = self.client.post(
            "/api/platform/auth/login",
            json={
                "username": "other-content-teacher",
                "password": "Qx5d3d349c303c-9",
            },
        )
        other_teacher_headers = {
            "Authorization": "Bearer " + other_teacher_login.json()["access_token"]
        }

        upload = self.client.post(
            "/api/platform/teacher/content",
            headers=teacher_headers,
            data={"category": "document"},
            files={"file": ("lesson.pdf", b"%PDF-1.7\nprivate lesson", "application/pdf")},
        )
        self.assertEqual(upload.status_code, 201)
        upload_id = upload.json()["id"]
        self.assertEqual(
            self.client.get(
                "/api/platform/teacher/content", headers=teacher_headers
            ).json()[0]["id"],
            upload_id,
        )
        owner_download = self.client.get(
            f"/api/platform/teacher/content/{upload_id}/download",
            headers=teacher_headers,
        )
        self.assertEqual(owner_download.status_code, 200)
        self.assertEqual(owner_download.content, b"%PDF-1.7\nprivate lesson")
        self.assertEqual(owner_download.headers["cache-control"], "private, no-store")
        self.assertEqual(owner_download.headers["x-content-type-options"], "nosniff")
        self.assertEqual(
            self.client.get(
                f"/api/platform/teacher/content/{upload_id}/download",
                headers=parent_headers,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/platform/teacher/content/{upload_id}/download",
                headers=other_teacher_headers,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/api/platform/teacher/content", headers=other_teacher_headers
            ).json(),
            [],
        )
        admin_list = self.client.get(
            "/api/platform/admin/teacher-content", headers=self.admin_headers
        )
        self.assertEqual([item["id"] for item in admin_list.json()], [upload_id])
        self.assertEqual(admin_list.json()[0]["owner_username"], "content-teacher")
        self.assertEqual(
            self.client.get(
                f"/api/platform/admin/teacher-content/{upload_id}/download",
                headers=self.admin_headers,
            ).content,
            b"%PDF-1.7\nprivate lesson",
        )

        invalid = self.client.post(
            "/api/platform/teacher/content",
            headers=teacher_headers,
            data={"category": "document"},
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        self.assertEqual(invalid.status_code, 415)

        child_response = self.client.post(
            "/api/platform/children",
            headers=self.admin_headers,
            json={"display_name": "Report attachment child"},
        )
        child = child_response.json()
        assignment = self.client.post(
            f"/api/platform/children/{child['id']}/teachers",
            headers=self.admin_headers,
            json={"teacher_id": str(teacher_id)},
        )
        self.assertEqual(assignment.status_code, 201)
        report = self.client.post(
            "/api/platform/teacher/reports",
            headers=teacher_headers,
            json={
                "child_id": child["id"],
                "title": "Private attachment report",
                "body": "A report with a private attachment.",
            },
        )
        self.assertEqual(report.status_code, 201)
        attachment = self.client.post(
            "/api/platform/teacher/content",
            headers=teacher_headers,
            data={
                "category": "report_attachment",
                "report_id": report.json()["id"],
            },
            files={"file": ("report.pdf", b"%PDF-1.7\nreport attachment", "application/pdf")},
        )
        self.assertEqual(attachment.status_code, 201)
        for index in range(4):
            next_attachment = self.client.post(
                "/api/platform/teacher/content",
                headers=teacher_headers,
                data={
                    "category": "report_attachment",
                    "report_id": report.json()["id"],
                },
                files={
                    "file": (
                        f"report-{index}.pdf",
                        b"%PDF-1.7\nadditional attachment",
                        "application/pdf",
                    )
                },
            )
            self.assertEqual(next_attachment.status_code, 201)
        over_limit = self.client.post(
            "/api/platform/teacher/content",
            headers=teacher_headers,
            data={
                "category": "report_attachment",
                "report_id": report.json()["id"],
            },
            files={"file": ("sixth.pdf", b"%PDF-1.7\nsixth", "application/pdf")},
        )
        self.assertEqual(over_limit.status_code, 409)
        self.assertEqual(
            len(
                self.client.get(
                    f"/api/platform/teacher/reports/{report.json()['id']}/attachments",
                    headers=teacher_headers,
                ).json()
            ),
            5,
        )
        self.assertEqual(
            self.client.get(
                f"/api/platform/teacher/reports/{report.json()['id']}/attachments",
                headers=parent_headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/platform/children/{child['id']}/reports",
                headers=parent_headers,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/platform/teacher/content/{upload_id}",
                headers=teacher_headers,
            ).status_code,
            204,
        )


if __name__ == "__main__":
    unittest.main()
