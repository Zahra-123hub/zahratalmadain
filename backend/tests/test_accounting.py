import os
import sys
import tempfile
import uuid
import unittest
import unittest.mock
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import accounting, fees, main
from app.database import Base, get_session
from app import import_vorlagen
from app.import_vorlagen import parse_date, run_import
from app.models import Account, AccountingEntry, Child, Employee, FeeCharge, FeePayment, Role, SalaryLine
from app.numbers_ar import parse_amount


class NumberWordTests(unittest.TestCase):
    def amount(self, text):
        parsed = parse_amount(text)
        return parsed.value, parsed.ok

    def test_words_and_digits_become_numbers(self):
        cases = {
            "مليون ونصف": 1_500_000,
            "مليونين": 2_000_000,
            "٣ مليون": 3_000_000,
            "نصف مليون": 500_000,
            "مئتين وخمسين ألف": 250_000,
            "ثلاث مئة ألف": 300_000,
            "1,500,000": 1_500_000,
            "١٥٠٠٠٠٠ ل.س": 1_500_000,
            "٢٫٥ مليون": 2_500_000,
            "500000 + 250 ألف": 750_000,
            "مليون و٢٠٠ ألف": 1_200_000,
        }
        for text, expected in cases.items():
            value, ok = self.amount(text)
            self.assertTrue(ok, text)
            self.assertEqual(value, Decimal(expected), text)

    def test_currency_marks(self):
        self.assertEqual(parse_amount("100$").currency, "USD")
        self.assertEqual(parse_amount("75000 ل.س").currency, "SYP")
        self.assertIsNone(parse_amount("75000").currency)

    def test_unsure_amounts_are_rejected_not_guessed(self):
        for text in ("مليون و٢٠٠", "شيء غير مقروء", "100$ + 5000 ل.س"):
            self.assertFalse(parse_amount(text).ok, text)
        self.assertEqual(parse_amount("").value, None)

    def test_dates(self):
        self.assertEqual(parse_date("٠٣/٠٩", 2026)[0].isoformat(), "2026-09-03")
        self.assertEqual(parse_date("2026-09-03", 2026)[0].isoformat(), "2026-09-03")
        self.assertFalse(parse_date("31/02/2026", 2026)[1])
        self.assertEqual(parse_date("", 2026), (None, True))


class CalculationTests(unittest.TestCase):
    def test_net_pay(self):
        self.assertEqual(
            accounting.net_pay(Decimal("1000"), Decimal("200"), Decimal("150"), Decimal("50")),
            Decimal("1000.00"),
        )

    def test_salary_totals_keep_currencies_apart(self):
        rows = [
            {"currency": "SYP", "base": "100", "bonus": "10", "advance": "5", "deduction": "5", "net": "100"},
            {"currency": "SYP", "base": "200", "bonus": "0", "advance": "0", "deduction": "0", "net": "200"},
            {"currency": "USD", "base": "50", "bonus": "0", "advance": "0", "deduction": "0", "net": "50"},
        ]
        totals = accounting.salary_totals(rows)
        self.assertEqual(totals["SYP"]["net"], "300.00")
        self.assertEqual(totals["USD"]["net"], "50.00")


class ConversionTests(unittest.TestCase):
    def test_conversion_is_exact_and_rounds_half_up(self):
        from app.fees import convert, rate_text
        D = Decimal
        self.assertEqual(convert(D("1000"), "USD", "SYP", D("12500.5")), D("12500500.00"))
        self.assertEqual(convert(D("1000000"), "SYP", "USD", D("12500.5")), D("80.00"))  # 79.9968
        self.assertEqual(convert(D("2.50"), "SYP", "USD", D("3")), D("0.83"))  # 0.8333...
        # half a cent rounds UP (banker's rounding would give 0.00 here)
        self.assertEqual(convert(D("0.05"), "SYP", "USD", D("10")), D("0.01"))
        self.assertEqual(convert(D("0.15"), "SYP", "USD", D("10")), D("0.02"))
        self.assertEqual(convert(D("1.005"), "USD", "USD", D("1")), D("1.01"))
        # the same currency is only rounded, a huge sum keeps every digit
        self.assertEqual(convert(D("123456789012.34"), "SYP", "SYP", D("9")), D("123456789012.34"))
        self.assertEqual(convert(D("999999999.99"), "USD", "SYP", D("13000.123456")), D("13000123455870.00"))  # ...869.99876544
        # no floating point error: 0.1 + 0.2 style sums stay exact
        self.assertEqual(convert(D("0.10"), "USD", "SYP", D("3")) + convert(D("0.20"), "USD", "SYP", D("3")), D("0.90"))
        self.assertEqual(rate_text(D("12500.000000")), "12500")
        self.assertEqual(rate_text(D("12500.500000")), "12500.5")
        self.assertEqual(rate_text(D("0.000125")), "0.000125")


class AccountingApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SESSION_SECRET": "test-accounting-secret-long-enough",
                "ADMIN_USERNAME": "legacy-admin",
                "ADMIN_PASSWORD": "Qx9edbcb5679ea-9",
            },
        )
        self.env.start()
        self.feed = patch("app.accounting.fetch_online_rate", return_value=None)  # the tests never touch the internet
        self.feed_mock = self.feed.start()
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

        def override():
            with Session(self.engine) as session:
                yield session

        main.app.dependency_overrides[get_session] = override
        main.app.dependency_overrides[main.optional_session] = override
        self.client = TestClient(main.app)
        with Session(self.engine) as session:
            roles = {n: Role(name=n) for n in ("admin", "teacher", "parent", "accountant")}
            session.add_all(roles.values())
            for username, role in (("acc", "accountant"), ("teacher1", "teacher"), ("parent1", "parent")):
                session.add(Account(username=username, password_hash=main.PASSWORD_HASHER.hash("Qx5a6ba62b7e4b-9"), roles=[roles[role]]))
            session.add(Child(display_name="Amal", class_name="KG1"))
            session.commit()

        def token(name):
            return {"Authorization": "Bearer " + self.client.post(
                "/api/platform/auth/login", json={"username": name, "password": "Qx5a6ba62b7e4b-9"}
            ).json()["access_token"]}

        self.acc = token("acc")
        self.teacher = token("teacher1")
        self.parent = token("parent1")
        self.legacy = {"Authorization": "Bearer " + self.client.post(
            "/api/auth/login", json={"username": "legacy-admin", "password": "Qx9edbcb5679ea-9"}
        ).json()["access_token"]}

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.pop(get_session, None)
        main.app.dependency_overrides.pop(main.optional_session, None)
        self.engine.dispose()
        self.feed.stop()
        self.env.stop()

    def salary(self, name="Rima", base="1000", currency="SYP", month=10, **extra):
        return self.client.post(
            "/api/admin/accounting/salaries", headers=self.acc,
            json={"employee_name": name, "job_title": "teacher", "year": 2026, "month": month,
                  "currency": currency, "base": base, **extra},
        )

    # ---- access ----
    def test_only_accountant_and_admin_reach_accounting(self):
        paths = ["/api/admin/accounting/employees", "/api/admin/accounting/salaries",
                 "/api/admin/accounting/sheet?period_type=month&year=2026&month=10&currency=SYP",
                 "/api/admin/accounting/overview?year=2026"]
        for path in paths:
            for headers, expected in ((self.acc, 200), (self.legacy, 200), (self.teacher, 403),
                                      (self.parent, 403), ({}, 401)):
                self.assertEqual(self.client.get(path, headers=headers).status_code, expected, (path, expected))
        for method, path in (("post", "/api/admin/accounting/salaries"), ("put", "/api/admin/accounting/entries"),
                             ("post", "/api/admin/accounting/employees")):
            for headers in (self.teacher, self.parent):
                self.assertEqual(getattr(self.client, method)(path, headers=headers, json={}).status_code, 403, path)

    # ---- payroll ----
    def test_salary_net_totals_and_validation(self):
        self.assertEqual(self.salary("Rima", "1000", bonus="200", advance="150", deduction="50").json()["net"], "1000.00")
        self.salary("Dina", "500")
        self.salary("Rima", "40", currency="USD")
        listing = self.client.get("/api/admin/accounting/salaries?year=2026&month=10", headers=self.acc).json()
        self.assertEqual(listing["totals"]["SYP"]["net"], "1500.00")
        self.assertEqual(listing["totals"]["USD"]["net"], "40.00")
        self.assertEqual(self.salary("Rima", "1000").status_code, 409)  # same employee/month/currency
        self.assertEqual(self.salary("Neg", "100", advance="200").status_code, 422)  # negative net
        self.assertEqual(self.salary("Bad", "-5").status_code, 422)
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(Employee)).all()), 2)  # Rima reused; rejected rows create nobody

    # ---- corrections after the accounting review ----
    A = "/api/admin/accounting"

    def _sheet(self, **query):
        return self.client.get(self.A + "/sheet?" + "&".join(f"{k}={v}" for k, v in query.items()), headers=self.acc).json()

    def _row(self, sheet, key):
        return next(row for row in sheet["rows"] if row["key"] == key)

    def _fee(self, month=10, amount="1000", paid="400", paid_on="2026-11-02"):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": month, "amount": amount, "currency": "SYP"}).json()
        if paid:
            self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc, json={"amount": paid, "paid_on": paid_on})
        return charge

    def test_income_counts_by_payment_date_in_every_sheet(self):
        self._fee(month=10, paid="400", paid_on="2026-11-02")  # fee for October, money received on 2 November
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "registration")["income"], "0.00")
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=11, currency="SYP"), "registration")["income"], "400.00")
        self.assertEqual(self._row(self._sheet(period_type="week", year=2026, currency="SYP", week_start="2026-11-02"), "registration")["income"], "400.00")
        self.assertEqual(self._row(self._sheet(period_type="day", year=2026, currency="SYP", week_start="2026-11-02"), "registration")["income"], "400.00")
        self.assertEqual(self._row(self._sheet(period_type="day", year=2026, currency="SYP", week_start="2026-11-03"), "registration")["income"], "0.00")

    def test_payment_without_date_counts_in_the_month_of_its_fee(self):
        charge = self._fee(month=9, paid=None)
        with Session(self.engine) as session:
            session.add(FeePayment(charge_id=uuid.UUID(charge["id"]), amount=Decimal("300"), paid_on=None))
            session.commit()
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=9, currency="SYP"), "registration")["income"], "300.00")
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "registration")["income"], "0.00")
        # it can still be edited without inventing a date, but a new payment needs one
        payment_id = self.client.get("/api/admin/fees?year=2026&month=9", headers=self.acc).json()["rows"][0]["payments"][0]["id"]
        keep = self.client.patch(f"/api/admin/fees/payments/{payment_id}", headers=self.acc, json={"amount": "300", "paid_on": None, "note": "ok"})
        self.assertEqual(keep.status_code, 200)
        self.assertIsNone(keep.json()["payments"][0]["paid_on"])
        self.assertEqual(self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc, json={"amount": "10"}).status_code, 422)
        dated = self.client.patch(f"/api/admin/fees/payments/{payment_id}", headers=self.acc, json={"amount": "300", "paid_on": "2026-09-15"})
        self.assertEqual(dated.status_code, 200)
        self.assertEqual(self.client.patch(f"/api/admin/fees/payments/{payment_id}", headers=self.acc, json={"amount": "300", "paid_on": None}).status_code, 422)

    def test_salaries_count_when_paid_out_unpaid_ones_in_their_own_month(self):
        self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Rima", "salary": "500", "salary_currency": "SYP"})
        self.client.post(self.A + "/salaries/generate", headers=self.acc, json={"year": 2026, "month": 11, "currency": "SYP"})
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=11, currency="SYP"), "salaries")["expense"], "500.00")
        self.assertEqual(self._row(self._sheet(period_type="week", year=2026, currency="SYP", week_start="2026-11-02"), "salaries")["expense"], "0.00")
        line = self.client.get(self.A + "/salaries?year=2026&month=11", headers=self.acc).json()["rows"][0]
        self.client.patch(f"{self.A}/salaries/{line['id']}", headers=self.acc, json={"base": "500", "paid_on": "2026-10-30"})
        # paid out on 30 October: it is an October expense now and no longer November's
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "salaries")["expense"], "500.00")
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=11, currency="SYP"), "salaries")["expense"], "0.00")
        self.assertEqual(self._row(self._sheet(period_type="day", year=2026, currency="SYP", week_start="2026-10-30"), "salaries")["expense"], "500.00")

    def test_saving_a_note_does_not_freeze_an_automatic_amount(self):
        charge = self._fee(month=10, paid="400", paid_on="2026-10-05")
        body = {"period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "registration",
                "income": "400", "expense": "0", "note": "only a note", "manual": True}
        saved = self.client.put(self.A + "/entries", headers=self.acc, json=body).json()
        row = self._row(saved, "registration")
        self.assertFalse(row["manual"])
        self.assertEqual(row["note"], "only a note")
        self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc, json={"amount": "100", "paid_on": "2026-10-20"})
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "registration")["income"], "500.00")
        # a really different amount is a manual override
        body["income"] = "999"
        override = self._row(self.client.put(self.A + "/entries", headers=self.acc, json=body).json(), "registration")
        self.assertTrue(override["manual"])
        self.assertEqual(override["income"], "999.00")

    def test_salary_update_changes_only_what_is_sent(self):
        line = self.salary("Rima", "1000", bonus="100", paid_on="2026-10-28").json()
        sent = self.client.patch(f"{self.A}/salaries/{line['id']}", headers=self.acc, json={"paid_by": "Samir"}).json()
        self.assertEqual((sent["base"], sent["bonus"], sent["paid_on"], sent["paid_by"]), ("1000.00", "100.00", "2026-10-28", "Samir"))
        cleared = self.client.patch(f"{self.A}/salaries/{line['id']}", headers=self.acc, json={"bonus": None, "paid_on": None}).json()
        self.assertIsNone(cleared["bonus"])
        self.assertIsNone(cleared["paid_on"])
        self.assertEqual(cleared["base"], "1000.00")
        # the net check uses the stored values too
        self.assertEqual(self.client.patch(f"{self.A}/salaries/{line['id']}", headers=self.acc, json={"advance": "5000"}).status_code, 422)

    def test_names_cannot_become_blank_or_duplicate(self):
        first = self.salary("Rima", "1000").json()
        self.salary("Dina", "500")
        blank = self.client.patch(f"{self.A}/salaries/{first['id']}", headers=self.acc, json={"employee_name": "  ", "base": "1000"})
        self.assertEqual(blank.status_code, 422)
        clash = self.client.patch(f"{self.A}/salaries/{first['id']}", headers=self.acc, json={"employee_name": "dina", "base": "1000"})
        self.assertEqual(clash.status_code, 409)
        renamed = self.client.patch(f"{self.A}/salaries/{first['id']}", headers=self.acc, json={"employee_name": "Rima S.", "base": "1000"})
        self.assertEqual(renamed.json()["employee_name"], "Rima S.")
        child = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]
        self.assertEqual(self.client.patch(f"/api/admin/fees/children/{child['id']}", headers=self.acc, json={"class_name": "KG1", "display_name": ""}).status_code, 422)
        self.client.post("/api/admin/fees/charges", headers=self.acc, json={"child_name": "Bashar", "year": 2026, "month": 10, "amount": "1", "currency": "SYP"})
        self.assertEqual(self.client.patch(f"/api/admin/fees/children/{child['id']}", headers=self.acc, json={"class_name": "KG1", "display_name": "bashar"}).status_code, 409)
        self.assertEqual(self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["display_name"], "Amal")

    def test_week_and_day_sheets_take_the_year_from_their_date(self):
        entry = {"period_type": "day", "year": 2025, "week_start": "2026-03-05", "currency": "SYP", "item_key": "operating",
                 "income": "0", "expense": "100", "manual": True}  # a wrong year typed next to a 2026 date
        self.client.put(self.A + "/entries", headers=self.acc, json=entry)
        for year in (2025, 2026):
            self.assertEqual(self._row(self._sheet(period_type="day", year=year, currency="SYP", week_start="2026-03-05"), "operating")["expense"], "100.00")
        # a week across New Year is one sheet whichever day of it is opened
        week = {"period_type": "week", "year": 2026, "week_start": "2026-12-30", "currency": "SYP", "item_key": "misc",
                "income": "0", "expense": "7", "manual": True}
        self.client.put(self.A + "/entries", headers=self.acc, json=week)
        for day in ("2026-12-29", "2027-01-02"):
            self.assertEqual(self._row(self._sheet(period_type="week", year=2027, currency="SYP", week_start=day), "misc")["expense"], "7.00")

    def test_saving_a_standard_row_twice_leaves_one_row(self):
        body = {"period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "operating", "income": "0", "expense": "10", "manual": True}
        self.client.put(self.A + "/entries", headers=self.acc, json=body)
        with Session(self.engine) as session:  # simulate the duplicate a simultaneous save could leave behind
            session.add(AccountingEntry(period_type="month", year=2026, month=10, currency="SYP", item_key="operating", income=0, expense=5, manual=True))
            session.commit()
        body["expense"] = "20"
        self.client.put(self.A + "/entries", headers=self.acc, json=body)
        with Session(self.engine) as session:
            rows = session.scalars(select(AccountingEntry).where(AccountingEntry.item_key == "operating")).all()
            self.assertEqual([str(r.expense) for r in rows], ["20.00"])

    def test_week_can_start_on_another_day(self):
        import datetime
        with patch.dict(os.environ, {"ACCOUNTING_WEEK_START": "6"}):  # Sunday
            self.assertEqual(accounting.week_monday(datetime.date(2026, 11, 4)), datetime.date(2026, 11, 1))
        self.assertEqual(accounting.week_monday(datetime.date(2026, 11, 4)), datetime.date(2026, 11, 2))
        with patch.dict(os.environ, {"ACCOUNTING_WEEK_START": "nonsense"}):
            self.assertEqual(accounting.week_start_day(), 0)

    # ---- a person stays tied to what was saved for them ----
    def test_a_removed_person_who_is_saved_again_keeps_history_salary_and_account(self):
        acc = self.client.get(self.A + "/staff-accounts", headers=self.acc).json()
        teacher_account = next(a for a in acc if a["username"] == "teacher1")["id"]
        first = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Rima Saleh", "job_title": "Teacher", "salary": "500", "salary_currency": "SYP", "account_id": teacher_account}).json()
        self.salary("Rima Saleh", "500")
        self.client.delete(f"{self.A}/employees/{first['id']}", headers=self.acc)
        again = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "rima saleh", "job_title": "Head teacher"})
        self.assertEqual(again.status_code, 201)
        self.assertEqual((again.json()["id"], again.json()["salary"], again.json()["account_id"]), (first["id"], "500.00", teacher_account))
        self.assertEqual(again.json()["job_title"], "Head teacher")
        people = self.client.get(self.A + "/employees", headers=self.acc).json()
        self.assertEqual([p["name"] for p in people], ["Rima Saleh"])  # one person, not two
        rows = self.client.get(self.A + "/salaries?year=2026", headers=self.acc).json()["rows"]
        self.assertEqual([(r["employee_name"], r["job_title"]) for r in rows], [("Rima Saleh", "Head teacher")])
        # a salary row typed by name for a removed person brings the same record back, too
        self.client.delete(f"{self.A}/employees/{first['id']}", headers=self.acc)
        self.assertEqual(self.salary("RIMA SALEH", "500", month=11).status_code, 201)
        self.assertEqual(len(self.client.get(self.A + "/employees", headers=self.acc).json()), 1)
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(Employee)).all()), 1)

    def test_an_account_given_up_by_a_removed_person_can_be_linked_again(self):
        account_id = next(a for a in self.client.get(self.A + "/staff-accounts", headers=self.acc).json() if a["username"] == "teacher1")["id"]
        old = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Old Name", "account_id": account_id}).json()
        self.client.delete(f"{self.A}/employees/{old['id']}", headers=self.acc)
        new = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "New Name", "account_id": account_id})
        self.assertEqual(new.status_code, 201)
        self.assertEqual(new.json()["account_id"], account_id)
        # an active person still holds an account against everyone else
        other = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Third Person", "account_id": account_id})
        self.assertEqual(other.status_code, 409)

    def test_changing_the_saved_salary_updates_open_payroll_rows_only(self):
        person = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Rima", "salary": "500", "salary_currency": "SYP"}).json()
        for month in (9, 10, 11):
            self.client.post(self.A + "/salaries/generate", headers=self.acc, json={"year": 2026, "month": month, "currency": "SYP"})
        rows = {r["month"]: r for r in self.client.get(self.A + "/salaries?year=2026", headers=self.acc).json()["rows"]}
        self.client.patch(f"{self.A}/salaries/{rows[9]['id']}", headers=self.acc, json={"paid_on": "2026-09-28"})  # paid out
        self.client.patch(f"{self.A}/salaries/{rows[10]['id']}", headers=self.acc, json={"base": "520"})  # corrected by hand
        result = self.client.patch(f"{self.A}/employees/{person['id']}", headers=self.acc, json={"name": "Rima", "salary": "600", "salary_currency": "SYP"}).json()
        self.assertEqual(result["updated_salary_rows"], 1)
        now = {r["month"]: r["base"] for r in self.client.get(self.A + "/salaries?year=2026", headers=self.acc).json()["rows"]}
        self.assertEqual(now, {9: "500.00", 10: "520.00", 11: "600.00"})
        # a new month uses the new salary
        self.client.post(self.A + "/salaries/generate", headers=self.acc, json={"year": 2026, "month": 12, "currency": "SYP"})
        december = next(r for r in self.client.get(self.A + "/salaries?year=2026&month=12", headers=self.acc).json()["rows"])
        self.assertEqual(december["base"], "600.00")

    def test_the_first_salary_typed_for_a_person_is_remembered_with_them(self):
        self.salary("Dina", "750", month=10)
        saved = next(p for p in self.client.get(self.A + "/employees", headers=self.acc).json() if p["name"] == "Dina")
        self.assertEqual((saved["salary"], saved["salary_currency"]), ("750.00", "SYP"))
        self.client.post(self.A + "/salaries/generate", headers=self.acc, json={"year": 2026, "month": 11, "currency": "SYP"})
        self.assertEqual([r["base"] for r in self.client.get(self.A + "/salaries?year=2026&month=11", headers=self.acc).json()["rows"]], ["750.00"])
        # a later row with another amount does not overwrite what was saved for the person
        self.salary("Dina", "999", month=12)
        saved = next(p for p in self.client.get(self.A + "/employees", headers=self.acc).json() if p["name"] == "Dina")
        self.assertEqual(saved["salary"], "750.00")

    def test_an_account_created_with_a_removed_persons_name_takes_that_person_back(self):
        person = self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Hana Ali", "salary": "300"}).json()
        self.client.delete(f"{self.A}/employees/{person['id']}", headers=self.acc)
        created = self.client.post("/api/admin/platform/teacher-accounts", headers=self.legacy, json={
            "username": "hana-teacher", "role": "teacher", "full_name": "Hana Ali", "job_title": "Teacher", "password": "Qx1d3f5h7j9l-9"})
        self.assertEqual(created.status_code, 201)
        people = self.client.get(self.A + "/employees", headers=self.acc).json()
        self.assertEqual([(p["id"], p["salary"], p["account_username"]) for p in people], [(person["id"], "300.00", "hana-teacher")])

    # ---- cash balance and roll-up ----
    def _entry(self, **body):
        base = {"currency": "SYP", "income": "0", "expense": "0", "manual": True}
        return self.client.put(self.A + "/entries", headers=self.acc, json={**base, **body})

    def _cash(self):
        return self.client.get(self.A + "/cash", headers=self.acc).json()

    def test_cash_balance_is_opening_plus_income_minus_expense(self):
        import datetime
        today = datetime.date.today()
        self.assertEqual(self._cash()["SYP"]["balance"], "0.00")
        self.assertFalse(self._cash()["SYP"]["configured"])
        # opening balance at the start of this month, then income and expense in this month
        set_up = self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "SYP", "opening": "1000", "start_year": today.year, "start_month": today.month})
        self.assertEqual(set_up.status_code, 200)
        self.assertTrue(set_up.json()["configured"])
        self._entry(period_type="month", year=today.year, month=today.month, item_key="buffet", income="300")
        self._entry(period_type="month", year=today.year, month=today.month, item_key="operating", expense="450")
        usd = self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "USD", "opening": "50", "start_year": today.year, "start_month": today.month}).json()
        cash = self._cash()
        self.assertEqual((cash["SYP"]["income"], cash["SYP"]["expense"], cash["SYP"]["balance"]), ("300.00", "450.00", "850.00"))
        self.assertEqual((usd["balance"], cash["USD"]["balance"]), ("50.00", "50.00"))  # the currencies never mix
        # fee money received and a paid salary change the balance by themselves
        charge = self._fee(month=today.month, amount="1000", paid="400", paid_on=today.isoformat())
        self.assertEqual(self._cash()["SYP"]["balance"], "1250.00")
        self.client.post(self.A + "/employees", headers=self.acc, json={"name": "Rima", "salary": "200", "salary_currency": "SYP"})
        self.client.post(self.A + "/salaries/generate", headers=self.acc, json={"year": today.year, "month": today.month, "currency": "SYP"})
        self.assertEqual(self._cash()["SYP"]["balance"], "1050.00")
        # the monthly sheet shows the balance at the start and the end of the month
        sheet = self._sheet(period_type="month", year=today.year, month=today.month, currency="SYP")
        self.assertEqual(sheet["balance"], {"opening": "1000.00", "closing": "1050.00"})
        # removing the payment takes the money away again
        payment_id = self.client.get(f"/api/admin/fees?year={today.year}&month={today.month}", headers=self.acc).json()["rows"][0]["payments"][0]["id"]
        self.client.delete(f"/api/admin/fees/payments/{payment_id}", headers=self.acc)
        self.assertEqual(self._cash()["SYP"]["balance"], "650.00")

    def test_balance_carries_over_from_month_to_month(self):
        self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "SYP", "opening": "500", "start_year": 2026, "start_month": 1})
        self._entry(period_type="month", year=2026, month=1, item_key="buffet", income="200")
        self._entry(period_type="month", year=2026, month=2, item_key="operating", expense="100")
        self._entry(period_type="month", year=2026, month=3, item_key="buffet", income="50")
        months = {(m["year"], m["month"]): m for m in self.client.get(self.A + "/cash", headers=self.acc).json()["SYP"]["months"]}
        self.assertEqual((months[(2026, 1)]["opening"], months[(2026, 1)]["closing"]), ("500.00", "700.00"))
        self.assertEqual((months[(2026, 2)]["opening"], months[(2026, 2)]["closing"]), ("700.00", "600.00"))
        self.assertEqual((months[(2026, 3)]["opening"], months[(2026, 3)]["closing"]), ("600.00", "650.00"))
        march = self._sheet(period_type="month", year=2026, month=3, currency="SYP")
        self.assertEqual(march["balance"], {"opening": "600.00", "closing": "650.00"})
        # a month before the books start has no balance
        self.assertIsNone(self._sheet(period_type="month", year=2025, month=12, currency="SYP")["balance"])
        # without an opening balance nothing is claimed on the sheet
        self.client.post(self.A + "/reset", headers=self.legacy, json={"confirm": "RESET"})
        self.assertIsNone(self._sheet(period_type="month", year=2026, month=3, currency="SYP")["balance"])
        self.assertFalse(self._cash()["SYP"]["configured"])

    def test_only_accountant_and_admin_can_set_the_opening_balance(self):
        body = {"currency": "SYP", "opening": "10", "start_year": 2026, "start_month": 1}
        self.assertEqual(self.client.put(self.A + "/cash", headers=self.teacher, json=body).status_code, 403)
        self.assertEqual(self.client.put(self.A + "/cash", headers=self.parent, json=body).status_code, 403)
        self.assertEqual(self.client.put(self.A + "/cash", headers=self.acc, json={**body, "opening": "-5"}).status_code, 422)
        self.assertEqual(self.client.put(self.A + "/cash", headers=self.acc, json={**body, "start_month": 13}).status_code, 422)
        self.assertEqual(self.client.put(self.A + "/cash", headers=self.acc, json=body).status_code, 200)

    def test_days_and_weeks_add_up_into_the_month_without_double_counting(self):
        # 6 and 7 October fall in the week of Monday 5 October; 20 October is another week
        self._entry(period_type="day", year=2026, week_start="2026-10-06", item_key="operating", expense="10")
        self._entry(period_type="day", year=2026, week_start="2026-10-07", item_key="operating", expense="20")
        self._entry(period_type="day", year=2026, week_start="2026-10-20", item_key="operating", expense="5")
        month = lambda: self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "operating")
        self.assertEqual((month()["expense"], month()["rolled"]), ("35.00", True))
        self.assertEqual(self._row(self._sheet(period_type="week", year=2026, currency="SYP", week_start="2026-10-05"), "operating")["expense"], "30.00")
        # a weekly row replaces the days of that week (it is the summary of them), the other days still count
        self._entry(period_type="week", year=2026, week_start="2026-10-05", item_key="operating", expense="100")
        self.assertEqual(month()["expense"], "105.00")
        # a monthly row replaces everything below it
        self._entry(period_type="month", year=2026, month=10, item_key="operating", expense="999")
        self.assertEqual((month()["expense"], month()["rolled"]), ("999.00", False))
        # taking the monthly row away brings the roll-up back
        entry_id = month()["id"]
        self.client.delete(f"{self.A}/entries/{entry_id}", headers=self.acc)
        self.assertEqual(month()["expense"], "105.00")

    def test_custom_rows_of_the_days_appear_once_in_the_week_and_month(self):
        self._entry(period_type="day", year=2026, week_start="2026-10-06", item_key="custom", item_label="Repair", expense="40")
        self._entry(period_type="day", year=2026, week_start="2026-10-08", item_key="custom", item_label="repair", expense="10")
        for sheet in (self._sheet(period_type="week", year=2026, currency="SYP", week_start="2026-10-05"),
                      self._sheet(period_type="month", year=2026, month=10, currency="SYP")):
            rolled = [r for r in sheet["rows"] if r["key"] == "rolled"]
            self.assertEqual([(r["label"], r["expense"]) for r in rolled], [("Repair", "50.00")])
            self.assertEqual(sheet["totals"]["expense"], "50.00")

    def test_an_auto_item_is_not_counted_twice_through_the_roll_up(self):
        self._fee(month=10, paid="400", paid_on="2026-10-06")
        day = self._sheet(period_type="day", year=2026, currency="SYP", week_start="2026-10-06")
        self.assertEqual(self._row(day, "registration")["income"], "400.00")
        self.assertEqual(self._row(self._sheet(period_type="week", year=2026, currency="SYP", week_start="2026-10-05"), "registration")["income"], "400.00")
        self.assertEqual(self._row(self._sheet(period_type="month", year=2026, month=10, currency="SYP"), "registration")["income"], "400.00")

    # ---- switching the currency of a form converts what was typed ----
    def _rate(self, day, rate, headers=None):
        return self.client.put("/api/admin/accounting/rates", headers=headers or self.acc, json={"effective_date": day, "syp_per_usd": rate})

    def _convert(self, amounts, source, target, headers=None):
        return self.client.post("/api/admin/accounting/convert", headers=headers or self.acc, json={"amounts": amounts, "source": source, "target": target})

    def test_typed_amounts_are_converted_exactly_with_the_current_rate(self):
        import datetime
        today = datetime.date.today()
        self.assertIsNone(self.client.get("/api/admin/accounting/rates", headers=self.acc).json()["current"])
        self.assertEqual(self._convert(["100"], "USD", "SYP").status_code, 409)  # no rate yet: nothing is guessed
        self.assertEqual(self._rate((today - datetime.timedelta(days=30)).isoformat(), "12000").status_code, 200)
        self._rate(today.isoformat(), "13000.5")
        self._rate((today + datetime.timedelta(days=30)).isoformat(), "99999")  # a future rate is not used yet
        done = self._convert(["1000", "0.05", "2500.25"], "USD", "SYP").json()
        self.assertEqual(done["amounts"], ["13000500.00", "650.03", "32504500.13"])  # 0.05 x 13000.5 = 650.025 and 2500.25 x 13000.5 = 32504500.125: half a cent goes up
        self.assertEqual((done["rate"], done["rate_date"]), ("13000.5", today.isoformat()))
        back = self._convert(["13000500", "1", "0.01"], "SYP", "USD").json()
        self.assertEqual(back["amounts"], ["1000.00", "0.00", "0.00"])
        # the same currency only rounds; many amounts at once; limits
        self.assertEqual(self._convert(["10.005"], "SYP", "SYP").json()["amounts"], ["10.01"])
        self.assertEqual(self._convert([], "USD", "SYP").status_code, 422)
        self.assertEqual(self._convert(["-1"], "USD", "SYP").status_code, 422)
        self.assertEqual(self._convert(["5"], "EUR", "SYP").status_code, 422)
        self.assertEqual(self._convert(["1"] * 31, "USD", "SYP").status_code, 422)
        # setting a day again replaces that day's rate; the rate must be positive
        again = self._rate(today.isoformat(), "14000").json()
        self.assertEqual(again["current"]["rate"], "14000")
        self.assertEqual(self._rate(today.isoformat(), "0").status_code, 422)
        self.assertEqual(self._rate(today.isoformat(), "-3").status_code, 422)

    def test_the_rate_is_fetched_automatically_once_a_day(self):
        import datetime
        today = datetime.date.today()
        self.feed_mock.return_value = Decimal("12166.006900")
        first = self._convert(["1000000"], "SYP", "USD").json()
        self.assertEqual((first["amounts"], first["rate"], first["source"], first["stale"]), (["82.20"], "12166.0069", "auto", False))
        self.assertEqual(self._convert(["100"], "USD", "SYP").json()["amounts"], ["1216600.69"])
        self.assertEqual(self.feed_mock.call_count, 1)  # asked the internet only once for today
        stored = self.client.get("/api/admin/accounting/rates", headers=self.acc).json()
        self.assertEqual([(r["date"], r["rate"]) for r in stored["rates"]], [(today.isoformat(), "12166.0069")])
        # a rate typed for today beats the feed
        self._rate(today.isoformat(), "13000")
        self.assertEqual((self._convert(["1"], "USD", "SYP").json()["rate"], self._convert(["1"], "USD", "SYP").json()["source"]), ("13000", "manual"))
        self.assertEqual(self.feed_mock.call_count, 1)

    def test_when_the_feed_is_down_the_last_stored_rate_is_used_and_marked_old(self):
        import datetime
        today = datetime.date.today()
        self.assertEqual(self._convert(["1"], "USD", "SYP").status_code, 409)  # nothing stored, nothing online: nothing guessed
        self._rate((today - datetime.timedelta(days=3)).isoformat(), "12000")
        old = self._convert(["2"], "USD", "SYP").json()
        self.assertEqual((old["amounts"], old["stale"], old["rate_date"]), (["24000.00"], True, (today - datetime.timedelta(days=3)).isoformat()))
        self.feed_mock.return_value = Decimal("12200")  # the feed is back: today's rate is stored and used
        fresh = self._convert(["2"], "USD", "SYP").json()
        self.assertEqual((fresh["amounts"], fresh["stale"], fresh["source"]), (["24400.00"], False, "auto"))

    def test_the_feed_quote_of_the_new_pound_is_scaled_to_the_old_pound(self):
        import app.accounting as acc
        feed = unittest.mock.MagicMock()
        feed.json.return_value = {"rates": {"SYP": 121.660069}}
        self.feed.stop()  # use the real function, with a fake web reply
        try:
            with patch("app.accounting.httpx.get", return_value=feed):
                self.assertEqual(acc.fetch_online_rate(), Decimal("12166.006900"))
                with patch.dict(os.environ, {"SYP_RATE_SCALE": "1"}):
                    self.assertEqual(acc.fetch_online_rate(), Decimal("121.660069"))
                feed.json.return_value = {"rates": {"SYP": 12950.5}}  # a quote that is already in old pounds stays as it is
                self.assertEqual(acc.fetch_online_rate(), Decimal("12950.500000"))
                feed.json.return_value = {"rates": {}}
                self.assertIsNone(acc.fetch_online_rate())
            with patch("app.accounting.httpx.get", side_effect=OSError("offline")):
                self.assertIsNone(acc.fetch_online_rate())
        finally:
            self.feed_mock = self.feed.start()

    # ---- one sheet with pounds and dollars, capital and balance in every sheet ----
    def _all(self, **query):
        url = self.A + "/sheet-all?" + "&".join(f"{k}={v}" for k, v in query.items())
        return self.client.get(url, headers=self.acc).json()

    def _item(self, sheet, key, label=None):
        return next(i for i in sheet["items"] if i["key"] == key and (label is None or i["label"] == label))

    def test_a_sheet_has_a_line_per_currency_and_converts_only_when_dollars_are_involved(self):
        day = {"period_type": "day", "year": 2026, "week_start": "2026-10-06"}
        self._entry(**day, item_key="operating", expense="150000")
        pounds_only = self._all(period_type="day", year=2026, week_start="2026-10-06")
        self.assertEqual([l["currency"] for l in self._item(pounds_only, "operating")["lines"]], ["SYP"])
        self.assertIsNone(pounds_only["converted"])
        self.assertEqual(self.feed_mock.call_count, 0)  # nothing to convert: the internet is not asked
        self.feed_mock.return_value = Decimal("12166")
        self._entry(**day, item_key="operating", expense="10", currency="USD")
        self._entry(**day, item_key="custom", item_label="Repair", expense="5", currency="USD")
        sheet = self._all(period_type="day", year=2026, week_start="2026-10-06")
        self.assertEqual([(l["currency"], l["expense"]) for l in self._item(sheet, "operating")["lines"]], [("SYP", "150000.00"), ("USD", "10.00")])
        self.assertEqual([l["currency"] for l in self._item(sheet, "registration")["lines"]], ["SYP"])  # the automatic row is always there
        self.assertEqual((sheet["totals"]["SYP"]["expense"], sheet["totals"]["USD"]["expense"]), ("150000.00", "15.00"))
        self.assertEqual(sheet["converted"]["rate"], "12166")
        self.assertEqual(sheet["converted"]["SYP"]["expense"], "332490.00")  # 150000 + 15 x 12166
        self.assertEqual(sheet["converted"]["USD"]["expense"], "27.33")  # 150000 / 12166 = 12.33 + 15
        self.assertEqual(sheet["converted"]["SYP"]["net"], "-332490.00")
        repair = self._item(sheet, "custom", "Repair")
        self.assertEqual((repair["custom"], repair["lines"][0]["currency"]), (True, "USD"))

    def test_a_row_moves_to_the_other_currency_with_one_save(self):
        day = {"period_type": "day", "year": 2026, "week_start": "2026-10-06"}
        saved = self._entry(**day, item_key="operating", expense="12166").json()
        old = self._item(self._all(period_type="day", year=2026, week_start="2026-10-06"), "operating")["lines"][0]
        moved = self._entry(**day, item_key="operating", expense="1", currency="USD", replaces=old["id"])
        self.assertEqual(moved.status_code, 200)
        sheet = self._all(period_type="day", year=2026, week_start="2026-10-06")
        self.assertEqual([(l["currency"], l["expense"]) for l in self._item(sheet, "operating")["lines"]], [("USD", "1.00")])
        self.assertEqual(sheet["totals"]["SYP"]["expense"], "0.00")  # it left the pound book
        # a custom row moves the same way (a new row in the new currency, the old one removed)
        custom = self._entry(**day, item_key="custom", item_label="Repair", expense="500").json()
        row = self._item(self._all(period_type="day", year=2026, week_start="2026-10-06"), "custom", "Repair")["lines"][0]
        self._entry(**day, item_key="custom", item_label="Repair", expense="0.04", currency="USD", replaces=row["id"])
        lines = self._item(self._all(period_type="day", year=2026, week_start="2026-10-06"), "custom", "Repair")["lines"]
        self.assertEqual([(l["currency"], l["expense"]) for l in lines], [("USD", "0.04")])
        # when the other currency already has that item, the row is not moved over it
        self._entry(**day, item_key="buffet", income="100")
        self._entry(**day, item_key="buffet", income="1", currency="USD")
        pound_line = next(l for l in self._item(self._all(period_type="day", year=2026, week_start="2026-10-06"), "buffet")["lines"] if l["currency"] == "SYP")
        clash = self._entry(**day, item_key="buffet", income="1", currency="USD", replaces=pound_line["id"])
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(len(self._item(self._all(period_type="day", year=2026, week_start="2026-10-06"), "buffet")["lines"]), 2)

    def test_the_capital_runs_through_day_week_and_month(self):
        self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "SYP", "opening": "1000", "start_year": 2026, "start_month": 10})
        self._entry(period_type="day", year=2026, week_start="2026-10-01", item_key="buffet", income="200")
        self._entry(period_type="day", year=2026, week_start="2026-10-02", item_key="operating", expense="50")
        self._entry(period_type="day", year=2026, week_start="2026-10-03", item_key="buffet", income="10")
        third = self._all(period_type="day", year=2026, week_start="2026-10-03")["balance"]["SYP"]
        self.assertEqual((third["opening"], third["closing"]), ("1150.00", "1160.00"))  # 1000 + 200 - 50, then + 10
        first = self._all(period_type="day", year=2026, week_start="2026-10-01")["balance"]["SYP"]
        self.assertEqual((first["opening"], first["closing"]), ("1000.00", "1200.00"))
        month = self._all(period_type="month", year=2026, month=10)
        self.assertEqual((month["balance"]["SYP"]["opening"], month["balance"]["SYP"]["closing"]), ("1000.00", "1160.00"))
        self.assertTrue(month["capital_set"])
        # a week inside the month starts from the month's opening plus the days before it
        self._entry(period_type="day", year=2026, week_start="2026-10-06", item_key="operating", expense="100")
        week = self._all(period_type="week", year=2026, week_start="2026-10-06")["balance"]["SYP"]
        self.assertEqual((week["opening"], week["closing"]), ("1160.00", "1060.00"))
        # before the capital starts there is no balance; the dollar book has its own (empty) balance
        self.assertIsNone(self._all(period_type="month", year=2026, month=9)["balance"]["SYP"])
        self.assertEqual(month["balance"]["USD"]["closing"], "0.00")

    def test_without_capital_no_balance_is_claimed(self):
        sheet = self._all(period_type="day", year=2026, week_start="2026-10-06")
        self.assertEqual((sheet["balance"], sheet["capital_set"]), (None, False))

    def test_total_of_the_kindergarten_in_both_currencies(self):
        self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "SYP", "opening": "12166000", "start_year": 2026, "start_month": 10})
        self.assertIsNone(self._cash()["total"])  # only pounds: nothing to add up
        self.assertEqual(self.feed_mock.call_count, 0)
        self.feed_mock.return_value = Decimal("12166")
        self.client.put(self.A + "/cash", headers=self.acc, json={"currency": "USD", "opening": "100", "start_year": 2026, "start_month": 10})
        total = self._cash()["total"]
        self.assertEqual((total["SYP"]["balance"], total["USD"]["balance"], total["rate"]), ("13382600.00", "1100.00", "12166"))
        sheet = self._all(period_type="month", year=2026, month=10)
        self.assertEqual((sheet["converted"]["SYP"]["opening"], sheet["converted"]["USD"]["opening"]), ("13382600.00", "1100.00"))

    def test_only_accountant_and_admin_may_set_a_rate_or_convert(self):
        for headers in (self.teacher, self.parent):
            self.assertEqual(self._rate("2026-10-01", "13000", headers).status_code, 403)
            self.assertEqual(self._convert(["1"], "USD", "SYP", headers).status_code, 403)
            self.assertEqual(self.client.get("/api/admin/accounting/rates", headers=headers).status_code, 403)

    # ---- sheets ----
    def test_monthly_sheet_fills_registration_and_salaries_automatically(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "1500000", "currency": "SYP"}).json()
        self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc,
                         json={"amount": "600000", "paid_on": "2026-10-04", "receipt_no": "S-1"})
        self.salary("Rima", "1000000", bonus="100000", advance="50000")
        url = "/api/admin/accounting/sheet?period_type=month&year=2026&month=10&currency=SYP"
        rows = {r["key"]: r for r in self.client.get(url, headers=self.acc).json()["rows"]}
        self.assertEqual(rows["registration"]["income"], "600000.00")
        self.assertEqual(rows["salaries"]["expense"], "1050000.00")
        self.assertEqual(len(rows), 9)  # six original items plus buffet, transport and advertising
        self.assertIn("buffet", rows)
        self.assertIn("transport", rows)
        sheet = self.client.get(url, headers=self.acc).json()
        self.assertEqual(sheet["totals"], {"income": "600000.00", "expense": "1050000.00", "net": "-450000.00"})
        # the other currency is untouched
        usd = self.client.get(url.replace("SYP", "USD"), headers=self.acc).json()
        self.assertEqual(usd["totals"]["income"], "0.00")

        # manual override beats the automatic value; deleting the row restores it
        saved = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "registration",
            "details": "تعديل يدوي", "income": "700000", "manual": True})
        reg = next(r for r in saved.json()["rows"] if r["key"] == "registration")
        self.assertEqual((reg["income"], reg["manual"], reg["auto_income"]), ("700000.00", True, "600000.00"))
        reset = self.client.delete(f"/api/admin/accounting/entries/{reg['id']}", headers=self.acc).json()
        self.assertEqual(next(r for r in reset["rows"] if r["key"] == "registration")["income"], "600000.00")

        # other items and custom rows
        self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "operating",
            "expense": "250000"})
        custom = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "custom",
            "item_label": "بند إضافي", "expense": "10000"}).json()
        self.assertEqual(custom["totals"]["expense"], "1310000.00")

    def test_weekly_sheet_uses_payment_dates(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "100", "currency": "USD"}).json()
        for day, amount in (("2026-10-05", "30"), ("2026-10-14", "20")):  # Monday week of the 5th vs next week
            self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc,
                             json={"amount": amount, "paid_on": day})
        url = "/api/admin/accounting/sheet?period_type=week&year=2026&currency=USD&week_start="
        first = self.client.get(url + "2026-10-07", headers=self.acc).json()  # a Wednesday -> week of Mon 5th
        self.assertEqual(first["start"], "2026-10-05")
        self.assertEqual(next(r for r in first["rows"] if r["key"] == "registration")["income"], "30.00")
        second = self.client.get(url + "2026-10-12", headers=self.acc).json()
        self.assertEqual(next(r for r in second["rows"] if r["key"] == "registration")["income"], "20.00")

    def test_daily_sheet_uses_that_days_payments_and_salaries(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "1000", "currency": "SYP"}).json()
        for day, amount in (("2026-10-05", "300"), ("2026-10-06", "200")):
            self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc,
                             json={"amount": amount, "paid_on": day})
        self.salary("Rima", "5000", paid_on="2026-10-06")
        url = "/api/admin/accounting/sheet?period_type=day&year=2026&currency=SYP&week_start="
        first = self.client.get(url + "2026-10-05", headers=self.acc).json()
        self.assertEqual((first["start"], first["end"]), ("2026-10-05", "2026-10-05"))
        rows = {r["key"]: r for r in first["rows"]}
        self.assertEqual((rows["registration"]["income"], rows["salaries"]["expense"]), ("300.00", "0.00"))
        second = {r["key"]: r for r in self.client.get(url + "2026-10-06", headers=self.acc).json()["rows"]}
        self.assertEqual((second["registration"]["income"], second["salaries"]["expense"]), ("200.00", "5000.00"))
        # rows saved for one day do not leak into another day (the week sheet adds its days up, see the roll-up tests)
        saved = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "day", "year": 2026, "week_start": "2026-10-05", "currency": "SYP",
            "item_key": "operating", "expense": "75", "details": "x"}).json()
        self.assertEqual(saved["totals"]["expense"], "75.00")
        other = self.client.get(url + "2026-10-06", headers=self.acc).json()
        self.assertEqual(other["totals"]["expense"], "5000.00")
        week = self.client.get("/api/admin/accounting/sheet?period_type=week&year=2026&currency=SYP&week_start=2026-10-05", headers=self.acc).json()
        self.assertEqual(next(r for r in week["rows"] if r["key"] == "operating")["expense"], "75.00")  # rolled up from the day

    def test_buffet_and_transport_can_be_income_or_expense(self):
        base = {"period_type": "month", "year": 2026, "month": 10, "currency": "SYP"}
        self.client.put("/api/admin/accounting/entries", headers=self.acc, json={**base, "item_key": "buffet", "expense": "40000"})
        sheet = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={**base, "item_key": "transport", "income": "90000"}).json()
        rows = {r["key"]: r for r in sheet["rows"]}
        self.assertEqual((rows["buffet"]["kind"], rows["buffet"]["expense"], rows["buffet"]["choice"]), ("expense", "40000.00", True))
        self.assertEqual((rows["transport"]["kind"], rows["transport"]["income"]), ("income", "90000.00"))
        self.assertEqual(sheet["totals"], {"income": "90000.00", "expense": "40000.00", "net": "50000.00"})

    def test_it_is_recorded_who_paid_who_spent_and_who_entered_it(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "1000", "currency": "SYP"}).json()
        paid = self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc,
                                json={"amount": "400", "paid_on": "2026-10-05", "payer_name": "الأب أحمد"}).json()
        self.assertEqual(paid["payers"], ["الأب أحمد"])
        self.assertEqual((paid["payments"][0]["payer_name"], paid["payments"][0]["created_by"]), ("الأب أحمد", "acc"))
        edited = self.client.patch(f"/api/admin/fees/payments/{paid['payments'][0]['id']}", headers=self.acc,
                                   json={"amount": "400", "paid_on": "2026-10-05", "payer_name": "الأم سلمى"}).json()
        self.assertEqual(edited["payers"], ["الأم سلمى"])

        sheet = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "buffet",
            "expense": "5000", "person": "أم محمد"}).json()
        buffet = next(r for r in sheet["rows"] if r["key"] == "buffet")
        self.assertEqual((buffet["person"], buffet["entered_by"]), ("أم محمد", "acc"))

        line = self.salary("Rima", "1000", paid_by="الأستاذ كريم").json()
        self.assertEqual((line["paid_by"], line["recorded_by"]), ("الأستاذ كريم", "acc"))

    def test_saved_names_are_offered_again_and_staff_can_be_managed(self):
        created = self.client.post("/api/admin/accounting/employees", headers=self.acc,
                                   json={"name": "Rima Saleh", "job_title": "معلمة"}).json()
        self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "buffet",
            "expense": "10", "person": "أم محمد"})
        self.salary("Lana", "100", paid_by="الأستاذ كريم")
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "100", "currency": "SYP"}).json()
        self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc,
                         json={"amount": "10", "paid_on": "2026-10-05", "payer_name": "الأب أحمد"})
        names = self.client.get("/api/admin/accounting/names", headers=self.acc).json()
        self.assertEqual(sorted(names["staff"]), ["Lana", "Rima Saleh"])
        self.assertIn("أم محمد", names["persons"])
        self.assertIn("الأستاذ كريم", names["persons"])
        self.assertIn("Rima Saleh", names["persons"])
        self.assertEqual(names["payers"], ["الأب أحمد"])
        # rename / remove a saved person; old salary rows keep the name
        renamed = self.client.patch(f"/api/admin/accounting/employees/{created['id']}", headers=self.acc,
                                    json={"name": "Rima S.", "job_title": "مديرة"})
        self.assertEqual(renamed.json()["name"], "Rima S.")
        self.assertEqual(self.client.patch(f"/api/admin/accounting/employees/{created['id']}", headers=self.acc,
                                           json={"name": "lana", "job_title": ""}).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/admin/accounting/employees/{created['id']}", headers=self.acc).status_code, 204)
        self.assertNotIn("Rima S.", self.client.get("/api/admin/accounting/names", headers=self.acc).json()["staff"])
        self.assertEqual(self.client.get("/api/admin/accounting/names", headers=self.teacher).status_code, 403)

    def test_saved_names_depend_on_the_accounts(self):
        admin = self.legacy
        created = self.client.post("/api/admin/platform/teacher-accounts", headers=admin, json={
            "role": "teacher", "username": "rima.s", "password": "Qx7f3a9c1d2e44-9", "full_name": "ريما صالح", "job_title": "معلمة"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual((created.json()["full_name"], created.json()["job_title"]), ("ريما صالح", "معلمة"))
        staff = self.client.get("/api/admin/accounting/employees", headers=self.acc).json()
        person = next(e for e in staff if e["name"] == "ريما صالح")
        self.assertEqual(person["account_username"], "rima.s")
        accounts = {a["username"]: a for a in self.client.get("/api/admin/platform/accounts", headers=admin).json()}
        self.assertEqual(accounts["rima.s"]["full_name"], "ريما صالح")

        # renaming through the account renames the same person (no duplicate)
        account_id = created.json()["id"]
        self.client.patch(f"/api/admin/platform/accounts/{account_id}", headers=admin, json={"full_name": "ريما أحمد"})
        staff = self.client.get("/api/admin/accounting/employees", headers=self.acc).json()
        self.assertEqual([e["name"] for e in staff if e["account_id"] == account_id], ["ريما أحمد"])
        self.assertEqual(len(staff), 1)

        # a salary row uses the person tied to the account
        row = self.salary("ريما أحمد", "1000").json()
        self.assertEqual(row["employee_id"], person["id"])

        # tying a saved person to an account; an account has only one person
        loose = self.client.post("/api/admin/accounting/employees", headers=self.acc, json={"name": "Dina Kareem", "job_title": "محاسبة"}).json()
        options = {a["username"]: a for a in self.client.get("/api/admin/accounting/staff-accounts", headers=self.acc).json()}
        self.assertEqual(options["rima.s"]["linked_to"], "ريما أحمد")
        self.assertEqual(options["acc"]["linked_to"], "")
        conflict = self.client.patch(f"/api/admin/accounting/employees/{loose['id']}", headers=self.acc,
                                     json={"name": "Dina Kareem", "account_id": account_id})
        self.assertEqual(conflict.status_code, 409)
        linked = self.client.patch(f"/api/admin/accounting/employees/{loose['id']}", headers=self.acc,
                                   json={"name": "Dina Kareem", "account_id": options["acc"]["id"]})
        self.assertEqual(linked.json()["account_username"], "acc")
        unlinked = self.client.patch(f"/api/admin/accounting/employees/{loose['id']}", headers=self.acc,
                                     json={"name": "Dina Kareem", "account_id": None})
        self.assertEqual(unlinked.json()["account_id"], "")
        # parents' accounts cannot be tied to staff
        parent_tie = self.client.patch(f"/api/admin/accounting/employees/{loose['id']}", headers=self.acc,
                                       json={"name": "Dina Kareem", "account_id": str(uuid.uuid4())})
        self.assertEqual(parent_tie.status_code, 404)
        self.assertEqual(self.client.get("/api/admin/accounting/staff-accounts", headers=self.teacher).status_code, 403)

    def test_advertising_has_its_own_line_for_income_and_expense(self):
        base = {"period_type": "day", "year": 2026, "week_start": "2026-10-27", "currency": "SYP"}
        self.client.put("/api/admin/accounting/entries", headers=self.acc, json={**base, "item_key": "advertising", "expense": "75000", "person": "مطبعة النور", "details": "لافتات"})
        sheet = self.client.put("/api/admin/accounting/entries", headers=self.acc, json={**base, "item_key": "advertising", "income": "20000", "expense": "0"}).json()
        row = next(r for r in sheet["rows"] if r["key"] == "advertising")
        self.assertEqual((row["label"], row["choice"], row["kind"], row["income"]), ("الإعلانات والدعاية", True, "income", "20000.00"))

    def test_saved_salary_prefills_payroll_and_generates_rows(self):
        a = self.client.post("/api/admin/accounting/employees", headers=self.acc,
                             json={"name": "Rima", "job_title": "معلمة", "salary": "1500000"}).json()
        b = self.client.post("/api/admin/accounting/employees", headers=self.acc,
                             json={"name": "Dina", "salary": "120", "salary_currency": "USD"}).json()
        self.client.post("/api/admin/accounting/employees", headers=self.acc, json={"name": "NoSalary"})
        self.assertEqual((a["salary"], a["salary_currency"]), ("1500000.00", "SYP"))
        listing = {e["name"]: e for e in self.client.get("/api/admin/accounting/employees", headers=self.acc).json()}
        self.assertEqual((listing["Dina"]["salary"], listing["Dina"]["salary_currency"]), ("120.00", "USD"))
        self.assertIsNone(listing["NoSalary"]["salary"])
        # one click creates the month's rows for everyone with a saved salary in that currency
        first = self.client.post("/api/admin/accounting/salaries/generate", headers=self.acc, json={"year": 2026, "month": 10, "currency": "SYP"})
        self.assertEqual(first.json(), {"created": 1, "skipped": 0})
        again = self.client.post("/api/admin/accounting/salaries/generate", headers=self.acc, json={"year": 2026, "month": 10, "currency": "SYP"})
        self.assertEqual(again.json(), {"created": 0, "skipped": 1})
        rows = self.client.get("/api/admin/accounting/salaries?year=2026&month=10", headers=self.acc).json()["rows"]
        self.assertEqual([(r["employee_name"], r["base"], r["net"]) for r in rows], [("Rima", "1500000.00", "1500000.00")])
        # changing the saved salary does not touch rows that already exist; clearing it is possible
        updated = self.client.patch(f"/api/admin/accounting/employees/{a['id']}", headers=self.acc,
                                    json={"name": "Rima", "job_title": "معلمة", "salary": None})
        self.assertIsNone(updated.json()["salary"])
        self.assertEqual(len(self.client.get("/api/admin/accounting/salaries?year=2026&month=10", headers=self.acc).json()["rows"]), 1)
        self.assertEqual(self.client.post("/api/admin/accounting/salaries/generate", headers=self.teacher, json={"year": 2026, "month": 10}).status_code, 403)
        self.assertTrue(b["id"])

    def test_admin_can_reset_all_financial_data_to_zero(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        charge = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "1000", "currency": "SYP"}).json()
        self.client.post(f"/api/admin/fees/charges/{charge['id']}/payments", headers=self.acc, json={"amount": "400", "paid_on": "2026-10-05"})
        self.salary("Rima", "5000")
        self.client.put("/api/admin/accounting/entries", headers=self.acc, json={
            "period_type": "month", "year": 2026, "month": 10, "currency": "SYP", "item_key": "operating", "expense": "75"})
        url = "/api/admin/accounting/reset"
        self.assertEqual(self.client.post(url, headers=self.acc, json={"confirm": "RESET"}).status_code, 401)  # accountants cannot
        self.assertEqual(self.client.post(url, headers=self.legacy, json={"confirm": "yes"}).status_code, 422)  # needs the word
        done = self.client.post(url, headers=self.legacy, json={"confirm": "RESET"}).json()
        self.assertEqual(done, {"payments": 1, "fees": 1, "salaries": 1, "sheet_rows": 1, "cash": 0})
        overview = self.client.get("/api/admin/accounting/overview?year=2026", headers=self.acc).json()
        self.assertEqual(overview["SYP"]["classes"], {})
        self.assertTrue(all(m["income"] == "0.00" and m["expense"] == "0.00" for m in overview["SYP"]["series"]))
        # names stay: the children and staff are still there
        self.assertEqual(len(self.client.get("/api/admin/fees/children", headers=self.acc).json()), 1)

    def test_syrian_pound_is_the_main_currency(self):
        self.assertEqual(fees.CURRENCIES[0], "SYP")
        overview = self.client.get("/api/admin/accounting/overview?year=2026", headers=self.acc).json()
        self.assertEqual([k for k in overview if k in ("SYP", "USD")], ["SYP", "USD"])

    def test_overview_per_class_and_chart_series(self):
        children = {c["display_name"]: c["id"] for c in self.client.get("/api/admin/fees/children", headers=self.acc).json()}
        new = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_name": "Bashar", "class_name": "KG1", "year": 2026, "month": 10, "amount": "100", "currency": "USD"}).json()
        self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": children["Amal"], "year": 2026, "month": 10, "amount": "100", "currency": "USD",
            "payment": {"amount": "100", "paid_on": "2026-10-02"}})
        data = self.client.get("/api/admin/accounting/overview?year=2026", headers=self.acc).json()
        cell = data["USD"]["classes"]["KG1"][0]
        self.assertEqual((cell["required"], cell["paid"], cell["remaining"], cell["children_open"]),
                         ("200.00", "100.00", "100.00", 1))
        self.assertEqual(data["USD"]["children_open"], 1)
        self.assertEqual(len(data["USD"]["series"]), 12)
        self.assertEqual(data["USD"]["series"][9]["income"], "100.00")
        self.assertEqual(data["SYP"]["classes"], {})
        self.assertTrue(new["id"])

    def test_zero_amount_row_is_review_not_paid(self):
        child_id = self.client.get("/api/admin/fees/children", headers=self.acc).json()[0]["id"]
        row = self.client.post("/api/admin/fees/charges", headers=self.acc, json={
            "child_id": child_id, "year": 2026, "month": 10, "amount": "0", "currency": "SYP"}).json()
        self.assertEqual((row["amount"], row["paid"], row["remaining"], row["status"]), ("0.00", "0.00", "0.00", "review"))
        listing = self.client.get("/api/admin/fees?status=review", headers=self.acc).json()["rows"]
        self.assertEqual(len(listing), 1)
        self.assertEqual(self.client.get("/api/admin/fees?status=paid", headers=self.acc).json()["rows"], [])

    def test_correcting_an_imported_salary_row_keeps_empty_fields_empty(self):
        with Session(self.engine) as session:
            employee = Employee(name="")
            session.add(employee)
            session.flush()
            line = SalaryLine(employee_id=employee.id, year=2026, month=9, currency="SYP", needs_review=True,
                              raw_text="x", source="g.csv#1")
            session.add(line)
            session.commit()
            line_id = str(line.id)
        rows = self.client.get("/api/admin/accounting/salaries?needs_review=true", headers=self.acc).json()["rows"]
        self.assertEqual((rows[0]["base"], rows[0]["net"]), (None, None))
        fixed = self.client.patch(f"/api/admin/accounting/salaries/{line_id}", headers=self.acc,
                                  json={"employee_name": "Rima", "base": "1000", "bonus": None, "advance": None, "deduction": None})
        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual((fixed.json()["employee_name"], fixed.json()["base"], fixed.json()["bonus"], fixed.json()["net"]),
                         ("Rima", "1000.00", None, "1000.00"))
        self.assertTrue(fixed.json()["needs_review"])  # stays flagged until a human confirms
        confirmed = self.client.post(f"/api/admin/accounting/salaries/{line_id}/reviewed", headers=self.acc).json()
        self.assertFalse(confirmed["needs_review"])

    def test_needs_review_can_be_cleared(self):
        with Session(self.engine) as session:
            child = session.scalar(select(Child))
            charge = FeeCharge(child_id=child.id, year=2026, month=9, currency="SYP", amount=Decimal("5"),
                               needs_review=True, raw_text="x", source="a.jpg#1")
            session.add(charge)
            session.commit()
            charge_id = str(charge.id)
        flagged = self.client.get("/api/admin/fees?needs_review=true", headers=self.acc).json()["rows"]
        self.assertEqual([r["needs_review"] for r in flagged], [True])
        cleared = self.client.post(f"/api/admin/fees/charges/{charge_id}/reviewed", headers=self.acc).json()
        self.assertFalse(cleared["needs_review"])


