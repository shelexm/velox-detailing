"""Russian phone numbers: the site and the bot accept any common spelling, the database stores +7XXXXXXXXXX."""

from __future__ import annotations

import re

_NOT_ASCII_DIGIT = re.compile(r"[^0-9]")  # \D would keep full-width and Arabic digits, which the database refuses


class InvalidPhoneError(ValueError):
    pass


def normalize_ru_phone(raw: str) -> str:
    digits = _NOT_ASCII_DIGIT.sub("", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "3489":
        raise InvalidPhoneError("Введите номер полностью: 10 цифр после +7")
    return "+7" + digits


def format_ru_phone(phone: str) -> str:
    """+79134521807 -> +7 913 452-18-07"""
    d = phone[2:]
    return f"+7 {d[0:3]} {d[3:6]}-{d[6:8]}-{d[8:10]}"
