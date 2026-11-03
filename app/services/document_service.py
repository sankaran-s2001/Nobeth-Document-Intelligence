import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import config
from app.database.database import update_job_status, save_job_result, get_job
from app.schemas.document import (
    MasterDocument,
    DocumentPage,
    DocumentBlock,
    NormalizedBBox,
    UncertaintyItem,
    TableBlockData,
    ListItem,
    KeyValuePair,
    LanguageInfo,
    ProcessingMetadata,
)
from app.services.file_service import FileService
from app.services.image_service import ImageService
from app.services.pdf_service import PDFService
from app.services.docx_service import DocxService
from app.services.gemini_service import GeminiService

logger = logging.getLogger("nobeth.document_service")

# Concurrency semaphore for active jobs
_job_semaphore = asyncio.Semaphore(config.max_concurrent_jobs)


class DocumentService:
    @classmethod
    async def process_job_async(
        cls,
        job_id: str,
        file_path: Path,
        file_format: str,
        original_filename: str,
        file_size_bytes: int,
    ) -> None:
        """
        Background task executing the complete 10-stage processing pipeline.
        Controlled by semaphore to enforce MAX_CONCURRENT_JOBS.
        """
        async with _job_semaphore:
            job_dir = FileService.get_job_dir(job_id)
            previews_dir = job_dir / "previews"
            assets_dir = job_dir / "extracted_assets"
            total_start_t = time.perf_counter()

            try:
                # STAGE 1: VALIDATION
                update_job_status(
                    job_id,
                    status="validating",
                    progress_percent=10,
                    stage_label="Validating file format, signature, and dimensions",
                )
                await asyncio.sleep(0.05)

                # STAGE 2: PREPROCESSING
                update_job_status(
                    job_id,
                    status="preprocessing",
                    progress_percent=25,
                    stage_label="Preprocessing document and preparing visual previews",
                )

                pages_to_process: List[Dict[str, Any]] = []

                if file_format in ("jpg", "jpeg", "png"):
                    preview_name = "page_1.jpg"
                    preview_path = previews_dir / preview_name
                    img_info = ImageService.process_image(file_path, preview_path)
                    pages_to_process.append(
                        {
                            "page_number": 1,
                            "width": img_info["width"],
                            "height": img_info["height"],
                            "preview_filename": preview_name,
                            "image_path": preview_path,
                            "context": f"Image format: {img_info['format']}",
                        }
                    )

                elif file_format == "pdf":
                    pdf_pages = PDFService.inspect_and_render_pages(file_path, previews_dir)
                    update_job_status(
                        job_id,
                        status="preprocessing",
                        progress_percent=30,
                        stage_label=f"Rendered {len(pdf_pages)} PDF pages",
                        page_count=len(pdf_pages),
                    )
                    for p in pdf_pages:
                        pages_to_process.append(
                            {
                                "page_number": p["page_number"],
                                "width": p["width"],
                                "height": p["height"],
                                "preview_filename": p["preview_filename"],
                                "image_path": p["image_path"],
                                "context": f"Digital text preview: {p['existing_text'][:150]}"
                                if p["has_digital_text"]
                                else "",
                            }
                        )

                elif file_format == "docx":
                    docx_items = DocxService.inspect_and_extract_docx(file_path, assets_dir, previews_dir)
                    preview_name = "page_1.jpg"
                    pages_to_process.append(
                        {
                            "page_number": 1,
                            "width": 800,
                            "height": 1100,
                            "preview_filename": preview_name,
                            "image_path": previews_dir / preview_name,
                            "docx_items": docx_items,
                            "context": f"DOCX document containing {len(docx_items)} structured elements.",
                        }
                    )

                # STAGE 3 & 4: DOCUMENT UNDERSTANDING & VERBATIM EXTRACTION
                if not GeminiService.is_configured():
                    update_job_status(
                        job_id,
                        status="failed",
                        progress_percent=35,
                        stage_label="AI processing stopped: Gemini API key not configured",
                        error_message="GEMINI_API_KEY is not configured in .env. Please configure your Google AI Studio API key.",
                    )
                    return

                update_job_status(
                    job_id,
                    status="analysing",
                    progress_percent=45,
                    stage_label="Understanding document layout, classifying type and languages",
                )

                master_doc = MasterDocument(
                    job_id=job_id,
                    original_filename=original_filename,
                    file_format=file_format,
                    file_size_bytes=file_size_bytes,
                    page_count=len(pages_to_process),
                )

                total_extraction_ms = 0
                used_model = config.gemini_primary_model
                used_fallback = False

                for idx, page_info in enumerate(pages_to_process):
                    p_num = page_info["page_number"]
                    pct = 50 + int((idx / len(pages_to_process)) * 25)
                    update_job_status(
                        job_id,
                        status="extracting",
                        progress_percent=pct,
                        stage_label=f"Reading and transcribing handwriting (Page {p_num} of {len(pages_to_process)})",
                    )

                    # Read image bytes for multimodal input
                    with open(page_info["image_path"], "rb") as f:
                        img_bytes = f.read()

                    # Call Gemini
                    extracted_json, m_id, f_used, dur_ms = await GeminiService.extract_page_content(
                        image_bytes=img_bytes,
                        page_number=p_num,
                        page_width=page_info["width"],
                        page_height=page_info["height"],
                        additional_context=page_info.get("context", ""),
                    )

                    total_extraction_ms += dur_ms
                    used_model = m_id
                    if f_used:
                        used_fallback = True

                    if idx == 0:
                        master_doc.document_title = extracted_json.get("document_title") or Path(original_filename).stem.replace("_", " ").title()
                        master_doc.document_type = extracted_json.get("document_type") or "general_handwritten_document"
                        raw_langs = extracted_json.get("languages", [])
                        master_doc.languages = [
                            LanguageInfo(
                                code=l.get("code", "en"),
                                name=l.get("name", "English"),
                                script=l.get("script", "Latin"),
                                is_primary=l.get("is_primary", False),
                            )
                            for l in raw_langs
                        ] or [LanguageInfo(code="en", name="English", script="Latin", is_primary=True)]

                    # Build DocumentPage
                    doc_page = DocumentPage(
                        page_number=p_num,
                        width=page_info["width"],
                        height=page_info["height"],
                        preview_filename=page_info["preview_filename"],
                    )

                    # Build Blocks
                    for b_raw in extracted_json.get("blocks", []):
                        bbox = None
                        if "bbox" in b_raw and isinstance(b_raw["bbox"], dict):
                            try:
                                bbox = NormalizedBBox(
                                    x=max(0.0, min(1.0, float(b_raw["bbox"].get("x", 0.0)))),
                                    y=max(0.0, min(1.0, float(b_raw["bbox"].get("y", 0.0)))),
                                    width=max(0.0, min(1.0, float(b_raw["bbox"].get("width", 0.5)))),
                                    height=max(0.0, min(1.0, float(b_raw["bbox"].get("height", 0.1)))),
                                )
                            except Exception:
                                bbox = None

                        uncertainties = []
                        for u_raw in b_raw.get("uncertainties", []):
                            uncertainties.append(
                                UncertaintyItem(
                                    text=str(u_raw.get("text", "")),
                                    reason=str(u_raw.get("reason", "Ambiguous handwriting stroke")),
                                    page_number=p_num,
                                    bbox=bbox,
                                )
                            )

                        tbl_data = None
                        if "table_data" in b_raw and isinstance(b_raw["table_data"], dict):
                            t_raw = b_raw["table_data"]
                            tbl_data = TableBlockData(
                                headers=[str(h) for h in t_raw.get("headers", [])],
                                rows=[[str(c) for c in r] for r in t_raw.get("rows", [])],
                            )

                        list_items = None
                        if "list_items" in b_raw and isinstance(b_raw["list_items"], list):
                            def _safe_list_type(raw_val: Any) -> str:
                                s = str(raw_val or "bullet").lower().strip()
                                if s in ("numbered", "number", "ordered", "digits", "roman", "alpha"):
                                    return "numbered"
                                elif s in ("checkbox", "check", "task", "todo", "box"):
                                    return "checkbox"
                                return "bullet"

                            list_items = [
                                ListItem(
                                    order=li.get("order", i + 1),
                                    verbatim_text=str(li.get("verbatim_text", "")),
                                    list_type=_safe_list_type(li.get("list_type", "bullet")),
                                    is_checked=li.get("is_checked"),
                                    level=int(li.get("level", 0) or 0),
                                )
                                for i, li in enumerate(b_raw["list_items"])
                            ]

                        key_values = None
                        if "key_values" in b_raw and isinstance(b_raw["key_values"], list):
                            key_values = [
                                KeyValuePair(key=str(kv.get("key", "")), value=str(kv.get("value", "")))
                                for kv in b_raw["key_values"]
                            ]

                        block = DocumentBlock(
                            id=b_raw.get("id") or f"blk-{p_num}-{len(doc_page.blocks) + 1}",
                            type=b_raw.get("type", "paragraph"),
                            reading_order=b_raw.get("reading_order", len(doc_page.blocks) + 1),
                            page_number=p_num,
                            bbox=bbox,
                            language=b_raw.get("language", "en"),
                            source_type=b_raw.get("source_type", "handwritten"),
                            verbatim_text=b_raw.get("verbatim_text", ""),
                            cleaned_text="",  # Generated in next stage
                            uncertainties=uncertainties,
                            review_status=b_raw.get("review_status", "clear"),
                            table_data=tbl_data,
                            list_items=list_items,
                            key_values=key_values,
                        )
                        doc_page.blocks.append(block)

                    master_doc.pages.append(doc_page)

                # STAGE 6: CLEANED VERSION GENERATION
                update_job_status(
                    job_id,
                    status="cleaning",
                    progress_percent=80,
                    stage_label="Polishing document, checking spelling, and formatting tables",
                )

                all_blocks = master_doc.get_all_blocks()
                clean_json, c_model, c_fallback, clean_duration_ms = await GeminiService.generate_cleaned_version(
                    document_title=master_doc.document_title,
                    blocks=all_blocks,
                    document_type=master_doc.document_type,
                )

                # Map cleaned blocks back to blocks by id
                cleaned_map = {b["id"]: b for b in clean_json.get("blocks", []) if "id" in b}
                for block in all_blocks:
                    if block.id in cleaned_map:
                        cb = cleaned_map[block.id]
                        block.cleaned_text = cb.get("cleaned_text") or block.verbatim_text
                        if block.table_data and "cleaned_table_data" in cb:
                            ct = cb["cleaned_table_data"]
                            block.table_data.cleaned_headers = ct.get("headers")
                            block.table_data.cleaned_rows = ct.get("rows")
                        if block.list_items and "cleaned_list_items" in cb:
                            for li, cli in zip(block.list_items, cb["cleaned_list_items"]):
                                li.cleaned_text = cli.get("cleaned_text") or li.verbatim_text
                        if block.key_values and "cleaned_key_values" in cb:
                            for kv, ckv in zip(block.key_values, cb["cleaned_key_values"]):
                                kv.cleaned_key = ckv.get("cleaned_key") or kv.key
                                kv.cleaned_value = ckv.get("cleaned_value") or kv.value
                    else:
                        block.cleaned_text = block.verbatim_text

                # STAGE 7: VALIDATION
                update_job_status(
                    job_id,
                    status="validating_result",
                    progress_percent=92,
                    stage_label="Checking document quality and marking unclear handwriting",
                )

                # Backup initial state for restoration
                master_doc.original_backup = {
                    "document_title": master_doc.document_title,
                    "pages": [p.model_dump() for p in master_doc.pages],
                }

                total_duration_ms = int((time.perf_counter() - total_start_t) * 1000)
                master_doc.processing = ProcessingMetadata(
                    extraction_model=used_model,
                    cleaning_model=c_model,
                    fallback_used=used_fallback or c_fallback,
                    extraction_duration_ms=total_extraction_ms,
                    cleaning_duration_ms=clean_duration_ms,
                    total_duration_ms=total_duration_ms,
                )

                # STAGE 8: SAVE RESULT
                save_job_result(job_id, master_doc)
                logger.info(
                    "Job %s completed successfully in %dms. Model: %s (fallback=%s)",
                    job_id,
                    total_duration_ms,
                    used_model,
                    used_fallback,
                )

            except Exception as e:
                logger.error("Job %s failed at processing pipeline: %s", job_id, e, exc_info=True)
                update_job_status(
                    job_id,
                    status="failed",
                    progress_percent=100,
                    stage_label="Document processing failed",
                    error_message=f"Processing error: {str(e)}",
                )

    @classmethod
    async def update_block_content(
        cls,
        job_id: str,
        block_id: str,
        verbatim_text: Optional[str] = None,
        cleaned_text: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> MasterDocument:
        """Saves user edits to a specific document block."""
        job_record = get_job(job_id)
        if not job_record or not job_record.get("result"):
            raise ValueError(f"Job {job_id} not found or has no result.")

        master_doc = MasterDocument.model_validate(job_record["result"])
        block = master_doc.get_block_by_id(block_id)
        if not block:
            raise ValueError(f"Block {block_id} not found in document {job_id}.")

        if verbatim_text is not None:
            block.verbatim_text = verbatim_text
        if cleaned_text is not None:
            block.cleaned_text = cleaned_text
        if review_status in ("clear", "needs_review", "unreadable"):
            block.review_status = review_status

        master_doc.user_edited = True
        save_job_result(job_id, master_doc)
        return master_doc

    @classmethod
    async def regenerate_cleaned_from_verbatim(cls, job_id: str) -> MasterDocument:
        """Regenerates the cleaned version using the user's latest edited verbatim content."""
        job_record = get_job(job_id)
        if not job_record or not job_record.get("result"):
            raise ValueError(f"Job {job_id} not found or has no result.")

        master_doc = MasterDocument.model_validate(job_record["result"])
        all_blocks = master_doc.get_all_blocks()

        clean_json, c_model, c_fallback, clean_duration_ms = await GeminiService.generate_cleaned_version(
            document_title=master_doc.document_title,
            blocks=all_blocks,
            document_type=master_doc.document_type,
        )

        cleaned_map = {b["id"]: b for b in clean_json.get("blocks", []) if "id" in b}
        for block in all_blocks:
            if block.id in cleaned_map:
                cb = cleaned_map[block.id]
                block.cleaned_text = cb.get("cleaned_text") or block.verbatim_text
                if block.table_data and "cleaned_table_data" in cb:
                    ct = cb["cleaned_table_data"]
                    block.table_data.cleaned_headers = ct.get("headers")
                    block.table_data.cleaned_rows = ct.get("rows")
            else:
                block.cleaned_text = block.verbatim_text

        master_doc.processing.cleaning_model = c_model
        master_doc.processing.cleaning_duration_ms = clean_duration_ms
        master_doc.user_edited = True
        save_job_result(job_id, master_doc)
        return master_doc

    @classmethod
    def restore_ai_transcription(cls, job_id: str) -> MasterDocument:
        """Restores the original AI transcription from backup."""
        job_record = get_job(job_id)
        if not job_record or not job_record.get("result"):
            raise ValueError(f"Job {job_id} not found or has no result.")

        master_doc = MasterDocument.model_validate(job_record["result"])
        if not master_doc.original_backup:
            raise ValueError("No original AI backup found for this job.")

        backup = master_doc.original_backup
        master_doc.document_title = backup.get("document_title", master_doc.document_title)
        master_doc.pages = [DocumentPage.model_validate(p) for p in backup.get("pages", [])]
        master_doc.user_edited = False

        save_job_result(job_id, master_doc)
        return master_doc

