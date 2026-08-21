# src/file_reader.py
import os
from pypdf import PdfReader
from docx import Document as DocxDocument

def read_file_content(path: str, max_chars: int = 8000) -> str:
    """Extracts text from txt/pdf/docx. Caps length so it fits the model's context —
    for a genuinely huge document you'd want chunking, but for a personal assistant's
    typical use (a letter, a short report) this covers it honestly."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:max_chars]

    elif ext == ".pdf":
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text[:max_chars]

    elif ext == ".docx":
        doc = DocxDocument(path)
        text = "\n".join(p.text for p in doc.paragraphs)
        return text[:max_chars]

    else:
        return f"[Unsupported file type: {ext}]"
