import logging
from pathlib import Path
from typing import Optional, Literal
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel

from app.config import config
from app.database.database import (
    create_job,
    get_job,
    get_all_jobs,
    delete_job,
    update_job_status,
)
from app.schemas.document import MasterDocument
from app.services.file_service import FileService
from app.services.gemini_service import GeminiService
from app.services.document_service import DocumentService
from app.services.export_service import ExportService

logger = logging.getLogger("nobeth.routes")

router = APIRouter()


class UpdateBlockRequest(BaseModel):
    verbatim_text: Optional[str] = None
    cleaned_text: Optional[str] = None
    review_status: Optional[Literal["clear", "needs_review", "unreadable"]] = None


class ExportRequest(BaseModel):
    format: Literal["docx", "pdf", "txt", "json"] = "docx"
    version: Literal["verbatim", "cleaned"] = "cleaned"
    style: Literal["professional", "layout"] = "professional"


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "product": "Nobeth Document Intelligence",
        "organization": "Nobeth Analytics",
        "gemini_configured": GeminiService.is_configured(),
        "primary_model": config.gemini_primary_model,
        "fallback_model": config.gemini_fallback_model,
        "data_mode": config.gemini_data_mode,
    }


@router.get("/api/system/info")
async def get_system_info():
    return {
        "product_name": "Nobeth Document Intelligence",
        "organization": "Nobeth Analytics",
        "gemini_configured": GeminiService.is_configured(),
        "primary_model": config.gemini_primary_model,
        "fallback_model": config.gemini_fallback_model,
        "gemini_data_mode": config.gemini_data_mode,
        "limits": {
            "max_upload_mb": config.max_upload_mb,
            "max_files_per_job": config.max_files_per_job,
            "max_pdf_pages": config.max_pdf_pages,
            "max_image_pixels": config.max_image_pixels,
            "max_docx_images": config.max_docx_images,
            "job_retention_hours": config.job_retention_hours,
        },
    }


