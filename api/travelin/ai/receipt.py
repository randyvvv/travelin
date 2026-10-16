"""Receipt Scan: Gemini reads the items, prices, tax, and service charge from a photo."""

from google.genai import types
from pydantic import BaseModel

from ..config import get_settings
from .genai import client, fast_config

IMAGE_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
}
# Totals within this fraction count as matching (rounding on printed receipts).
TOLERANCE = 0.01

PROMPT = """\
Read this restaurant or shop receipt from Indonesia.

All money values are whole Indonesian rupiah written as plain integers. Receipts use "." as
the thousands separator, so "Rp 25.000" is 25000 and "1.250.000" is 1250000.

- items: every ordered line with its name as printed, the unit price, the quantity, and the
  line total. Skip lines that are not items (headers, payment method, change).
- subtotal: the total before tax and service.
- tax: tax such as PB1 or PPN; 0 if none.
- service: the service charge; 0 if none.
- discount: any discount or promo as a positive number; 0 if none.
- total: the final amount to pay.
- merchant: the shop or restaurant name, or "" if not printed."""


class ReceiptItem(BaseModel):
    name: str
    unit_price: int
    qty: int
    line_total: int


class Receipt(BaseModel):
    merchant: str
    items: list[ReceiptItem]
    subtotal: int
    tax: int
    service: int
    discount: int
    total: int


def _close(a: int, b: int) -> bool:
    return abs(a - b) <= max(1, TOLERANCE * max(abs(a), abs(b)))


def check(receipt: Receipt) -> list[str]:
    """Arithmetic the squad should double-check before saving."""
    warnings = []
    items_total = sum(item.line_total for item in receipt.items)
    if not _close(items_total, receipt.subtotal):
        warnings.append(
            f"The items add up to Rp{items_total:,} but the subtotal reads Rp{receipt.subtotal:,}."
        )
    expected = receipt.subtotal + receipt.tax + receipt.service - receipt.discount
    if not _close(expected, receipt.total):
        warnings.append(
            f"Subtotal, tax, service, and discount make Rp{expected:,}, "
            f"but the total reads Rp{receipt.total:,}."
        )
    for item in receipt.items:
        if not _close(item.unit_price * item.qty, item.line_total):
            warnings.append(f"Check the price or quantity of {item.name}.")
    return warnings


async def scan(storage_path: str) -> Receipt:
    extension = storage_path.rsplit(".", 1)[-1].lower()
    image = types.Part.from_uri(
        file_uri=f"gs://{get_settings().storage_bucket}/{storage_path}",
        mime_type=IMAGE_MIME_TYPES.get(extension, "image/jpeg"),
    )
    response = await client().aio.models.generate_content(
        model=get_settings().fast_model,
        contents=[image, PROMPT],
        config=fast_config(response_mime_type="application/json", response_schema=Receipt),
    )
    result = response.parsed
    if not isinstance(result, Receipt):
        result = Receipt.model_validate_json(response.text or "{}")
    return result
