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


def test_booking_links_and_bot_urls_are_masked() -> None:
    token = "x7Kq2mZp9LwR4tYv8NbC3dFg"
    for line in (
        f"GET /booking/{token} HTTP/1.1",
        f"POST /api/v1/public/studios/velox/bookings/manage/{token}/cancel",
        f"GET /api/v1/public/studios/velox/bookings/manage/{token}/calendar.ics",
    ):
        masked = mask_sensitive(line)
        assert token not in masked and "<token>" in masked
    bot_url = "https://api.telegram.org/bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw/getMe"
    assert "AAHdq" not in mask_sensitive(bot_url)
    assert mask_sensitive("GET /booking/new HTTP/1.1") == "GET /booking/new HTTP/1.1"  # short words are not secrets


def test_probe_access_lines_are_dropped() -> None:
    from app.core.logging import QuietProbeFilter

    def record(path: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("1.2.3.4", "GET", path, "1.1", 200),
            None,
        )

    assert not QuietProbeFilter().filter(record("/health/live"))
    assert QuietProbeFilter().filter(record("/health/ready"))
    assert QuietProbeFilter().filter(record("/booking/abc"))
