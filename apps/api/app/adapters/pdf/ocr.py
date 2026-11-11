"""OCR for pages without a text layer (D19, D71; spec 004 AC10). Tesseract, English only.

CPU-heavy, so it runs only on the enrichment queue and never delays digital papers.
"""

import pypdfium2 as pdfium
import pytesseract

OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 60  # per page


def ocr_pages(data: bytes, page_numbers: list[int]) -> dict[int, str]:
    """Text per 1-based page number."""
    pdf = pdfium.PdfDocument(data)
    try:
        result: dict[int, str] = {}
        for page_no in page_numbers:
            page = pdf[page_no - 1]
            try:
                image = page.render(scale=OCR_DPI / 72).to_pil()
            finally:
                page.close()
            text: str = pytesseract.image_to_string(image, lang="eng", timeout=OCR_TIMEOUT_SECONDS)
            result[page_no] = text.strip()
        return result
    finally:
        pdf.close()
