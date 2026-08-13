import logging
from pathlib import Path
from typing import List
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract full text from a PDF file using pypdf."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found at path: {path}")

    logger.info(f"Extracting text from PDF: {path.name}")
    reader = PdfReader(str(path))
    extracted_text: List[str] = []

    for idx, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            extracted_text.append(page_text)
        else:
            logger.warning(f"No text extracted from page {idx + 1} of {path.name}")

    full_text = "\n\n".join(extracted_text).strip()
    logger.info(f"Successfully extracted {len(full_text)} characters from {path.name}")
    return full_text


def split_text_into_chunks(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[str]:
    """Split input text into overlapping semantic text chunks."""
    if not text:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be strictly less than chunk_size")

    chunks: List[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start += chunk_size - chunk_overlap

    logger.info(f"Split text into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})")
    return chunks
