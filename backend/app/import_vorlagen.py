"""Import of the paper tables from CSV files (fees and payroll).

    python -m app.import_vorlagen                      # docs/vorlagen/beitraege.csv + gehaelter.csv
    python -m app.import_vorlagen --dry-run            # read and report, write nothing
    python -m app.import_vorlagen --year 2026 --month 9 --only fees

Rules (nothing is ever invented):
  * Only values that stand in the CSV are stored. An empty or unreadable cell stays EMPTY
    (NULL, never 0 and never a made-up name, class, amount or date).
  * A row with an empty/unreadable field, an amount of 0, a currency mark that differs from the
    sheet, an inconsistent "open" or "net" column, or a duplicate receipt number is stored with
    needs_review = true and the raw row text. It is shown as "يحتاج مراجعة", never as "مدفوع".
  * A row without a month/year (neither in the CSV nor given with --year/--month) cannot be placed
    in a period and is rejected and reported, not guessed.
  * Re-running the import is safe: rows are identified by source + row number.
  * Missing CSV files abort the import; no data is generated.

CSV columns (UTF-8, header row as on the paper table; optional columns in brackets):
  fees:      م, اسم الطفل, الصف/الشعبة, الرسم/القسط المطلوب, المبلغ المدفوع, المتبقي,
             تاريخ الدفع, رقم الإيصال, ملاحظات   [الشهر, السنة, العملة, المصدر]
  salaries:  م, اسم الموظف/المدرسة, المسمى الوظيفي, الراتب الأساسي, المكافآت/الإضافي, السلف,
             الخصومات, الصافي المستحق, تاريخ الاستلام   [الشهر, السنة, العملة, المصدر]
Amounts may be digits (Arabic or Western), words ("مليون ونصف", "مليونين", "٣ مليون") or sums
("500000 + 250 ألف"). Currency is SYP unless a cell says otherwise ($, دولار).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.fees import money, paid_amount, remaining_amount
from app.models import Child, Employee, FeeCharge, FeePayment, SalaryLine
from app.numbers_ar import DIGITS, normalize, parse_amount

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEES = REPO_ROOT / "docs" / "vorlagen" / "beitraege.csv"
DEFAULT_SALARIES = REPO_ROOT / "docs" / "vorlagen" / "gehaelter.csv"
CURRENCIES = ("USD", "SYP")

# normalised header text -> field name
FEE_HEADERS = {
    "م": "row", "اسمالطفل": "name", "الاسم": "name", "الصف/الشعبه": "class", "الصف": "class",
    "الرسم/القسطالمطلوب": "required", "الرسمالمطلوب": "required", "القسطالمطلوب": "required", "المطلوب": "required",
    "المبلغالمدفوع": "paid", "المدفوع": "paid", "المتبقي": "open", "المتبقي(انوجد)": "open",
    "تاريخالدفع": "date", "رقمالايصال": "receipt", "ملاحظات": "note",
    "الدافع": "payer", "اسمالدافع": "payer",
}
SALARY_HEADERS = {
    "م": "row", "اسمالموظف/المدرسه": "name", "اسمالموظف": "name", "الاسم": "name",
    "المسمىالوظيفي": "job", "الراتبالاساسي": "base", "المكافات/الاضافي": "bonus", "المكافات": "bonus",
    "السلف": "advance", "الخصومات": "deduction", "الصافيالمستحق": "net", "تاريخالاستلام": "date",
    "صرفه": "paid_by", "منصرف": "paid_by", "الصارف": "paid_by",
}
COMMON_HEADERS = {"الشهر": "month", "السنه": "year", "العمله": "currency", "المصدر": "source"}


def header_key(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text or "")).replace("(إنوجد)", "")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_date(text: str, default_year: int | None) -> tuple[date | None, bool]:
    """(date, ok). Empty text gives (None, True)."""
    raw = clean(text).translate(DIGITS)
    if not raw:
        return None, True
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if match:
        year, month, day = map(int, match.groups())
    else:
        match = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", raw)
        if not match:
            return None, False
        day, month = int(match.group(1)), int(match.group(2))
        if match.group(3):
            year = int(match.group(3)) + (2000 if int(match.group(3)) < 100 else 0)
        elif default_year:
            year = default_year
        else:
            return None, False  # no year anywhere: do not guess one
    try:
        return date(year, month, day), True
    except ValueError:
        return None, False


def read_text(path: Path) -> str:
    """Excel saves CSV as UTF-8 (with BOM), as "Unicode text" (UTF-16) or in the Windows code page.
    The last one loses Arabic letters, so it is refused with a clear message instead of guessed."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path.name}: die Datei ist nicht UTF-8. In Excel: Speichern unter -> CSV UTF-8 (durch Trennzeichen getrennt)."
        ) from exc


