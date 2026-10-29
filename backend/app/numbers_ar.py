"""Turn handwritten-style Arabic amounts into numbers.

Handles Arabic-Indic digits, number words ("مليون ونصف" -> 1,500,000), digit + multiplier
("٣ مليون" -> 3,000,000), sums ("500000 + 250 ألف") and currency marks ($, ل.س, USD, SYP).
Anything it is not sure about is returned with ok=False so the caller can flag it for review
instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile("[ً-ٰٟـ]")

UNITS = {
    "واحد": 1, "واحده": 1, "احد": 1, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2, "اثنا": 2,
    "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6,
    "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8, "ثمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10,
}
TENS = {
    "عشرين": 20, "عشرون": 20, "ثلاثين": 30, "ثلاثون": 30, "اربعين": 40, "اربعون": 40,
    "خمسين": 50, "خمسون": 50, "ستين": 60, "ستون": 60, "سبعين": 70, "سبعون": 70,
    "ثمانين": 80, "ثمانون": 80, "تسعين": 90, "تسعون": 90,
}
HUNDREDS = {
    "مئه": 100, "مائه": 100, "ميه": 100, "مئتين": 200, "مائتين": 200, "ميتين": 200,
    "مئتان": 200, "مائتان": 200, "ثلاثمئه": 300, "ثلاثمائه": 300, "اربعمئه": 400, "اربعمائه": 400,
    "خمسمئه": 500, "خمسمائه": 500, "ستمئه": 600, "ستمائه": 600, "سبعمئه": 700, "سبعمائه": 700,
    "ثمانمئه": 800, "ثمانمائه": 800, "تسعمئه": 900, "تسعمائه": 900,
}
MULTIPLIERS = {"الف": 1_000, "مليون": 1_000_000, "مليار": 1_000_000_000}
DUAL = {"الفين": 2_000, "مليونين": 2_000_000}
PLURAL = {"الاف": 1_000, "ملايين": 1_000_000}
FRACTIONS = {"نصف": Decimal("0.5"), "ربع": Decimal("0.25")}
IGNORED = {"ل", "س", "ليره", "ليرات", "سوريه", "سورية", "دولار", "دولارا", "دولارات", "امريكي", "فقط", "لا", "غير"}

USD_MARKS = re.compile(r"(\$|usd|دولار)", re.IGNORECASE)
SYP_MARKS = re.compile(r"(ل\s*\.\s*س|ل\s*س|ل\.س|ليرة|ليره|ليرات|syp|s\.?p\.?)", re.IGNORECASE)
NUMBER = re.compile(r"^\d+(\.\d+)?$")


@dataclass
class ParsedAmount:
    value: Decimal | None
    currency: str | None  # "USD", "SYP" or None when the text names no currency
    ok: bool
    note: str = ""


def normalize(text: str) -> str:
    text = DIACRITICS.sub("", text).translate(DIGITS)
    for old, new in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("٫", "."), ("٬", ""), ("،", " ")):
        text = text.replace(old, new)
    return text.lower()


def detect_currency(text: str) -> str | None:
    found = set()
    if USD_MARKS.search(text):
        found.add("USD")
    if SYP_MARKS.search(text):
        found.add("SYP")
    return found.pop() if len(found) == 1 else ("?" if found else None)


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,500,000 -> 1500000
    text = re.sub(r"[\$،؛;:()\[\]\"']", " ", text)
    text = re.sub(r"ل\s*\.?\s*س\.?", " ", text)
    words = []
    for raw in text.split():
        raw = raw.strip(".-_/")
        if not raw:
            continue
        if raw not in _VOCAB and not NUMBER.match(raw) and raw.startswith("و") and len(raw) > 2:
            raw = raw[1:]  # "ونصف" -> "نصف", "وخمسين" -> "خمسين"
        words.append(raw)
    return words


_VOCAB = set(UNITS) | set(TENS) | set(HUNDREDS) | set(MULTIPLIERS) | set(DUAL) | set(PLURAL) | set(FRACTIONS) | IGNORED


def _parse_part(part: str) -> tuple[Decimal | None, str]:
    """Returns (value, problem). value None + problem "" means empty text."""
    tokens = _tokens(part)
    tokens = [t for t in tokens if t not in IGNORED and t != "و"]
    if not tokens:
        return None, ""
    total = Decimal(0)
    current = Decimal(0)
    last_multiplier = 0
    last_unit = 0
    for index, token in enumerate(tokens):
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if NUMBER.match(token):
            try:
                current += Decimal(token)
            except InvalidOperation:
                return None, f"رقم غير مفهوم: {token}"
            last_unit = 0
        elif token in UNITS:
            current += UNITS[token]
            last_unit = UNITS[token] if 3 <= UNITS[token] <= 9 else 0
        elif token in TENS:
            current += TENS[token]
            last_unit = 0
        elif token in HUNDREDS:
            if token in ("مئه", "مائه", "ميه") and last_unit:
                current += last_unit * 99  # "ثلاث مئة": 3 -> 300
            else:
                current += HUNDREDS[token]
            last_unit = 0
        elif token in MULTIPLIERS:
            total += (current or 1) * MULTIPLIERS[token]
            current = Decimal(0)
            last_multiplier = MULTIPLIERS[token]
            last_unit = 0
        elif token in DUAL:
            total += current * DUAL[token] if current else DUAL[token]
            current = Decimal(0)
            last_multiplier = DUAL[token] // 2
            last_unit = 0
        elif token in PLURAL:
            if not current:
                return None, f"عدد ناقص قبل: {token}"
            total += current * PLURAL[token]
            current = Decimal(0)
            last_multiplier = PLURAL[token]
            last_unit = 0
        elif token in FRACTIONS:
            if following in MULTIPLIERS:
                current += FRACTIONS[token]  # "نصف مليون"
            elif last_multiplier:
                total += FRACTIONS[token] * last_multiplier  # "مليون ونصف"
            else:
                return None, "كسر بدون وحدة"
            last_unit = 0
        else:
            return None, f"كلمة غير مفهومة: {token}"
    total += current
    if last_multiplier >= 1_000_000 and current and total - current >= 1_000_000 and current < 1_000:
        return None, "مبلغ غامض بعد المليون (آلاف أم آحاد؟)"
    return total, ""


def parse_amount(text: str | None) -> ParsedAmount:
    """Parse one amount cell. Empty text gives value None with ok=True."""
    if text is None or not str(text).strip():
        return ParsedAmount(None, None, True)
    raw = normalize(str(text))
    currency = detect_currency(raw)
    if currency == "?":
        return ParsedAmount(None, None, False, "عملتان في الخانة نفسها")
    total = Decimal(0)
    seen = False
    for part in re.split(r"\+", raw):
        value, problem = _parse_part(part)
        if problem:
            return ParsedAmount(None, currency, False, problem)
        if value is not None:
            total += value
            seen = True
    if not seen:
        return ParsedAmount(None, currency, False, "لا يوجد مبلغ")
    if total < 0:
        return ParsedAmount(None, currency, False, "مبلغ سالب")
    return ParsedAmount(total.quantize(Decimal("0.01")), currency, True)