FEES_HEADER = "م,اسم الطفل,الصف/الشعبة,الرسم/القسط المطلوب,المبلغ المدفوع,المتبقي,تاريخ الدفع,رقم الإيصال,ملاحظات,الشهر,السنة"
SALARY_HEADER = "م,اسم الموظف/المدرسة,المسمى الوظيفي,الراتب الأساسي,المكافآت/الإضافي,السلف,الخصومات,الصافي المستحق,تاريخ الاستلام,الشهر,السنة"


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.dir = tempfile.TemporaryDirectory()
        self.fees_csv = Path(self.dir.name) / "beitraege.csv"
        self.salaries_csv = Path(self.dir.name) / "gehaelter.csv"

    def tearDown(self):
        self.dir.cleanup()
        self.engine.dispose()

    def write(self, path, header, *rows):
        path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8-sig")

    def run_fees(self, session):
        return run_import(session, self.fees_csv, None)

    def test_excel_files_with_semicolons_tabs_or_utf16_are_read(self):
        row = ["1", "Amal", "KG1", "مليون", "500000", "500000", "03/09", "R1", "", "9", "2026"]
        for name, delimiter, encoding in (("semi.csv", ";", "utf-8-sig"), ("tab.csv", "\t", "utf-8-sig"), ("utf16.csv", "\t", "utf-16")):
            path = Path(self.dir.name) / name
            header = FEES_HEADER.split(",")
            path.write_text(delimiter.join(header) + "\n" + delimiter.join(row) + "\n", encoding=encoding)
            rows, ignored = import_vorlagen.read_csv(path, import_vorlagen.FEE_HEADERS)
            self.assertEqual(len(rows), 1, name)
            self.assertEqual((rows[0]["name"], rows[0]["required"], rows[0]["paid"]), ("Amal", "مليون", "500000"), name)
            self.assertEqual(ignored, [], name)

    def test_file_in_the_windows_code_page_is_refused_with_a_clear_message(self):
        path = Path(self.dir.name) / "ansi.csv"
        # an ANSI export leaves bytes that are not valid UTF-8
        path.write_bytes(FEES_HEADER.encode("utf-8") + "\n1,Amal \xe9,KG1,100\n".encode("latin-1"))
        with self.assertRaises(ValueError) as caught:
            import_vorlagen.read_csv(path, import_vorlagen.FEE_HEADERS)
        self.assertIn("UTF-8", str(caught.exception))
        with Session(self.engine) as session:
            with self.assertRaises(ValueError):
                run_import(session, path, None)
            self.assertEqual(session.scalar(select(func.count()).select_from(FeeCharge)), 0)

    def test_values_are_stored_as_read_and_empty_stays_empty(self):
        self.write(
            self.fees_csv, FEES_HEADER,
            "1,Amal,KG1,مليون ونصف,500000 + 250 ألف,750000,٠٣/٠٩,R1,,9,2026",      # adds up
            "2,Bashar,KG2,مليونين,٣ مليون,,05/09,R2,,9,2026",                        # paid > required
            "3,,KG1,,,,,,,9,2026",                                                   # nothing readable
            "4,Carla,KG3,0,0,0,,,,9,2026",                                           # 0 / 0 / 0
            "5,Dana,KG1,مليون,,,,,ملاحظة,9,2026",                                    # nothing paid yet
            "6,Eli,KG2,100$,,,,,,9,2026",                                            # dollar mark on a SYP sheet
            "7,Fadi,KG1,مليون,مليون,800000,١٠/٠٩,R7,,9,2026",                        # open column does not add up
        )
        with Session(self.engine) as session:
            report, text = self.run_fees(session)
            session.commit()
            charges = {c.source: c for c in session.scalars(select(FeeCharge))}
            children = {c.id: c for c in session.scalars(select(Child))}
            by = lambda n: charges[f"beitraege.csv#{n}"]

            first = by(1)
            self.assertEqual((first.amount, first.currency, first.needs_review), (Decimal("1500000.00"), "SYP", False))
            self.assertEqual(sum(p.amount for p in first.payments), Decimal("750000.00"))
            self.assertEqual(first.payments[0].paid_on.isoformat(), "2026-09-03")
            self.assertEqual(fees.status_of(first.amount, fees.paid_amount(first), first.needs_review), "partial")

            over = by(2)  # stored exactly as read, but flagged
            self.assertEqual(sum(p.amount for p in over.payments), Decimal("3000000.00"))
            self.assertTrue(over.needs_review)

            blank = by(3)  # unreadable: EMPTY values, raw text kept, never 0 or an invented name
            self.assertIsNone(blank.amount)
            self.assertEqual(children[blank.child_id].display_name, "")
            self.assertTrue(blank.needs_review)
            self.assertIn("KG1", blank.raw_text)

            zero = by(4)
            self.assertTrue(zero.needs_review)
            self.assertEqual(fees.status_of(zero.amount, fees.paid_amount(zero), zero.needs_review), "review")

            unpaid = by(5)
            self.assertFalse(unpaid.needs_review)
            self.assertEqual(unpaid.note, "ملاحظة")
            self.assertEqual(len(unpaid.payments), 0)

            self.assertEqual((by(6).currency, by(6).needs_review), ("USD", True))
            self.assertTrue(by(7).needs_review)  # 1,000,000 - 1,000,000 != 800,000

            fees_stats = report.stats["fees"]
            self.assertEqual((fees_stats["rows"], fees_stats["imported"]), (7, 7))
            self.assertIn("needs_review", text)

    def test_no_placeholders_after_import(self):
        self.write(self.fees_csv, FEES_HEADER, "1,,,,,,,,,9,2026", "2,,,غير واضح,,,,,,9,2026", "3,Amal,KG1,مليون,,,,,,9,2026")
        self.write(self.salaries_csv, SALARY_HEADER, "1,,,,,,,,,9,2026", "2,Rima,معلمة,,,,,,,9,2026")
        with Session(self.engine) as session:
            run_import(session, self.fees_csv, self.salaries_csv)
            session.commit()
            names = [c.display_name for c in session.scalars(select(Child))]
            self.assertEqual(sorted(names), ["", "", "Amal"])  # unreadable names stay empty, nothing invented
            for text in names + [e.name for e in session.scalars(select(Employee))]:
                for marker in ("تجريبي", "غير مقروء", "demo", "DEMO", "placeholder"):
                    self.assertNotIn(marker, text)
            charges = session.scalars(select(FeeCharge)).all()
            self.assertEqual(sorted(str(c.amount) for c in charges if c.amount is not None), ["1000000.00"])
            self.assertEqual(len([c for c in charges if c.amount is None]), 2)  # empty, not 0
            lines = session.scalars(select(SalaryLine)).unique().all()
            for line in lines:
                self.assertIsNone(line.base)
                self.assertIsNone(line.bonus)
                self.assertTrue(line.needs_review)

    def test_import_is_idempotent(self):
        self.write(self.fees_csv, FEES_HEADER, "1,Amal,KG1,مليون,500000,500000,01/09,R1,,9,2026", "2,,,,,,,,,9,2026")
        self.write(self.salaries_csv, SALARY_HEADER, "1,Rima,معلمة,مليون,٢٠٠ ألف,,,1200000,28/09,9,2026")
        with Session(self.engine) as session:
            first, _ = run_import(session, self.fees_csv, self.salaries_csv)
            session.commit()
            counts = (session.scalar(select(func.count()).select_from(Child)), session.scalar(select(func.count()).select_from(FeeCharge)),
                      session.scalar(select(func.count()).select_from(FeePayment)), session.scalar(select(func.count()).select_from(Employee)),
                      session.scalar(select(func.count()).select_from(SalaryLine)))
            again, text = run_import(session, self.fees_csv, self.salaries_csv)
            session.commit()
            self.assertEqual(again.stats["fees"]["imported"], 0)
            self.assertEqual(again.stats["fees"]["skipped"], 2)
            self.assertEqual(again.stats["salaries"]["skipped"], 1)
            after = (session.scalar(select(func.count()).select_from(Child)), session.scalar(select(func.count()).select_from(FeeCharge)),
                     session.scalar(select(func.count()).select_from(FeePayment)), session.scalar(select(func.count()).select_from(Employee)),
                     session.scalar(select(func.count()).select_from(SalaryLine)))
            self.assertEqual(counts, after)
            self.assertEqual(counts, (2, 2, 1, 1, 1))
            self.assertIn("الإجمالي SYP", text)  # the report is the same after a repeat

    def test_salary_rules(self):
        self.write(
            self.salaries_csv, SALARY_HEADER,
            "1,Rima,معلمة,مليون,٢٠٠ ألف,100000,,1100000,28/09,9,2026",   # adds up (empty deduction stays empty)
            "2,Dina,مساعدة,مليون,,,50000,900000,,9,2026",                # written net is wrong
            "3,Lana,معلمة,مليون و٢٠٠,,,,,,9,2026",                        # ambiguous words: not guessed
            "4,Maya,معلمة,,,,,,,9,2026",                                  # no base salary
        )
        with Session(self.engine) as session:
            report, text = run_import(session, None, self.salaries_csv)
            session.commit()
            lines = {l.source: l for l in session.scalars(select(SalaryLine)).unique()}
            first = lines["gehaelter.csv#1"]
            self.assertEqual((first.base, first.bonus, first.advance, first.deduction), (Decimal("1000000.00"), Decimal("200000.00"), Decimal("100000.00"), None))
            self.assertFalse(first.needs_review)
            self.assertEqual(accounting.net_pay(first.base, first.bonus, first.advance, first.deduction), Decimal("1100000.00"))
            self.assertTrue(lines["gehaelter.csv#2"].needs_review)
            self.assertIsNone(lines["gehaelter.csv#3"].base)
            self.assertTrue(lines["gehaelter.csv#3"].needs_review)
            self.assertIsNone(accounting.net_pay(None, None, None, None))
            self.assertTrue(lines["gehaelter.csv#4"].needs_review)

    def test_rows_without_a_period_are_rejected_not_guessed(self):
        self.write(self.fees_csv, "م,اسم الطفل,الرسم/القسط المطلوب", "1,Amal,مليون")
        with Session(self.engine) as session:
            report, text = run_import(session, self.fees_csv, None)
            self.assertEqual(report.stats["fees"]["rejected"], 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(FeeCharge)), 0)
            report, _ = run_import(session, self.fees_csv, None, year=2026, month=9)  # period given explicitly
            self.assertEqual(report.stats["fees"]["imported"], 1)

    def test_import_aborts_when_csv_files_are_missing(self):
        argv = ["import_vorlagen", "--fees", str(Path(self.dir.name) / "fehlt.csv"), "--salaries", str(self.salaries_csv)]
        with unittest.mock.patch.object(sys, "argv", argv), unittest.mock.patch("builtins.print") as shown:
            self.assertEqual(import_vorlagen.main(), 2)
        self.assertIn("fehlt.csv", shown.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
