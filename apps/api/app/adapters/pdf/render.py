"""Render one box of one PDF page as PNG (figure crops, spec 009; regions, AC11).

Always from the sanitized PDF on the server: the browser only ever sends a page and a box.
"""

import io

import pypdfium2 as pdfium

from app.ports.layout import Box

CROP_SCALE = 2.0  # 144 dpi: sharp on screens and readable for vision models, small to store


def render_crop(data: bytes, page_no: int, box: Box, scale: float = CROP_SCALE) -> bytes:
    """PNG of one box of one page, rendered from the sanitized PDF (never from the browser)."""
    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_no - 1]
        try:
            width, height = page.get_size()
            b = box.clamped()
            image = page.render(
                scale=scale,
                crop=(
                    b.x * width,
                    (1 - b.y - b.height) * height,
                    (1 - b.x - b.width) * width,
                    b.y * height,
                ),
            ).to_pil()
        finally:
            page.close()
    finally:
        pdf.close()
    out = io.BytesIO()
    image.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def text_in_box(data: bytes, page_no: int, box: Box) -> str:
    """The text layer inside one box of one page (empty for scans and pictures)."""
    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_no - 1]
        try:
            width, height = page.get_size()
            b = box.clamped()
            textpage = page.get_textpage()
            try:
                return str(
                    textpage.get_text_bounded(
                        left=b.x * width,
                        bottom=(1 - b.y - b.height) * height,
                        right=(b.x + b.width) * width,
                        top=(1 - b.y) * height,
                    )
                ).strip()
            finally:
                textpage.close()
        finally:
            page.close()
    finally:
        pdf.close()
