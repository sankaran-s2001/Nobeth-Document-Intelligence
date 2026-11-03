import pytest
import pymupdf
import docx
import io
from app.schemas.document import (
    MasterDocument,
    DocumentPage,
    DocumentBlock,
    NormalizedBBox,
    LanguageInfo,
    TableBlockData,
)
from app.services.export_service import ExportService


@pytest.fixture
def multilingual_sample_doc() -> MasterDocument:
    return MasterDocument(
        document_title="Multilingual Intelligence Test",
        document_type="student_notes",
        languages=[
            LanguageInfo(code="en", name="English", script="Latin", is_primary=True),
            LanguageInfo(code="hi", name="Hindi", script="Devanagari"),
            LanguageInfo(code="ta", name="Tamil", script="Tamil"),
        ],
        pages=[
            DocumentPage(
                page_number=1,
                blocks=[
                    DocumentBlock(
                        id="b-1",
                        type="title",
                        reading_order=1,
                        verbatim_text="Multilingual Handwriting Analysis",
                        cleaned_text="Multilingual Handwriting Analysis",
                    ),
                    DocumentBlock(
                        id="b-2",
                        type="paragraph",
                        reading_order=2,
                        verbatim_text="Hindi text: नमस्ते दुनिया - हस्तलिखित दस्तावेज़ बुद्धिमत्ता",
                        cleaned_text="Hindi text: नमस्ते दुनिया - हस्तलिखित दस्तावेज़ बुद्धिमत्ता",
                    ),
                    DocumentBlock(
                        id="b-3",
                        type="paragraph",
                        reading_order=3,
                        verbatim_text="Tamil text: வணக்கம் உலகம் - கையெழுத்து ஆவண நுண்ணறிவு",
                        cleaned_text="Tamil text: வணக்கம் உலகம் - கையெழுத்து ஆவண நுண்ணறிவு",
                    ),
                    DocumentBlock(
                        id="b-4",
                        type="table",
                        reading_order=4,
                        table_data=TableBlockData(
                            headers=["Language", "Greeting", "Status"],
                            rows=[
                                ["English", "Hello World", "Verified"],
                                ["Hindi", "नमस्ते", "सत्यापित"],
                                ["Tamil", "வணக்கம்", "சரிபார்க்கப்பட்டது"],
                            ],
                        ),
                    ),
                ],
            )
        ],
    )


def test_docx_export_multilingual(multilingual_sample_doc):
    docx_bytes = ExportService.generate_docx(
        multilingual_sample_doc, version="cleaned", style="professional"
    )
    assert len(docx_bytes) > 0

    # Parse with python-docx
    doc = docx.Document(io.BytesIO(docx_bytes))
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "Multilingual Handwriting Analysis" in full_text
    assert "नमस्ते दुनिया" in full_text
    assert "வணக்கம் உலகம்" in full_text


def test_docx_export_layout_style(multilingual_sample_doc):
    docx_bytes = ExportService.generate_docx(
        multilingual_sample_doc, version="verbatim", style="layout"
    )
    assert len(docx_bytes) > 0


def test_pdf_export_multilingual(multilingual_sample_doc):
    pdf_bytes = ExportService.generate_pdf(
        multilingual_sample_doc, version="cleaned", style="professional"
    )
    assert len(pdf_bytes) > 0

    # Inspect rendered PDF text via pymupdf
    pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page_text = pdf_doc[0].get_text()
    assert "Multilingual Intelligence Test" in page_text
    assert "नमस्ते दुनिया" in page_text
    assert "வணக்கம் உலகம்" in page_text


def test_txt_and_json_export(multilingual_sample_doc):
    txt_str = ExportService.generate_txt(multilingual_sample_doc, version="cleaned")
    assert "Multilingual Handwriting Analysis" in txt_str
    assert "नमस्ते दुनिया" in txt_str
    assert "வணக்கம் உலகம்" in txt_str

    json_str = ExportService.generate_json(multilingual_sample_doc)
    assert '"document_title": "Multilingual Intelligence Test"' in json_str
    assert "नमस्ते दुनिया" in json_str

