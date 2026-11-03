import logging
from pathlib import Path
from typing import List, Dict, Any
from fastapi import HTTPException
import pymupdf
from app.config import config

logger = logging.getLogger("nobeth.pdf_service")


class PDFService:
    @staticmethod
    def inspect_and_render_pages(
        pdf_path: Path, previews_dir: Path, dpi: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Inspects PDF, checks limits, renders each page as an image for preview
        and multimodal Gemini analysis.
        """
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Corrupted or invalid PDF file: {str(e)}",
            )

        try:
            if doc.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Encrypted or password-protected PDFs are not supported.",
                )

            page_count = len(doc)
            if page_count == 0:
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded PDF contains no pages.",
                )

            if page_count > config.max_pdf_pages:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF has {page_count} pages, which exceeds the limit of {config.max_pdf_pages} pages.",
                )

            pages_info: List[Dict[str, Any]] = []
            zoom = dpi / 72.0
            mat = pymupdf.Matrix(zoom, zoom)

            for i in range(page_count):
                page = doc[i]
                page_num = i + 1

                # Extract existing digital text if present
                existing_text = page.get_text().strip()

                # Render page to image
                pix = page.get_pixmap(matrix=mat, alpha=False)
                preview_filename = f"page_{page_num}.jpg"
                preview_path = previews_dir / preview_filename
                pix.save(str(preview_path), output="jpeg", jpg_quality=90)

                pages_info.append(
                    {
                        "page_number": page_num,
                        "width": int(page.rect.width),
                        "height": int(page.rect.height),
                        "preview_filename": preview_filename,
                        "image_path": preview_path,
                        "existing_text": existing_text,
                        "has_digital_text": len(existing_text) > 20,
                    }
                )

            return pages_info
        finally:
            doc.close()

