import pytest
from app.schemas.document import (
    MasterDocument,
    DocumentPage,
    DocumentBlock,
    NormalizedBBox,
    UncertaintyItem,
    TableBlockData,
    LanguageInfo,
)
from app.database.database import (
    init_db,
    create_job,
    update_job_status,
    save_job_result,
    get_job,
    delete_job,
)


def test_master_document_schema():
    doc = MasterDocument(
        job_id="test-job-001",
        original_filename="receipt.jpg",
        file_format="jpg",
        file_size_bytes=1024,
        document_title="Sample Receipt",
        document_type="receipt",
        languages=[LanguageInfo(code="en", name="English", script="Latin", is_primary=True)],
        pages=[
            DocumentPage(
                page_number=1,
                width=800,
                height=1200,
                blocks=[
                    DocumentBlock(
                        id="blk-1",
                        type="heading",
                        reading_order=1,
                        verbatim_text="Store Reciept",
                        cleaned_text="Store Receipt",
                        bbox=NormalizedBBox(x=0.1, y=0.1, width=0.8, height=0.1),
                    ),
                    DocumentBlock(
                        id="blk-2",
                        type="paragraph",
                        reading_order=2,
                        verbatim_text="Total: $45.00 [unclear]",
                        cleaned_text="Total: $45.00",
                        uncertainties=[
                            UncertaintyItem(text="[unclear]", reason="Smudged ink", page_number=1)
                        ],
                        review_status="needs_review",
                    ),
                ],
            )
        ],
    )

    assert doc.schema_version == "1.0"
    assert doc.get_total_uncertainties() == 2  # 1 in list + 1 needs_review status
    assert len(doc.get_all_blocks()) == 2
    assert "Store Reciept" in doc.get_plain_text(mode="verbatim")
    assert "Store Receipt" in doc.get_plain_text(mode="cleaned")

    # JSON roundtrip
    json_str = doc.model_dump_json()
    reconstructed = MasterDocument.model_validate_json(json_str)
    assert reconstructed.document_id == doc.document_id
    assert reconstructed.pages[0].blocks[0].cleaned_text == "Store Receipt"


def test_sqlite_lifecycle():
    init_db()

    job_id = "test-job-sqlite"
    job = create_job(
        job_id=job_id,
        original_filename="notes.pdf",
        file_format="pdf",
        file_size_bytes=50000,
        page_count=3,
    )
    assert job["status"] == "queued"

    update_job_status(
        job_id,
        status="extracting",
        progress_percent=60,
        stage_label="Transcribing handwriting",
    )

    fetched = get_job(job_id)
    assert fetched is not None
    assert fetched["status"] == "extracting"
    assert fetched["progress_percent"] == 60

    # Save mock result
    doc = MasterDocument(job_id=job_id, document_title="Extracted Document")
    save_job_result(job_id, doc)

    ready_job = get_job(job_id)
    assert ready_job["status"] == "ready"
    assert ready_job["result"] is not None
    assert ready_job["result"]["document_title"] == "Extracted Document"

    # Delete
    assert delete_job(job_id) is True
    assert get_job(job_id) is None


def test_list_item_and_block_normalization():
    from app.schemas.document import ListItem, DocumentBlock

    # Test various model variations of list_type
    li_hyphen = ListItem(order=1, verbatim_text="Note 1", list_type="hyphen")
    assert li_hyphen.list_type == "bullet"

    li_dash = ListItem(order=2, verbatim_text="Note 2", list_type="dash")
    assert li_dash.list_type == "bullet"

    li_disc = ListItem(order=3, verbatim_text="Note 3", list_type="disc")
    assert li_disc.list_type == "bullet"

    li_ordered = ListItem(order=4, verbatim_text="Step 1", list_type="ordered")
    assert li_ordered.list_type == "numbered"

    li_task = ListItem(order=5, verbatim_text="Buy milk", list_type="checkbox")
    assert li_task.list_type == "checkbox"

    # Test block type normalization
    blk_header = DocumentBlock(id="b1", type="header", verbatim_text="Title")
    assert blk_header.type == "heading"

    blk_unknown = DocumentBlock(id="b2", type="unusual_type", verbatim_text="Some text")
    assert blk_unknown.type == "paragraph"


