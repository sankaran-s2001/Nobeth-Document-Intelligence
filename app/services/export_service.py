import io
import json
import logging
from pathlib import Path
from typing import Literal, Optional
from fpdf import FPDF
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from app.config import config
from app.schemas.document import MasterDocument, DocumentBlock

logger = logging.getLogger("nobeth.export_service")


class ExportService:
    @classmethod
    def generate_docx(
        cls,
        doc: MasterDocument,
        version: Literal["verbatim", "cleaned"] = "cleaned",
        style: Literal["professional", "layout"] = "professional",
    ) -> bytes:
        """
        Generates a DOCX document supporting both verbatim and cleaned content,
        and both Clean Professional and Layout-Preserved presentation styles.
        """
        word_doc = docx.Document()

        # Configure margins (1 inch for professional, 0.75 for layout)
        margin = 1.0 if style == "professional" else 0.75
        for section in word_doc.sections:
            section.top_margin = Inches(margin)
            section.bottom_margin = Inches(margin)
            section.left_margin = Inches(margin)
            section.right_margin = Inches(margin)

            # Header / Footer
            header = section.header
            header_p = header.paragraphs[0]
            header_p.text = f"Nobeth Document Intelligence | {doc.document_title}"
            header_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if header_p.runs:
                header_p.runs[0].font.size = Pt(8.5)
                header_p.runs[0].font.color.rgb = RGBColor(120, 120, 120)

            footer = section.footer
            footer_p = footer.paragraphs[0]
            footer_p.text = f"Version: {version.title()} ({style.title()}) | Nobeth Analytics"
            footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if footer_p.runs:
                footer_p.runs[0].font.size = Pt(8.5)
                footer_p.runs[0].font.color.rgb = RGBColor(120, 120, 120)

        # Title
        title_p = word_doc.add_paragraph()
        title_run = title_p.add_run(doc.document_title)
        title_run.bold = True
        title_run.font.size = Pt(22)
        title_run.font.color.rgb = RGBColor(13, 94, 99)  # Nobeth Teal
        title_p.paragraph_format.space_after = Pt(4)

        # Subtitle / Document Meta
        meta_p = word_doc.add_paragraph()
        meta_run = meta_p.add_run(
            f"Type: {doc.document_type.replace('_', ' ').title()} | "
            f"Mode: {version.title()} ({style.title()}) | "
            f"Languages: {', '.join(lang.name for lang in doc.languages) if doc.languages else 'Detected'}"
        )
        meta_run.font.size = Pt(9.5)
        meta_run.font.italic = True
        meta_run.font.color.rgb = RGBColor(100, 100, 100)
        meta_p.paragraph_format.space_after = Pt(18)

        # Process each page
        for p_idx, page in enumerate(sorted(doc.pages, key=lambda p: p.page_number)):
            if p_idx > 0:
                word_doc.add_page_break()

            if len(doc.pages) > 1 and style == "professional":
                page_head = word_doc.add_paragraph()
                p_run = page_head.add_run(f"Page {page.page_number}")
                p_run.bold = True
                p_run.font.size = Pt(11)
                p_run.font.color.rgb = RGBColor(13, 94, 99)
                page_head.paragraph_format.space_before = Pt(12)
                page_head.paragraph_format.space_after = Pt(8)

            sorted_blocks = sorted(page.blocks, key=lambda b: b.reading_order)
            for block in sorted_blocks:
                cls._add_block_to_docx(word_doc, block, version=version, style=style)

        buf = io.BytesIO()
        word_doc.save(buf)
        return buf.getvalue()

    @classmethod
    def _add_block_to_docx(
        cls,
        doc: docx.Document,
        block: DocumentBlock,
        version: str,
        style: str,
    ) -> None:
        text = block.cleaned_text if version == "cleaned" else block.verbatim_text
        if not text:
            text = block.verbatim_text

        # 1. Heading
        if block.type in ("title", "heading"):
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(16 if block.type == "title" else 14)
            run.font.color.rgb = RGBColor(13, 94, 99)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            if style == "layout" and block.bbox and block.bbox.x > 0.3:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 2. Subheading
        elif block.type == "subheading":
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(12)
            run.font.color.rgb = RGBColor(40, 40, 40)
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)

        # 3. List
        elif block.type == "list" and block.list_items:
            for item in block.list_items:
                itxt = item.cleaned_text if (version == "cleaned" and item.cleaned_text) else item.verbatim_text
                p = doc.add_paragraph(style="List Bullet" if item.list_type == "bullet" else "List Number")
                p.paragraph_format.left_indent = Inches(0.25 * (item.level + 1))
                if item.list_type == "checkbox":
                    check_mark = "[x] " if item.is_checked else "[ ] "
                    c_run = p.add_run(check_mark)
                    c_run.bold = True
                p.add_run(itxt)
                p.paragraph_format.space_after = Pt(2)

        # 4. Table
        elif block.type == "table" and block.table_data:
            td = block.table_data
            headers = (td.cleaned_headers if version == "cleaned" and td.cleaned_headers else td.headers) or []
            rows = (td.cleaned_rows if version == "cleaned" and td.cleaned_rows else td.rows) or []
            
            num_cols = max(len(headers), max((len(r) for r in rows), default=0))
            if num_cols > 0:
                table = doc.add_table(rows=0, cols=num_cols)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.style = "Table Grid"

                # Header row
                if headers:
                    hdr_row = table.add_row()
                    for c_idx, h_text in enumerate(headers[:num_cols]):
                        cell = hdr_row.cells[c_idx]
                        cell.text = h_text
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
                                run.font.color.rgb = RGBColor(255, 255, 255)
                        # Teal background
                        shading = parse_xml(r'<w:shd {} w:fill="0D5E63"/>'.format(nsdecls('w')))
                        cell._tc.get_or_add_tcPr().append(shading)

                # Data rows
                for r in rows:
                    row_cells = table.add_row().cells
                    for c_idx, val in enumerate(r[:num_cols]):
                        row_cells[c_idx].text = str(val)

                doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # 5. Key-Value (Receipts / Invoices / Forms)
        elif block.type == "key_value" and block.key_values:
            kv_table = doc.add_table(rows=0, cols=2)
            kv_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for kv in block.key_values:
                k = kv.cleaned_key if (version == "cleaned" and kv.cleaned_key) else kv.key
                v = kv.cleaned_value if (version == "cleaned" and kv.cleaned_value) else kv.value
                row_cells = kv_table.add_row().cells
                r_key = row_cells[0].paragraphs[0].add_run(k)
                r_key.bold = True
                row_cells[1].paragraphs[0].add_run(v)
            doc.add_paragraph().paragraph_format.space_after = Pt(4)

        # 6. Equation
        elif block.type == "equation":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.font.name = "Cambria Math"
            run.font.size = Pt(12)
            run.font.italic = True
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)

        # 7. Standard Paragraph / Notes
        else:
            if text:
                p = doc.add_paragraph()
                if style == "layout" and block.bbox:
                    # Indent relatively based on bbox x position
                    if block.bbox.x > 0.15:
                        p.paragraph_format.left_indent = Inches(min(block.bbox.x * 3.0, 2.5))
                p.add_run(text)
                p.paragraph_format.space_after = Pt(6)

    @classmethod
    def generate_pdf(
        cls,
        doc: MasterDocument,
        version: Literal["verbatim", "cleaned"] = "cleaned",
        style: Literal["professional", "layout"] = "professional",
    ) -> bytes:
        """
        Generates a PDF using fpdf2 with Unicode font embedding (Nirmala UI)
        and complex-script shaping for English, Tamil, and Hindi.
        """
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)

        # Register Unicode fonts
        reg_font_path = config.fonts_dir / "NirmalaUI-Regular.ttf"
        bold_font_path = config.fonts_dir / "NirmalaUI-Bold.ttf"

        has_custom_fonts = reg_font_path.exists() and bold_font_path.exists()
        font_family = "Nirmala" if has_custom_fonts else "Helvetica"

        if has_custom_fonts:
            pdf.add_font("Nirmala", "", str(reg_font_path))
            pdf.add_font("Nirmala", "B", str(bold_font_path))

        pdf.add_page()

        # Header Title
        pdf.set_font(font_family, "B", 18)
        pdf.set_text_color(13, 94, 99)  # Nobeth Teal
        pdf.cell(0, 10, doc.document_title, new_x="LMARGIN", new_y="NEXT", align="L")

        # Subtitle Meta
        pdf.set_font(font_family, "", 9)
        pdf.set_text_color(100, 100, 100)
        meta = (
            f"Type: {doc.document_type.replace('_', ' ').title()} | "
            f"Mode: {version.title()} ({style.title()}) | "
            f"Nobeth Analytics"
        )
        pdf.cell(0, 6, meta, new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(4)

        # Horizontal separator
        pdf.set_draw_color(220, 220, 220)
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        # Pages and Blocks
        pdf.set_text_color(30, 30, 30)

        for p_idx, page in enumerate(sorted(doc.pages, key=lambda p: p.page_number)):
            if p_idx > 0:
                pdf.add_page()

            if len(doc.pages) > 1:
                pdf.set_font(font_family, "B", 10)
                pdf.set_text_color(13, 94, 99)
                pdf.cell(0, 7, f"Page {page.page_number}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)
                pdf.ln(2)

            sorted_blocks = sorted(page.blocks, key=lambda b: b.reading_order)
            for block in sorted_blocks:
                cls._add_block_to_pdf(pdf, block, font_family, version=version, style=style)

        # Output bytes
        pdf_bytes = bytes(pdf.output())
        return pdf_bytes

    @classmethod
    def _add_block_to_pdf(
        cls,
        pdf: FPDF,
        block: DocumentBlock,
        font_family: str,
        version: str,
        style: str,
    ) -> None:
        text = block.cleaned_text if version == "cleaned" else block.verbatim_text
        if not text:
            text = block.verbatim_text

        # 1. Heading
        if block.type in ("title", "heading"):
            pdf.ln(3)
            pdf.set_font(font_family, "B", 13)
            pdf.set_text_color(13, 94, 99)
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 30, 30)
            pdf.ln(2)

        # 2. Subheading
        elif block.type == "subheading":
            pdf.ln(2)
            pdf.set_font(font_family, "B", 11)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 30, 30)
            pdf.ln(1)

        # 3. List
        elif block.type == "list" and block.list_items:
            pdf.set_font(font_family, "", 10)
            for item in block.list_items:
                itxt = item.cleaned_text if (version == "cleaned" and item.cleaned_text) else item.verbatim_text
                prefix = "- "
                if item.list_type == "numbered":
                    prefix = f"{item.order}. "
                elif item.list_type == "checkbox":
                    prefix = "[x] " if item.is_checked else "[ ] "

                indent = 6 * (item.level + 1)
                pdf.set_x(pdf.l_margin + indent)
                pdf.multi_cell(pdf.w - pdf.r_margin - pdf.l_margin - indent, 5.5, f"{prefix}{itxt}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

        # 4. Table
        elif block.type == "table" and block.table_data:
            td = block.table_data
            headers = (td.cleaned_headers if version == "cleaned" and td.cleaned_headers else td.headers) or []
            rows = (td.cleaned_rows if version == "cleaned" and td.cleaned_rows else td.rows) or []
            num_cols = max(len(headers), max((len(r) for r in rows), default=0))

            if num_cols > 0:
                available_w = pdf.w - pdf.l_margin - pdf.r_margin
                col_w = available_w / num_cols
                row_h = 7.0

                pdf.ln(2)
                # Header row
                if headers:
                    pdf.set_font(font_family, "B", 9.5)
                    pdf.set_fill_color(13, 94, 99)
                    pdf.set_text_color(255, 255, 255)
                    for h_text in headers[:num_cols]:
                        pdf.cell(col_w, row_h, str(h_text)[:30], border=1, fill=True, align="C")
                    pdf.ln()

                # Rows
                pdf.set_font(font_family, "", 9)
                pdf.set_text_color(30, 30, 30)
                for r in rows:
                    for val in r[:num_cols]:
                        pdf.cell(col_w, row_h, str(val)[:35], border=1, align="L")
                    pdf.ln()
                pdf.ln(3)

        # 5. Key-Value
        elif block.type == "key_value" and block.key_values:
            pdf.ln(2)
            pdf.set_font(font_family, "", 9.5)
            for kv in block.key_values:
                k = kv.cleaned_key if (version == "cleaned" and kv.cleaned_key) else kv.key
                v = kv.cleaned_value if (version == "cleaned" and kv.cleaned_value) else kv.value
                pdf.set_font(font_family, "B", 9.5)
                pdf.cell(45, 6, f"{k}:", border=0)
                pdf.set_font(font_family, "", 9.5)
                pdf.cell(0, 6, str(v), border=0, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

        # 6. Paragraph / Note
        else:
            if text:
                pdf.set_font(font_family, "", 10)
                if style == "layout" and block.bbox and block.bbox.x > 0.15:
                    indent = min(block.bbox.x * 50, 40)
                    pdf.set_x(pdf.l_margin + indent)
                    pdf.multi_cell(pdf.w - pdf.r_margin - pdf.l_margin - indent, 5.5, text, new_x="LMARGIN", new_y="NEXT")
                else:
                    pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

    @classmethod
    def generate_txt(
        cls,
        doc: MasterDocument,
        version: Literal["verbatim", "cleaned"] = "cleaned",
    ) -> str:
        """Generates UTF-8 plain text export."""
        header = (
            f"====================================================\n"
            f"NOBETH DOCUMENT INTELLIGENCE\n"
            f"Document Title: {doc.document_title}\n"
            f"Document Type:  {doc.document_type}\n"
            f"Extraction Version: {version.upper()}\n"
            f"Model Used:     {doc.processing.extraction_model}\n"
            f"====================================================\n\n"
        )
        return header + doc.get_plain_text(mode=version)

    @classmethod
    def generate_json(cls, doc: MasterDocument) -> str:
        """Generates complete structured JSON export."""
        return doc.model_dump_json(indent=2)

