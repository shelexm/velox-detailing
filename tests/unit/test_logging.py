import logging

import pytest

from app.core.logging import MaskingFormatter, RequestIdFilter, mask_sensitive, request_id_var


@pytest.mark.parametrize(
    ("raw", "expected_fragment"),
    [
        ("client +7 913 452-18-07 booked", "+7*******07"),
        ("phone=89134521807", "+7*******07"),
        ("call +7(913)452-18-07", "+7*******07"),
    ],
)
def test_phone_numbers_are_masked(raw: str, expected_fragment: str) -> None:
    masked = mask_sensitive(raw)
    assert expected_fragment in masked
    assert "452" not in masked


def test_tokens_and_secret_pairs_are_masked() -> None:
    masked = mask_sensitive("token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw password=hunter2 ok")
    assert "AAHdq" not in masked
    assert "hunter2" not in masked
    assert masked.endswith("ok")


def test_formatter_masks_whole_line_including_traceback() -> None:
    formatter = MaskingFormatter("%(request_id)s %(message)s")
    request_id_var.set("req-12345678")
    try:
        raise ValueError("bad phone +7 913 452-18-07")
    except ValueError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, exc_info=True)
        import sys

        record.exc_info = sys.exc_info()
    RequestIdFilter().filter(record)
    line = formatter.format(record)
    assert line.startswith("req-12345678 failed")
    assert "452-18" not in line
