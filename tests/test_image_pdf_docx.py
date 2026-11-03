import pytest
import io
from pathlib import Path
from PIL import Image
import pymupdf
import docx

from app.services.image_service import ImageService
from app.services.pdf_service import PDFService
from app.services.docx_service import DocxService


def test_image_processing(tmp_path: Path):
    # Create valid sample test image
    img_path = tmp_path / "sample.jpg"
    preview_path = tmp_path / "preview.jpg"
    img = Image.new("RGB", (300, 400), color=(240, 240, 240))
    img.save(img_path, format="JPEG")

    res = ImageService.process_image(img_path, preview_path)
    assert res["width"] == 300
    assert res["height"] == 400
    assert preview_path.exists()

    analysis_bytes = ImageService.get_analysis_bytes(img_path)
    assert len(analysis_bytes) > 0


def test_image_too_small(tmp_path: Path):
    small_path = tmp_path / "tiny.jpg"
    img = Image.new("RGB", (20, 20), color=(255, 255, 255))
    img.save(small_path, format="JPEG")

    with pytest.raises(Exception):
        ImageService.process_image(small_path)


def test_pdf_inspection_and_render(tmp_path: Path):
    pdf_path = tmp_path / "test.pdf"
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()

    # Create 2-page PDF
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "Nobeth Analytics Page 1 Test")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "Nobeth Analytics Page 2 Test")
    doc.save(str(pdf_path))
    doc.close()

    pages = PDFService.inspect_and_render_pages(pdf_path, previews_dir)
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert pages[1]["page_number"] == 2
    assert (previews_dir / "page_1.jpg").exists()
    assert (previews_dir / "page_2.jpg").exists()


def test_docx_inspection_and_structure(tmp_path: Path):
    docx_path = tmp_path / "test_doc.docx"
    assets_dir = tmp_path / "assets"
    previews_dir = tmp_path / "previews"
    assets_dir.mkdir()
    previews_dir.mkdir()

    # Create DOCX with paragraph, table, and embedded image
    doc = docx.Document()
    doc.add_paragraph("Paragraph 1: Executive Summary")
    
    # Table
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Item"
    table.cell(0, 1).text = "Price"
    table.cell(1, 0).text = "Consulting"
    table.cell(1, 1).text = "$500"

    # Embedded image
    img_sample = tmp_path / "embed.png"
    Image.new("RGB", (100, 100), color=(13, 94, 99)).save(img_sample)
    doc.add_picture(str(img_sample))

    doc.add_paragraph("Paragraph 2: Concluding Remarks")
    doc.save(str(docx_path))

    extracted = DocxService.inspect_and_extract_docx(docx_path, assets_dir, previews_dir)
    assert len(extracted) >= 3

    kinds = [it["kind"] for it in extracted]
    assert "text" in kinds
    assert "table" in kinds
    assert "embedded_image" in kinds
    assert (previews_dir / "page_1.jpg").exists()

