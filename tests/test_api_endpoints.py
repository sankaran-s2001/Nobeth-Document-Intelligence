import pytest
import io
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.database.database import init_db, save_job_result, create_job
from app.schemas.document import MasterDocument, DocumentPage, DocumentBlock


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def test_health_and_info(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["product"] == "Nobeth Document Intelligence"
    assert data["organization"] == "Nobeth Analytics"

    r_info = client.get("/api/system/info")
    assert r_info.status_code == 200
    info_data = r_info.json()
    assert "limits" in info_data
    assert info_data["limits"]["max_upload_mb"] == 25


def test_serve_html_index(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "Nobeth Document Intelligence" in r.text
    assert "Nobeth Analytics" in r.text
    assert "static/assets/nobeth-analytics.png" in r.text


def test_upload_and_job_lifecycle(client: TestClient):
    # Create sample image in memory
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), color=(255, 255, 255)).save(buf, format="JPEG")
    buf.seek(0)

    # 1. Upload
    response = client.post(
        "/api/jobs",
        files={"file": ("handwriting_sample.jpg", buf, "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]
    assert data["status"] == "queued"

    # 2. Check status
    r_stat = client.get(f"/api/jobs/{job_id}/status")
    assert r_stat.status_code == 200
    assert r_stat.json()["job_id"] == job_id

    # 3. Save a completed mock result to test result & export endpoints
    mock_doc = MasterDocument(
        job_id=job_id,
        original_filename="handwriting_sample.jpg",
        document_title="Sample Note",
        pages=[
            DocumentPage(
                page_number=1,
                blocks=[
                    DocumentBlock(
                        id="blk-test-1",
                        reading_order=1,
                        type="paragraph",
                        verbatim_text="Initial verbatim text",
                        cleaned_text="Initial cleaned text",
                    )
                ],
            )
        ],
    )
    save_job_result(job_id, mock_doc)

    # 4. Get result
    r_res = client.get(f"/api/jobs/{job_id}/result")
    assert r_res.status_code == 200
    assert r_res.json()["document_title"] == "Sample Note"

    # 5. Patch block
    r_patch = client.patch(
        f"/api/jobs/{job_id}/blocks/blk-test-1",
        json={"verbatim_text": "Updated verbatim content"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["pages"][0]["blocks"][0]["verbatim_text"] == "Updated verbatim content"

    # 6. Export DOCX
    r_exp_docx = client.post(
        f"/api/jobs/{job_id}/export",
        json={"format": "docx", "version": "cleaned", "style": "professional"},
    )
    assert r_exp_docx.status_code == 200
    assert len(r_exp_docx.content) > 0
    assert "attachment" in r_exp_docx.headers.get("content-disposition", "")

    # 7. Export PDF
    r_exp_pdf = client.post(
        f"/api/jobs/{job_id}/export",
        json={"format": "pdf", "version": "verbatim", "style": "professional"},
    )
    assert r_exp_pdf.status_code == 200
    assert len(r_exp_pdf.content) > 0

    # 8. Export TXT
    r_exp_txt = client.post(
        f"/api/jobs/{job_id}/export",
        json={"format": "txt", "version": "cleaned"},
    )
    assert r_exp_txt.status_code == 200
    assert b"Initial cleaned text" in r_exp_txt.content

    # 9. Delete job
    r_del = client.delete(f"/api/jobs/{job_id}")
    assert r_del.status_code == 200

