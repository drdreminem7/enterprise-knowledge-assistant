from pathlib import Path

import fitz
from docx import Document as DocxDocument


def extract_text_from_file(file_path: str) -> tuple[str, int | None]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore"), None

    if suffix == ".docx":
        document = DocxDocument(path)
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        return "\n".join(paragraphs), None

    if suffix == ".pdf":
        with fitz.open(path) as pdf:
            pages = [page.get_text("text") for page in pdf]
            return "\n".join(pages), len(pdf)

    raise ValueError(f"Unsupported file type: {suffix}")
