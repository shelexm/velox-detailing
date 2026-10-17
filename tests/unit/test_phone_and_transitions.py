import pytest

from app.core.phone import InvalidPhoneError, format_ru_phone, normalize_ru_phone
from app.models.enums import BookingStatus
from app.services.booking import TRANSITIONS


@pytest.mark.parametrize(
    "raw", ["+7 913 452-18-07", "8 (913) 452 18 07", "9134521807", "+79134521807", "7-913-452-18-07"]
)
def test_phone_normalization(raw: str) -> None:
    assert normalize_ru_phone(raw) == "+79134521807"


@pytest.mark.parametrize("raw", ["", "+7 913 45", "12345678901", "+1 913 452 18 07", "+7 113 452-18-07", "abc"])
def test_invalid_phones_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_ru_phone(raw)


def test_phone_formatting() -> None:
    assert format_ru_phone("+79134521807") == "+7 913 452-18-07"


def test_every_status_has_transitions_defined() -> None:
    assert set(TRANSITIONS) == set(BookingStatus)


def test_final_and_expired_states() -> None:
    assert TRANSITIONS[BookingStatus.EXPIRED] == frozenset()
    assert BookingStatus.CONFIRMED in TRANSITIONS[BookingStatus.NEW]
    assert BookingStatus.HOLD not in set().union(*TRANSITIONS.values())
