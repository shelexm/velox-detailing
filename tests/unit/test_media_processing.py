"""Phone photos: huge JPEGs are decoded at reduced scale, oversized or HEIC files get a clear refusal."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.errors import ValidationFailedError
from app.services import media


def encode(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "#336699").save(buffer, fmt)
    return buffer.getvalue()


@pytest.mark.parametrize("size", [(5200, 3900), (3900, 5200)])
def test_large_jpeg_keeps_its_real_size_and_gets_standard_variants(size: tuple[int, int]) -> None:
    result = media.process_image(encode(*size))
    assert (result.width, result.height) == size
    widths = sorted({width for _, width, _, _ in result.variants})
    assert widths == [480, 960, 1600, 2400]
    assert {ext for ext, *_ in result.variants} == {"avif", "webp", "jpg"}


def test_small_jpeg_is_not_scaled_down() -> None:
    result = media.process_image(encode(1200, 800))
    assert (result.width, result.height) == (1200, 800)
    assert sorted({width for _, width, _, _ in result.variants}) == [480, 960, 1200]


def test_heic_gets_a_clear_message() -> None:
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
    with pytest.raises(ValidationFailedError) as caught:
        media.process_image(heic)
    assert "HEIC" in caught.value.message


def test_not_an_image_is_still_refused() -> None:
    with pytest.raises(ValidationFailedError) as caught:
        media.process_image(b"<svg onload=alert(1)>")
    assert "не изображение" in caught.value.message


def test_pixel_limits_are_checked_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "MAX_PIXELS", 1_000_000)
    with pytest.raises(ValidationFailedError) as png:
        media.process_image(encode(1200, 1000, "PNG"))
    assert "разрешение" in png.value.message

    monkeypatch.setattr(media, "MAX_JPEG_PIXELS", 1_000_000)
    with pytest.raises(ValidationFailedError) as jpeg:
        media.process_image(encode(1200, 1000))
    assert "разрешение" in jpeg.value.message
