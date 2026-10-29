import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base, get_engine, normalize_database_url
from app.manage import PASSWORD_HASHER, create_account
from app.models import Account, Permission, Role


class DatabaseTests(unittest.TestCase):
    def test_postgres_urls_use_psycopg(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host/database"),
            "postgresql+psycopg://user:pass@host/database",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@host/database"),
            "postgresql+psycopg://user:pass@host/database",
        )
        self.assertEqual(normalize_database_url("sqlite:///test.db"), "sqlite:///test.db")

    def test_accounts_support_multiple_roles_and_permissions(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            permission = Permission(name="reports.read")
            parent = Role(name="parent", permissions=[permission])
            teacher = Role(name="teacher")
            account = Account(
                username="test-parent",
                password_hash="argon2-hash-placeholder",
                preferred_language="ar",
                roles=[parent, teacher],
            )
            session.add(account)
            session.commit()

            stored = session.scalar(
                select(Account).where(Account.username == "test-parent")
            )
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(
                {role.name for role in stored.roles}, {"parent", "teacher"}
            )
            parent_role = next(role for role in stored.roles if role.name == "parent")
            self.assertEqual([item.name for item in parent_role.permissions], ["reports.read"])

        engine.dispose()

    def test_account_creation_hashes_password_and_normalizes_username(self):
        with patch.dict(
            "os.environ", {"DATABASE_URL": "sqlite+pysqlite:///:memory:"}
        ):
            get_engine.cache_clear()
            engine = get_engine()
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add(Role(name="teacher"))
                session.commit()

            create_account("  Teacher.Name  ", "teacher", "a-long-test-password")
            with Session(engine) as session:
                account = session.scalar(
                    select(Account).where(Account.username == "teacher.name")
                )
                self.assertIsNotNone(account)
                assert account is not None
                self.assertTrue(
                    PASSWORD_HASHER.verify("a-long-test-password", account.password_hash)
                )
                self.assertNotEqual(account.password_hash, "a-long-test-password")
            engine.dispose()
            get_engine.cache_clear()

    def test_account_creation_rejects_weak_passwords(self):
        with self.assertRaisesRegex(ValueError, "at least 12 characters"):
            create_account("teacher", "teacher", "too-short")


if __name__ == "__main__":
    unittest.main()
