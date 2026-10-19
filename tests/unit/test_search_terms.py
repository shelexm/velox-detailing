import pytest

from app.services.queries import _search_terms


@pytest.mark.parametrize("text", ["Audi A6", "X5", "BMW X5 2021", "Иван 2"])
def test_text_with_a_digit_is_not_a_phone_search(text: str) -> None:
    like, phone, number = _search_terms(text)
    assert phone is None and number is None and like == f"%{text}%"


@pytest.mark.parametrize(
    ("text", "phone"),
    [
        ("8 (913) 452-18-07", "%9134521807%"),
        ("+7 913 452", "%7913452%"),
        ("4521", "%4521%"),
        ("913", "%913%"),
        ("91", None),
    ],
)
def test_phone_like_text_searches_phones_from_three_digits(text: str, phone: str | None) -> None:
    assert _search_terms(text)[1] == phone


def test_booking_number_and_wildcards() -> None:
    assert _search_terms("№ 17")[2] == 17 and _search_terms("#17")[2] == 17 and _search_terms("17")[2] == 17
    assert _search_terms("1234567")[2] is None  # too long to be a booking number
    assert _search_terms("50%")[0] == r"%50\%%" and _search_terms("a_b")[0] == r"%a\_b%"
