import os
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import fees, main
from app.database import Base, get_session
from app.models import Account, Child, FeeAuditLog, FeePayment, Role


def fake_charge(amount, *payments):
    return SimpleNamespace(
        amount=Decimal(amount),
        payments=[
            SimpleNamespace(amount=Decimal(value), deleted_at=deleted)
            for value, deleted in payments
        ],
    )


class FeeCalculationTests(unittest.TestCase):
    def test_paid_and_remaining_are_derived_from_active_payments(self):
        charge = fake_charge("100", ("30", None), ("20.50", None), ("999", "deleted"))
        self.assertEqual(fees.paid_amount(charge), Decimal("50.50"))
        self.assertEqual(fees.remaining_amount(charge), Decimal("49.50"))

    def test_status(self):
        self.assertEqual(fees.status_of(Decimal("100"), Decimal("0")), "open")
        self.assertEqual(fees.status_of(Decimal("100"), Decimal("40")), "partial")
        self.assertEqual(fees.status_of(Decimal("100"), Decimal("100")), "paid")

    def test_zero_or_empty_never_counts_as_paid(self):
        # 0 due / 0 paid / 0 open and an empty amount are "needs review", never "paid"
        self.assertEqual(fees.status_of(Decimal("0"), Decimal("0")), "review")
        self.assertEqual(fees.status_of(None, Decimal("0")), "review")
        self.assertEqual(fees.status_of(None, Decimal("50")), "review")
        self.assertEqual(fees.status_of(Decimal("0"), Decimal("10")), "review")
        # a row flagged by the import stays "review" even when it adds up
        self.assertEqual(fees.status_of(Decimal("100"), Decimal("100"), needs_review=True), "review")

    def test_totals_keep_currencies_apart(self):
        rows = [
            {"currency": "USD", "amount": "100.00", "paid": "40.00", "remaining": "60.00"},
            {"currency": "USD", "amount": "50.00", "paid": "50.00", "remaining": "0.00"},
            {"currency": "SYP", "amount": "500000.00", "paid": "100000.00", "remaining": "400000.00"},
        ]
        totals = fees.totals_by_currency(rows)
        self.assertEqual(totals["USD"], {"amount": "150.00", "paid": "90.00", "remaining": "60.00"})
        self.assertEqual(
            totals["SYP"], {"amount": "500000.00", "paid": "100000.00", "remaining": "400000.00"}
        )

    def test_totals_ignore_empty_amounts(self):
        rows = [
            {"currency": "SYP", "amount": None, "paid": "10.00", "remaining": None},
            {"currency": "SYP", "amount": "100.00", "paid": "0.00", "remaining": "100.00"},
        ]
        self.assertEqual(fees.totals_by_currency(rows)["SYP"], {"amount": "100.00", "paid": "10.00", "remaining": "100.00"})

    def test_totals_are_zero_for_empty_currency(self):
        self.assertEqual(
            fees.totals_by_currency([])["USD"], {"amount": "0.00", "paid": "0.00", "remaining": "0.00"}
        )


class FeeApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SESSION_SECRET": "test-fees-session-secret-long-enough",
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
            roles = {name: Role(name=name) for name in ("admin", "teacher", "parent", "accountant")}
            session.add_all(roles.values())
            for username, role in (
                ("accountant1", "accountant"),
                ("teacher1", "teacher"),
                ("parent1", "parent"),
                ("platform-admin", "admin"),
            ):
                session.add(
                    Account(
                        username=username,
                        password_hash=main.PASSWORD_HASHER.hash("Qx5a6ba62b7e4b-9"),
                        roles=[roles[role]],
                    )
                )
            session.add_all(
                [
                    Child(display_name="Amal", class_name="KG1"),
                    Child(display_name="Bashar", class_name="KG2"),
                ]
            )
            session.commit()
        self.tokens = {
            name: {
                "Authorization": "Bearer "
                + self.client.post(
                    "/api/platform/auth/login",
                    json={"username": name, "password": "Qx5a6ba62b7e4b-9"},
                ).json()["access_token"]
            }
            for name in ("accountant1", "teacher1", "parent1", "platform-admin")
        }
        self.tokens["legacy"] = {
            "Authorization": "Bearer "
            + self.client.post(
                "/api/auth/login",
                json={"username": "legacy-admin", "password": "Qx9edbcb5679ea-9"},
            ).json()["access_token"]
        }
        self.acc = self.tokens["accountant1"]
        self.children = {
            c["display_name"]: c["id"]
            for c in self.client.get("/api/admin/fees/children", headers=self.acc).json()
        }

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.pop(get_session, None)
        main.app.dependency_overrides.pop(main.optional_session, None)
        self.engine.dispose()
        self.env.stop()

    def charge(self, child="Amal", amount="100", currency="USD", year=2026, month=10):
        response = self.client.post(
            "/api/admin/fees/charges",
            headers=self.acc,
            json={
                "child_id": self.children[child],
                "year": year,
                "month": month,
                "amount": amount,
                "currency": currency,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def pay(self, charge_id, amount, receipt=None, paid_on="2026-10-05"):
        return self.client.post(
            f"/api/admin/fees/charges/{charge_id}/payments",
            headers=self.acc,
            json={"amount": amount, "paid_on": paid_on, "receipt_no": receipt, "note": ""},
        )

    # --- access control ------------------------------------------------------

    def test_only_accountant_and_admin_may_use_fees(self):
        for name in ("accountant1", "platform-admin", "legacy"):
            response = self.client.get("/api/admin/fees", headers=self.tokens[name])
            self.assertEqual(response.status_code, 200, name)
        for name in ("teacher1", "parent1"):
            response = self.client.get("/api/admin/fees", headers=self.tokens[name])
            self.assertEqual(response.status_code, 403, name)
        self.assertEqual(self.client.get("/api/admin/fees").status_code, 401)

    def test_every_fee_route_rejects_teachers_and_parents(self):
        charge = self.charge()
        routes = [
            ("get", "/api/admin/fees/children"),
            ("get", "/api/admin/fees/summary"),
            ("get", "/api/admin/fees/audit"),
            ("post", "/api/admin/fees/charges"),
            ("post", "/api/admin/fees/generate"),
            ("patch", f"/api/admin/fees/charges/{charge['id']}"),
            ("delete", f"/api/admin/fees/charges/{charge['id']}"),
            ("post", f"/api/admin/fees/charges/{charge['id']}/payments"),
        ]
        for name in ("teacher1", "parent1"):
            for method, path in routes:
                response = getattr(self.client, method)(path, headers=self.tokens[name])
                self.assertEqual(response.status_code, 403, f"{name} {method} {path}")

    def test_admin_creates_accountant_account_who_lands_on_fees(self):
        with Session(self.engine) as session:
            self.assertIsNotNone(session.scalar(select(Role).where(Role.name == "accountant")))
        created = self.client.post(
            "/api/admin/platform/teacher-accounts",
            headers=self.tokens["legacy"],
            json={"role": "accountant", "username": "new-accountant", "password": "Qx7f3a9c1d2e44-9"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["roles"], ["accountant"])
        entry = self.client.post(
            "/api/auth/entry",
            json={"username": "new-accountant", "password": "Qx7f3a9c1d2e44-9"},
        )
        self.assertEqual(entry.json()["role"], "accountant")

    # --- calculations through the API ----------------------------------------

    def test_partial_payments_totals_and_currencies_stay_separate(self):
        usd = self.charge("Amal", "100", "USD")
        self.charge("Bashar", "200", "USD")
        syp = self.charge("Amal", "500000", "SYP")
        self.assertEqual(self.pay(usd["id"], "40", "R-1").status_code, 201)
        after = self.pay(usd["id"], "10", "R-2").json()
        self.assertEqual(after["paid"], "50.00")
        self.assertEqual(after["remaining"], "50.00")
        self.assertEqual(after["status"], "partial")
        self.assertEqual(after["receipts"], ["R-1", "R-2"])
        self.assertEqual(self.pay(syp["id"], "500000", "R-3").json()["status"], "paid")

        listing = self.client.get(
            "/api/admin/fees?year=2026&month=10", headers=self.acc
        ).json()
        self.assertEqual(
            listing["totals"]["USD"], {"amount": "300.00", "paid": "50.00", "remaining": "250.00"}
        )
        self.assertEqual(
            listing["totals"]["SYP"],
            {"amount": "500000.00", "paid": "500000.00", "remaining": "0.00"},
        )
        only_open = self.client.get("/api/admin/fees?status=open", headers=self.acc).json()
        self.assertEqual([r["child_name"] for r in only_open["rows"]], ["Bashar"])
        by_class = self.client.get("/api/admin/fees?class_name=KG1", headers=self.acc).json()
        self.assertEqual({r["child_name"] for r in by_class["rows"]}, {"Amal"})
        self.assertEqual([r["n"] for r in listing["rows"]], [1, 2, 3])

        summary = self.client.get(
            "/api/admin/fees/summary?year=2026&month=10", headers=self.acc
        ).json()
        self.assertEqual(summary["paid"], {"USD": "50.00", "SYP": "500000.00"})
        by_date = self.client.get(
            "/api/admin/fees/summary?date_from=2026-10-06&date_to=2026-10-31", headers=self.acc
        ).json()
        self.assertEqual(by_date["paid"], {"USD": "0.00", "SYP": "0.00"})

    # --- validation ----------------------------------------------------------

    def test_validation_rules(self):
        charge = self.charge("Amal", "100")
        self.assertEqual(self.pay(charge["id"], "100.01").status_code, 422)  # over the open amount
        self.assertEqual(self.pay(charge["id"], "0").status_code, 422)
        self.assertEqual(self.pay(charge["id"], "-5").status_code, 422)
        self.assertEqual(self.pay(charge["id"], "60", "DUP").status_code, 201)
        self.assertEqual(self.pay(charge["id"], "10", "DUP").status_code, 409)  # unique receipt
        self.assertEqual(self.pay(charge["id"], "40.01").status_code, 422)  # only 40 left
        duplicate = self.client.post(
            "/api/admin/fees/charges",
            headers=self.acc,
            json={"child_id": self.children["Amal"], "year": 2026, "month": 10, "amount": "5", "currency": "USD"},
        )
        self.assertEqual(duplicate.status_code, 409)
        for bad in (
            {"amount": "-1", "currency": "USD"},
            {"amount": "10", "currency": "EUR"},
            {"amount": "10", "currency": "USD", "month": 13},
        ):
            payload = {"child_id": self.children["Bashar"], "year": 2026, "month": 11, **bad}
            self.assertEqual(
                self.client.post("/api/admin/fees/charges", headers=self.acc, json=payload).status_code,
                422,
            )
        too_low = self.client.patch(
            f"/api/admin/fees/charges/{charge['id']}", headers=self.acc, json={"amount": "50"}
        )
        self.assertEqual(too_low.status_code, 422)  # 60 already paid

    # --- edit / soft delete / audit ------------------------------------------

    def test_edit_and_soft_delete_payment_with_audit_log(self):
        charge = self.charge("Amal", "100")
        paid = self.pay(charge["id"], "70", "A-1").json()
        payment_id = paid["payments"][0]["id"]
        edited = self.client.patch(
            f"/api/admin/fees/payments/{payment_id}",
            headers=self.acc,
            json={"amount": "100", "paid_on": "2026-10-07", "receipt_no": "A-1", "note": "corrected"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["status"], "paid")
        deleted = self.client.delete(f"/api/admin/fees/payments/{payment_id}", headers=self.acc)
        self.assertEqual(deleted.json()["paid"], "0.00")
        self.assertEqual(deleted.json()["status"], "open")
        # soft delete: row is kept, and the receipt number can be used again
        with Session(self.engine) as session:
            row = session.scalar(select(FeePayment))
            self.assertIsNotNone(row.deleted_at)
            self.assertEqual(row.created_by_name, "accountant1")
        self.assertEqual(self.pay(charge["id"], "10", "A-1").status_code, 201)
        with Session(self.engine) as session:
            actions = [e.action for e in session.scalars(select(FeeAuditLog).order_by(FeeAuditLog.at))]
        for expected in ("charge.create", "payment.create", "payment.update", "payment.delete"):
            self.assertIn(expected, actions)
        audit = self.client.get("/api/admin/fees/audit", headers=self.acc).json()
        self.assertTrue(all(entry["actor"] == "accountant1" for entry in audit))

    def test_generate_charges_for_all_children_without_duplicates(self):
        body = {"year": 2026, "month": 9, "amount": "25", "currency": "USD"}
        first = self.client.post("/api/admin/fees/generate", headers=self.acc, json=body).json()
        second = self.client.post("/api/admin/fees/generate", headers=self.acc, json=body).json()
        self.assertEqual(first, {"created": 2, "skipped": 0})
        self.assertEqual(second, {"created": 0, "skipped": 2})
        only_kg2 = self.client.post(
            "/api/admin/fees/generate",
            headers=self.acc,
            json={**body, "currency": "SYP", "class_name": "KG2"},
        ).json()
        self.assertEqual(only_kg2["created"], 1)

    def test_new_row_with_new_child_class_and_first_payment(self):
        response = self.client.post(
            "/api/admin/fees/charges",
            headers=self.acc,
            json={
                "child_name": "Dana New",
                "class_name": "KG3",
                "year": 2026,
                "month": 10,
                "amount": "80",
                "currency": "USD",
                "payment": {"amount": "30", "paid_on": "2026-10-02", "receipt_no": "N-1", "note": "x"},
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        row = response.json()
        self.assertEqual((row["child_name"], row["class_name"]), ("Dana New", "KG3"))
        self.assertEqual((row["paid"], row["remaining"], row["status"]), ("30.00", "50.00", "partial"))
        # same child again (other currency) reuses the child instead of duplicating it
        again = self.client.post(
            "/api/admin/fees/charges",
            headers=self.acc,
            json={"child_name": "dana new", "year": 2026, "month": 10, "amount": "900000", "currency": "SYP"},
        )
        self.assertEqual(again.status_code, 201)
        self.assertEqual(again.json()["child_id"], row["child_id"])
        names = [c["display_name"] for c in self.client.get("/api/admin/fees/children", headers=self.acc).json()]
        self.assertEqual(names.count("Dana New"), 1)
        # a first payment above the amount rejects the whole row (nothing is created)
        bad = self.client.post(
            "/api/admin/fees/charges",
            headers=self.acc,
            json={"child_name": "Eli Over", "year": 2026, "month": 10, "amount": "10", "currency": "USD",
                  "payment": {"amount": "11", "paid_on": "2026-10-02"}},
        )
        self.assertEqual(bad.status_code, 422)
        names = [c["display_name"] for c in self.client.get("/api/admin/fees/children", headers=self.acc).json()]
        self.assertNotIn("Eli Over", names)
        # neither a child nor a name
        self.assertEqual(
            self.client.post("/api/admin/fees/charges", headers=self.acc,
                             json={"year": 2026, "month": 10, "amount": "1", "currency": "USD"}).status_code,
            422,
        )

    def test_child_class_can_be_set(self):
        response = self.client.patch(
            f"/api/admin/fees/children/{self.children['Amal']}",
            headers=self.acc,
            json={"class_name": "KG3"},
        )
        self.assertEqual(response.json()["class_name"], "KG3")


if __name__ == "__main__":
    unittest.main()