@router.post("/api/jobs")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Ingests and validates document, registers job, and initiates asynchronous processing.
    """
    # 1. Ingest and save
    job_id, file_format, target_path, bytes_written = await FileService.save_uploaded_file(file)

    # 2. Register in SQLite
    create_job(
        job_id=job_id,
        original_filename=file.filename or f"document.{file_format}",
        file_format=file_format,
        file_size_bytes=bytes_written,
        page_count=1,
    )

    # 3. Queue async processing task
    background_tasks.add_task(
        DocumentService.process_job_async,
        job_id=job_id,
        file_path=target_path,
        file_format=file_format,
        original_filename=file.filename or f"document.{file_format}",
        file_size_bytes=bytes_written,
    )

    return {
        "job_id": job_id,
        "original_filename": file.filename,
        "file_format": file_format,
        "file_size_bytes": bytes_written,
        "status": "queued",
        "message": "Document uploaded successfully and queued for intelligence processing.",
    }


@router.get("/api/jobs")
async def list_jobs(limit: int = 30):
    return get_all_jobs(limit=limit)


@router.get("/api/jobs/{job_id}")
async def get_job_details(job_id: str):
    clean_id = Path(job_id).name
    record = get_job(clean_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


@router.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    clean_id = Path(job_id).name
    record = get_job(clean_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": record["job_id"],
        "status": record["status"],
        "progress_percent": record["progress_percent"],
        "stage_label": record["stage_label"],
        "error_message": record["error_message"],
        "page_count": record["page_count"],
        "updated_at": record["updated_at"],
    }


@router.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    clean_id = Path(job_id).name
    record = get_job(clean_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record["status"] != "ready" or not record.get("result"):
        raise HTTPException(
            status_code=400,
            detail=f"Result is not ready. Current status: {record['status']}. {record.get('error_message', '')}",
        )
    return record["result"]


@router.get("/api/jobs/{job_id}/preview/{filename}")
async def get_job_preview(job_id: str, filename: str):
    """Safely serves rendered document page preview images."""
    clean_job_id = Path(job_id).name
    clean_filename = Path(filename).name
    preview_path = config.jobs_dir / clean_job_id / "previews" / clean_filename

    if not preview_path.exists() or not preview_path.is_file():
        raise HTTPException(status_code=404, detail="Preview image not found.")

    return FileResponse(
        preview_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.patch("/api/jobs/{job_id}/blocks/{block_id}")
async def update_block(job_id: str, block_id: str, req: UpdateBlockRequest):
    """Updates verbatim or cleaned text of a specific document block."""
    clean_job_id = Path(job_id).name
    clean_block_id = Path(block_id).name
    try:
        updated_doc = await DocumentService.update_block_content(
            job_id=clean_job_id,
            block_id=clean_block_id,
            verbatim_text=req.verbatim_text,
            cleaned_text=req.cleaned_text,
            review_status=req.review_status,
        )
        return updated_doc.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update block: {str(e)}")


@router.post("/api/jobs/{job_id}/clean")
async def regenerate_cleaned(job_id: str):
    """Regenerates the cleaned version based on the latest user-edited verbatim content."""
    clean_job_id = Path(job_id).name
    try:
        updated_doc = await DocumentService.regenerate_cleaned_from_verbatim(clean_job_id)
        return updated_doc.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to regenerate cleaned version: {str(e)}")


@router.post("/api/jobs/{job_id}/restore")
async def restore_transcription(job_id: str):
    """Restores the original unmodified AI transcription."""
    clean_job_id = Path(job_id).name
    try:
        restored_doc = DocumentService.restore_ai_transcription(clean_job_id)
        return restored_doc.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/jobs/{job_id}/export")
async def export_document(job_id: str, req: ExportRequest):
    """
    Generates and downloads DOCX, PDF, TXT, or JSON in the requested
    version (verbatim/cleaned) and style (professional/layout).
    """
    clean_job_id = Path(job_id).name
    record = get_job(clean_job_id)
    if not record or not record.get("result"):
        raise HTTPException(status_code=404, detail="Job or result not found.")

    doc = MasterDocument.model_validate(record["result"])
    base_name = Path(doc.original_filename).stem or "document"
    safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base_name)

    if req.format == "docx":
        data = ExportService.generate_docx(doc, version=req.version, style=req.style)
        filename = f"{safe_stem}_{req.version}_{req.style}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    elif req.format == "pdf":
        data = ExportService.generate_pdf(doc, version=req.version, style=req.style)
        filename = f"{safe_stem}_{req.version}.pdf"
        media_type = "application/pdf"

    elif req.format == "txt":
        txt_str = ExportService.generate_txt(doc, version=req.version)
        data = txt_str.encode("utf-8")
        filename = f"{safe_stem}_{req.version}.txt"
        media_type = "text/plain; charset=utf-8"

    elif req.format == "json":
        json_str = ExportService.generate_json(doc)
        data = json_str.encode("utf-8")
        filename = f"{safe_stem}_structured.json"
        media_type = "application/json; charset=utf-8"

    else:
        raise HTTPException(status_code=400, detail="Unsupported export format.")

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, background_tasks: BackgroundTasks):
    """Re-executes processing for an existing or failed job."""
    clean_id = Path(job_id).name
    record = get_job(clean_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")

    source_path = config.jobs_dir / clean_id / f"source.{record['file_format']}"
    if not source_path.exists():
        raise HTTPException(status_code=400, detail="Source file not found for retry.")

    update_job_status(
        clean_id,
        status="queued",
        progress_percent=5,
        stage_label="Document queued for retry processing",
        error_message="",
    )

    background_tasks.add_task(
        DocumentService.process_job_async,
        job_id=clean_id,
        file_path=source_path,
        file_format=record["file_format"],
        original_filename=record["original_filename"],
        file_size_bytes=record["file_size_bytes"],
    )

    return {"status": "queued", "job_id": clean_id, "message": "Job queued for retry."}


@router.delete("/api/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Deletes job database record and temporary filesystem assets."""
    clean_job_id = Path(job_id).name
    FileService.delete_job_files(clean_job_id)
    deleted = delete_job(clean_job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"status": "deleted", "job_id": clean_job_id}

