import logging
import zipfile
import io
from pathlib import Path
from typing import List, Dict, Any, Tuple
from fastapi import HTTPException
from PIL import Image
import docx
from docx.oxml.ns import qn
from app.config import config

logger = logging.getLogger("nobeth.docx_service")


class DocxService:
    @staticmethod
    def inspect_and_extract_docx(
        docx_path: Path, output_assets_dir: Path, output_previews_dir: Path
    ) -> List[Dict[str, Any]]:
        """
        Safely validates DOCX archive, extracts typed text, tables, and embedded images
        in chronological reading order, and creates preview images.
        """
        # 1. Security Check: ZIP bomb and Path Traversal
        try:
            with zipfile.ZipFile(docx_path, "r") as zf:
                total_uncompressed = 0
                total_entries = len(zf.infolist())
                if total_entries > 2000:
                    raise HTTPException(
                        status_code=400,
                        detail="DOCX archive contains too many entries (possible zip bomb).",
                    )
                for info in zf.infolist():
                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        raise HTTPException(
                            status_code=400,
                            detail="Unsafe file path detected in DOCX archive.",
                        )
                    total_uncompressed += info.file_size
                
                # Check decompression ratio
                compressed_size = docx_path.stat().st_size
                if compressed_size > 0 and (total_uncompressed / compressed_size > 100):
                    raise HTTPException(
                        status_code=400,
                        detail="Excessive compression ratio detected (possible zip bomb).",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=400,
                detail="Corrupted DOCX file (invalid zip archive).",
            )

        # 2. Parse Document Structure with python-docx
        try:
            doc = docx.Document(str(docx_path))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse DOCX document: {str(e)}",
            )

        extracted_items: List[Dict[str, Any]] = []
        image_counter = 0

        # Helper to find blips (embedded images)
        def extract_blips(element) -> List[Tuple[str, bytes, str]]:
            blips = []
            for blip in element.xpath(".//a:blip"):
                r_id = blip.get(qn("r:embed"))
                if r_id and r_id in doc.part.rels:
                    rel = doc.part.rels[r_id]
                    target_part = rel.target_part
                    content_type = getattr(target_part, "content_type", "")
                    if "image" in content_type:
                        img_bytes = target_part.blob
                        # extension
                        ext = content_type.split("/")[-1].replace("jpeg", "jpg")
                        if not ext or len(ext) > 5:
                            ext = "png"
                        blips.append((r_id, img_bytes, ext))
            return blips

        # Iterate over body elements in true reading order
        for child in doc.element.body:
            tag = child.tag.split("}")[-1]

            if tag == "p":
                # Paragraph
                p = docx.text.paragraph.Paragraph(child, doc)
                p_text = p.text.strip()
                
                # Check for images inside paragraph
                blips = extract_blips(child)
                for _, img_bytes, ext in blips:
                    image_counter += 1
                    if image_counter > config.max_docx_images:
                        raise HTTPException(
                            status_code=400,
                            detail=f"DOCX has more than {config.max_docx_images} embedded images.",
                        )
                    img_filename = f"embedded_img_{image_counter}.{ext}"
                    img_path = output_assets_dir / img_filename
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)

                    extracted_items.append({
                        "kind": "embedded_image",
                        "image_index": image_counter,
                        "image_path": img_path,
                        "image_filename": img_filename,
                        "order": len(extracted_items) + 1,
                    })

                if p_text:
                    extracted_items.append({
                        "kind": "text",
                        "text": p_text,
                        "style": p.style.name if p.style else "Normal",
                        "order": len(extracted_items) + 1,
                    })

            elif tag == "tbl":
                # Table
                t = docx.table.Table(child, doc)
                rows_data = []
                for row in t.rows:
                    row_cells = []
                    for cell in row.cells:
                        # Extract cell text
                        cell_text = cell.text.strip()
                        row_cells.append(cell_text)

                        # Also check for images inside table cells
                        blips = extract_blips(cell._element)
                        for _, img_bytes, ext in blips:
                            image_counter += 1
                            if image_counter > config.max_docx_images:
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"DOCX exceeds {config.max_docx_images} embedded images.",
                                )
                            img_filename = f"embedded_img_{image_counter}.{ext}"
                            img_path = output_assets_dir / img_filename
                            with open(img_path, "wb") as f:
                                f.write(img_bytes)
                            extracted_items.append({
                                "kind": "embedded_image",
                                "image_index": image_counter,
                                "image_path": img_path,
                                "image_filename": img_filename,
                                "order": len(extracted_items) + 1,
                            })
                    rows_data.append(row_cells)

                if rows_data:
                    extracted_items.append({
                        "kind": "table",
                        "rows": rows_data,
                        "order": len(extracted_items) + 1,
                    })

        # Generate a preview image representing the DOCX (first embedded image or a rendered composite)
        preview_filename = "page_1.jpg"
        preview_path = output_previews_dir / preview_filename
        
        # If there are embedded images, use the first image or compose them
        first_img = next((it for it in extracted_items if it["kind"] == "embedded_image"), None)
        if first_img:
            try:
                with Image.open(first_img["image_path"]) as im:
                    im.convert("RGB").save(preview_path, format="JPEG", quality=90)
            except Exception:
                _create_fallback_docx_preview(extracted_items, preview_path)
        else:
            _create_fallback_docx_preview(extracted_items, preview_path)

        return extracted_items


def _create_fallback_docx_preview(items: List[Dict[str, Any]], target_path: Path) -> None:
    """Creates a clean visual preview card for text-based or mixed DOCX documents."""
    from PIL import ImageDraw, ImageFont
    w, h = 800, 1000
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle([0, 0, w, 60], fill=(13, 94, 99))  # Nobeth Teal
    draw.text((30, 20), "NOBETH DOCUMENT INTELLIGENCE - DOCX PREVIEW", fill=(255, 255, 255))

    y = 90
    for it in items[:15]:
        if it["kind"] == "text":
            snippet = it["text"][:90]
            draw.text((40, y), snippet, fill=(40, 40, 40))
            y += 32
        elif it["kind"] == "table":
            draw.text((40, y), f"[Table: {len(it['rows'])} rows]", fill=(13, 94, 99))
            y += 32
        elif it["kind"] == "embedded_image":
            draw.text((40, y), f"[Embedded Image: {it['image_filename']}]", fill=(180, 80, 20))
            y += 32
        if y > 920:
            break

    img.save(target_path, format="JPEG", quality=90)

