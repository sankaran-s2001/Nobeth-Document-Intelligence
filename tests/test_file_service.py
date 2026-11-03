import pytest
from pathlib import Path
from fastapi import HTTPException
from app.services.file_service import FileService


def test_detect_format_valid():
    # Valid JPEG magic bytes
    assert FileService.detect_format_from_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF", "photo.jpg") == "jpg"
    assert FileService.detect_format_from_bytes(b"\xFF\xD8\xFF\xE1", "scan.jpeg") == "jpg"

    # Valid PNG magic bytes
    assert FileService.detect_format_from_bytes(b"\x89PNG\r\n\x1a\n", "doc.png") == "png"

    # Valid PDF magic bytes
    assert FileService.detect_format_from_bytes(b"%PDF-1.7\n", "notes.pdf") == "pdf"

    # Valid DOCX (ZIP) magic bytes
    assert FileService.detect_format_from_bytes(b"PK\x03\x04\x14\x00", "report.docx") == "docx"


def test_reject_macro_docm():
    with pytest.raises(HTTPException) as exc:
        FileService.detect_format_from_bytes(b"PK\x03\x04", "macro_doc.docm")
    assert "Macro-enabled" in exc.value.detail


def test_reject_corrupted_signature():
    with pytest.raises(HTTPException) as exc:
        FileService.detect_format_from_bytes(b"INVALID_HEADER_BYTES", "fake.jpg")
    assert "Unsupported or corrupted" in exc.value.detail


def test_mismatched_extension():
    # File is PNG bytes but named .pdf
    with pytest.raises(HTTPException) as exc:
        FileService.detect_format_from_bytes(b"\x89PNG\r\n\x1a\n", "suspicious.pdf")
    assert "does not match" in exc.value.detail