def detect_delimiter(text: str) -> str:
    """Excel in a German or Arabic region writes ";" (or tabs) instead of commas: use whichever the header line has most."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = {delimiter: first.count(delimiter) for delimiter in (",", ";", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def read_csv(path: Path, headers: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    """Returns (rows as {field: text, _line: n, _raw: json}, ignored header names)."""
    text = read_text(path)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=detect_delimiter(text))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    fields: list[str | None] = []
    ignored: list[str] = []
    table = {**{header_key(k): v for k, v in headers.items()}, **{header_key(k): v for k, v in COMMON_HEADERS.items()}}
    for name in header:
        field = table.get(header_key(name))
        fields.append(field)
        if field is None and clean(name):
            ignored.append(clean(name))
    rows = []
    for number, cells in enumerate(reader, start=2):
        if not any(clean(c) for c in cells):
            continue  # blank line
        row = {"_line": str(number)}
        raw = {}
        for index, cell in enumerate(cells):
            label = clean(header[index]) if index < len(header) else f"col{index}"
            raw[label] = clean(cell)
            if index < len(fields) and fields[index]:
                row[fields[index]] = clean(cell)
        row["_raw"] = json.dumps(raw, ensure_ascii=False)[:300]
        rows.append(row)
    return rows, ignored


class Report:
    def __init__(self) -> None:
        self.stats: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, set[str]] = {"fees": set(), "salaries": set()}
        self.rejected: list[str] = []
        self.ignored: dict[str, list[str]] = {}

    def table(self, kind: str) -> dict[str, Any]:
        return self.stats.setdefault(kind, {"rows": 0, "imported": 0, "skipped": 0, "rejected": 0})


def read_amount(text: str, default_currency: str) -> tuple[Decimal | None, str | None, bool]:
    """(value, explicit currency, problem). Empty -> (None, None, False): empty is not a problem
    by itself; the caller decides whether the field is required."""
    if not clean(text):
        return None, None, False
    parsed = parse_amount(text)
    if not parsed.ok or parsed.value is None:
        return None, parsed.currency, True
    return parsed.value, parsed.currency, False


def row_period(row: dict[str, str], year: int | None, month: int | None) -> tuple[int | None, int | None]:
    def number(text: str) -> int | None:
        digits = clean(text).translate(DIGITS)
        return int(digits) if digits.isdigit() else None

    return number(row.get("year", "")) or year, number(row.get("month", "")) or month


def source_of(row: dict[str, str], csv_name: str) -> str:
    return f"{clean(row.get('source')) or csv_name}#{clean(row.get('row')) or 'L' + row['_line']}"


def find_or_create_child(session: Session, name: str, class_name: str) -> tuple[Child, bool]:
    """Existing child with the same name is reused (no duplicates). An unreadable (empty) name
    never matches anything: each such row gets its own record, flagged for review."""
    if name:
        child = session.scalar(
            select(Child).where(func.lower(Child.display_name) == name.lower(), Child.is_active.is_(True))
        )
        if child is not None:
            conflict = bool(class_name and child.class_name and child.class_name != class_name)
            if class_name and not child.class_name:
                child.class_name = class_name
            return child, conflict
    child = Child(display_name=name, class_name=class_name)
    session.add(child)
    session.flush()
    return child, False


def import_fees(session: Session, rows: list[dict[str, str]], csv_name: str, default_currency: str,
                year: int | None, month: int | None, report: Report) -> None:
    stats = report.table("fees")
    for row in rows:
        stats["rows"] += 1
        row_year, row_month = row_period(row, year, month)
        source = source_of(row, csv_name)
        if not row_year or not row_month or not 1 <= row_month <= 12:
            stats["rejected"] += 1
            report.rejected.append(f"{source}: كشف بلا شهر/سنة (استخدم --year/--month أو عمودي الشهر والسنة)")
            continue
        report.sources["fees"].add(source)
        if session.scalar(select(FeeCharge.id).where(FeeCharge.source == source)) is not None:
            stats["skipped"] += 1
            continue
        review = False
        name, class_name = clean(row.get("name")), clean(row.get("class"))
        review |= not name
        required, c1, bad = read_amount(row.get("required", ""), default_currency)
        review |= bad or required is None or required == 0
        paid, c2, bad = read_amount(row.get("paid", ""), default_currency)
        review |= bad
        written_open, c3, bad = read_amount(row.get("open", ""), default_currency)
        review |= bad
        marks = {c for c in (c1, c2, c3, clean(row.get("currency")).upper() or None) if c}
        marks &= set(CURRENCIES)
        currency = default_currency
        if len(marks) == 1:
            currency = marks.pop()
            review |= currency != default_currency  # a currency that differs from the sheet is checked by a human
        elif len(marks) > 1:
            review = True
        pay_date, date_ok = parse_date(row.get("date", ""), row_year)
        review |= not date_ok
        # the row must add up: required - paid = open
        if written_open is not None and required is not None:
            review |= (required - (paid or Decimal(0))) != written_open
        if paid is not None and required is not None and paid > required:
            review = True
        if paid is not None and paid > 0 and pay_date is None:
            review = True  # money without a date: keep the date empty, check it
        child, class_conflict = find_or_create_child(session, name, class_name)
        review |= class_conflict
        if session.scalar(
            select(FeeCharge.id).where(
                FeeCharge.child_id == child.id, FeeCharge.year == row_year,
                FeeCharge.month == row_month, FeeCharge.currency == currency,
            )
        ) is not None:
            stats["skipped"] += 1  # that child already has this month/currency (other source)
            continue
        charge = FeeCharge(
            child_id=child.id, year=row_year, month=row_month, currency=currency,
            amount=required, note=clean(row.get("note")), source=source,
        )
        session.add(charge)
        session.flush()
        if paid is not None and paid > 0:
            receipt = clean(row.get("receipt")) or None
            if receipt and session.scalar(
                select(FeePayment.id).where(FeePayment.receipt_no == receipt, FeePayment.deleted_at.is_(None))
            ) is not None:
                receipt, review = None, True  # duplicate receipt number: not stored twice
            charge.payments.append(
                FeePayment(amount=paid, paid_on=pay_date, receipt_no=receipt, created_by_name="import",
                           payer_name=clean(row.get("payer")))
            )
        charge.needs_review = review
        charge.raw_text = row["_raw"] if review else ""
        stats["imported"] += 1


def import_salaries(session: Session, rows: list[dict[str, str]], csv_name: str, default_currency: str,
                    year: int | None, month: int | None, report: Report) -> None:
    stats = report.table("salaries")
    for row in rows:
        stats["rows"] += 1
        row_year, row_month = row_period(row, year, month)
        source = source_of(row, csv_name)
        if not row_year or not row_month or not 1 <= row_month <= 12:
            stats["rejected"] += 1
            report.rejected.append(f"{source}: كشف بلا شهر/سنة (استخدم --year/--month أو عمودي الشهر والسنة)")
            continue
        report.sources["salaries"].add(source)
        if session.scalar(select(SalaryLine.id).where(SalaryLine.source == source)) is not None:
            stats["skipped"] += 1
            continue
        name, job = clean(row.get("name")), clean(row.get("job"))
        review = not name
        values: dict[str, Decimal | None] = {}
        marks: set[str] = set()
        for key in ("base", "bonus", "advance", "deduction"):
            value, mark, bad = read_amount(row.get(key, ""), default_currency)
            values[key] = value
            review |= bad
            if mark in CURRENCIES:
                marks.add(mark)
        written_net, mark, bad = read_amount(row.get("net", ""), default_currency)
        review |= bad
        if mark in CURRENCIES:
            marks.add(mark)
        if clean(row.get("currency")).upper() in CURRENCIES:
            marks.add(clean(row.get("currency")).upper())
        currency = default_currency
        if len(marks) == 1:
            currency = marks.pop()
            review |= currency != default_currency
        elif len(marks) > 1:
            review = True
        review |= values["base"] is None  # no base salary: no net pay can be worked out
        if values["base"] is not None:
            computed = values["base"] + (values["bonus"] or 0) - (values["advance"] or 0) - (values["deduction"] or 0)
            review |= computed < 0
            if written_net is not None:
                review |= computed != written_net  # the row must add up
        received, date_ok = parse_date(row.get("date", ""), row_year)
        review |= not date_ok
        employee = None
        if name:
            employee = session.scalar(
                select(Employee).where(func.lower(Employee.name) == name.lower(), Employee.is_active.is_(True))
            )
        if employee is None:
            employee = Employee(name=name, job_title=job)
            session.add(employee)
            session.flush()
        elif job and not employee.job_title:
            employee.job_title = job
        if session.scalar(
            select(SalaryLine.id).where(
                SalaryLine.employee_id == employee.id, SalaryLine.year == row_year,
                SalaryLine.month == row_month, SalaryLine.currency == currency,
            )
        ) is not None:
            stats["skipped"] += 1
            continue
        session.add(SalaryLine(
            employee_id=employee.id, year=row_year, month=row_month, currency=currency, paid_on=received,
            needs_review=review, raw_text=row["_raw"] if review else "", source=source,
            paid_by=clean(row.get("paid_by")), recorded_by="import", **values,
        ))
        stats["imported"] += 1


# --------------------------------------------------------------------------- report


def build_report(session: Session, report: Report) -> str:
    """Totals come from the database (rows of the imported files), so a repeated run shows the same report."""
    lines: list[str] = []
    for kind, stats in report.stats.items():
        sources = report.sources[kind]
        if kind == "fees":
            charges = [c for c in session.scalars(select(FeeCharge)).all() if c.source in sources]
            review = sum(1 for c in charges if c.needs_review)
        else:
            lines_db = [l for l in session.scalars(select(SalaryLine)).unique().all() if l.source in sources]
            review = sum(1 for l in lines_db if l.needs_review)
        lines.append(
            f"[{kind}] Zeilen={stats['rows']}  neu importiert={stats['imported']}  uebersprungen={stats['skipped']}  "
            f"abgelehnt={stats['rejected']}  needs_review (gesamt in dieser Quelle)={review}"
        )
        if kind == "fees":
            by_class: dict[tuple[str, str], list[Decimal]] = {}
            for charge in charges:
                child = session.get(Child, charge.child_id)
                key = (child.class_name or "(بدون صف)", charge.currency)
                bucket = by_class.setdefault(key, [Decimal(0)] * 3)
                bucket[0] += money(charge.amount)
                bucket[1] += paid_amount(charge)
                bucket[2] += remaining_amount(charge) or Decimal(0)
            for (class_name, currency), (required, paid, open_) in sorted(by_class.items()):
                lines.append(f"    {class_name:12} {currency}: مطلوب={money(required)}  مدفوع={money(paid)}  متبقي={money(open_)}")
            for currency in CURRENCIES:
                totals = [sum((v[i] for (c, cur), v in by_class.items() if cur == currency), Decimal(0)) for i in range(3)]
                if any(totals):
                    lines.append(f"    الإجمالي {currency}: مطلوب={money(totals[0])}  مدفوع={money(totals[1])}  متبقي={money(totals[2])}")
        else:
            sums: dict[str, dict[str, Decimal]] = {}
            from app.accounting import net_pay

            for line in lines_db:
                bucket = sums.setdefault(line.currency, {k: Decimal(0) for k in ("base", "bonus", "advance", "deduction", "net")})
                for key in ("base", "bonus", "advance", "deduction"):
                    bucket[key] += getattr(line, key) or 0
                bucket["net"] += net_pay(line.base, line.bonus, line.advance, line.deduction) or 0
            for currency, bucket in sums.items():
                lines.append(f"    الإجمالي {currency}: " + "  ".join(f"{k}={money(v)}" for k, v in bucket.items()))
    for problem in report.rejected:
        lines.append(f"  ! abgelehnt: {problem}")
    for kind, names in report.ignored.items():
        if names:
            lines.append(f"  (nicht verwendete Spalten in {kind}: {', '.join(names)})")
    return "\n".join(lines) or "nichts importiert"


def run_import(session: Session, fees_path: Path | None, salaries_path: Path | None, *, currency: str = "SYP",
               year: int | None = None, month: int | None = None) -> tuple[Report, str]:
    report = Report()
    if fees_path is not None:
        rows, ignored = read_csv(fees_path, FEE_HEADERS)
        report.ignored["fees"] = ignored
        report.table("fees")
        import_fees(session, rows, fees_path.name, currency, year, month, report)
    if salaries_path is not None:
        rows, ignored = read_csv(salaries_path, SALARY_HEADERS)
        report.ignored["salaries"] = ignored
        report.table("salaries")
        import_salaries(session, rows, salaries_path.name, currency, year, month, report)
    session.flush()
    return report, build_report(session, report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the paper tables from CSV files.")
    parser.add_argument("--fees", type=Path, default=DEFAULT_FEES)
    parser.add_argument("--salaries", type=Path, default=DEFAULT_SALARIES)
    parser.add_argument("--only", choices=("fees", "salaries"))
    parser.add_argument("--currency", choices=CURRENCIES, default="SYP", help="currency of the sheets (default SYP)")
    parser.add_argument("--year", type=int, help="year for rows without a السنة column")
    parser.add_argument("--month", type=int, help="month for rows without a الشهر column")
    parser.add_argument("--dry-run", action="store_true", help="read and report, write nothing")
    args = parser.parse_args()

    wanted = {"fees": args.fees, "salaries": args.salaries}
    if args.only:
        wanted = {args.only: wanted[args.only]}
    missing = [str(path) for path in wanted.values() if not path.is_file()]
    if missing:
        print("Import abgebrochen: diese Datei(en) fehlen:\n  " + "\n  ".join(missing))
        print("Es wurden keine Daten angelegt. Lege die CSV-Dateien (UTF-8) dort ab und starte den Import erneut.")
        return 2

    from app.database import get_engine

    with Session(get_engine()) as session:
        try:
            _, text = run_import(session, wanted.get("fees"), wanted.get("salaries"),
                                 currency=args.currency, year=args.year, month=args.month)
        except ValueError as error:
            print("Import abgebrochen: " + str(error))
            print("Es wurden keine Daten angelegt.")
            return 2
        print(text)
        if args.dry_run:
            session.rollback()
            print("(Trockenlauf: nichts wurde gespeichert)")
        else:
            session.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
