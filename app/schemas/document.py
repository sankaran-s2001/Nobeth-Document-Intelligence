from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import uuid


class NormalizedBBox(BaseModel):
    x: float = Field(ge=0.0, le=1.0, description="Left coordinate (0.0 to 1.0)")
    y: float = Field(ge=0.0, le=1.0, description="Top coordinate (0.0 to 1.0)")
    width: float = Field(ge=0.0, le=1.0, description="Width (0.0 to 1.0)")
    height: float = Field(ge=0.0, le=1.0, description="Height (0.0 to 1.0)")


class UncertaintyItem(BaseModel):
    id: str = Field(default_factory=lambda: f"unc-{uuid.uuid4().hex[:8]}")
    text: str
    reason: str
    page_number: int
    bbox: Optional[NormalizedBBox] = None
    suggested_alternatives: List[str] = Field(default_factory=list)


class TableCell(BaseModel):
    row: int
    col: int
    text: str
    cleaned_text: Optional[str] = None
    is_header: bool = False
    row_span: int = 1
    col_span: int = 1


class TableBlockData(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    cleaned_headers: Optional[List[str]] = None
    cleaned_rows: Optional[List[List[str]]] = None


class ListItem(BaseModel):
    order: int = 1
    verbatim_text: str = ""
    cleaned_text: Optional[str] = None
    list_type: str = "bullet"
    is_checked: Optional[bool] = None
    level: int = 0

    @field_validator("list_type", mode="before")
    @classmethod
    def normalize_list_type(cls, v: Any) -> str:
        s = str(v).lower().strip()
        if s in ("numbered", "number", "ordered", "digits", "roman", "alpha"):
            return "numbered"
        elif s in ("checkbox", "check", "task", "todo", "box"):
            return "checkbox"
        else:
            # Safely maps 'bullet', 'dash', 'hyphen', 'disc', 'dot', 'star', etc.
            return "bullet"


class KeyValuePair(BaseModel):
    key: str
    value: str
    cleaned_key: Optional[str] = None
    cleaned_value: Optional[str] = None


class LanguageInfo(BaseModel):
    code: str
    name: str
    script: str = "Latin"
    is_primary: bool = False


BlockType = Literal[
    "title",
    "heading",
    "subheading",
    "paragraph",
    "list",
    "table",
    "key_value",
    "equation",
    "form_field",
    "diagram_caption",
    "marginal_note",
    "signature",
]

ReviewStatus = Literal["clear", "needs_review", "unreadable"]
SourceType = Literal["handwritten", "printed", "mixed"]


class DocumentBlock(BaseModel):
    id: str = Field(default_factory=lambda: f"blk-{uuid.uuid4().hex[:8]}")
    type: BlockType = "paragraph"
    reading_order: int = 0
    page_number: int = 1
    bbox: Optional[NormalizedBBox] = None
    language: str = "en"
    source_type: SourceType = "handwritten"
    verbatim_text: str = ""
    cleaned_text: str = ""
    uncertainties: List[UncertaintyItem] = Field(default_factory=list)
    review_status: ReviewStatus = "clear"
    table_data: Optional[TableBlockData] = None
    list_items: Optional[List[ListItem]] = None
    key_values: Optional[List[KeyValuePair]] = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: Any) -> str:
        s = str(v).lower().strip()
        valid_types = {
            "title",
            "heading",
            "subheading",
            "paragraph",
            "list",
            "table",
            "key_value",
            "equation",
            "form_field",
            "diagram_caption",
            "marginal_note",
            "signature",
        }
        if s in valid_types:
            return s
        if s in ("header", "h1", "h2", "h3", "section_heading"):
            return "heading"
        if s in ("subheader", "subtitle"):
            return "subheading"
        if s in ("math", "formula", "latex"):
            return "equation"
        if s in ("kv", "pair", "attribute"):
            return "key_value"
        return "paragraph"

    @field_validator("review_status", mode="before")
    @classmethod
    def normalize_review_status(cls, v: Any) -> str:
        s = str(v).lower().strip()
        if s in ("needs_review", "review", "uncertain", "unclear", "warning"):
            return "needs_review"
        if s in ("unreadable", "illegible"):
            return "unreadable"
        return "clear"

    @field_validator("source_type", mode="before")
    @classmethod
    def normalize_source_type(cls, v: Any) -> str:
        s = str(v).lower().strip()
        if s in ("handwritten", "printed", "mixed"):
            return s
        return "handwritten"


class DocumentPage(BaseModel):
    page_number: int = 1
    width: int = 800
    height: int = 1100
    preview_filename: Optional[str] = None
    blocks: List[DocumentBlock] = Field(default_factory=list)


class ProcessingMetadata(BaseModel):
    extraction_model: str = ""
    cleaning_model: str = ""
    fallback_used: bool = False
    extraction_duration_ms: int = 0
    cleaning_duration_ms: int = 0
    total_duration_ms: int = 0
    warnings: List[str] = Field(default_factory=list)
    validation_notes: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


class MasterDocument(BaseModel):
    schema_version: str = "1.0"
    document_id: str = Field(default_factory=lambda: f"doc-{uuid.uuid4().hex[:12]}")
    job_id: str = ""
    original_filename: str = ""
    file_format: str = ""
    file_size_bytes: int = 0
    page_count: int = 1
    document_title: str = "Untitled Document"
    document_type: str = "general_handwritten_document"
    languages: List[LanguageInfo] = Field(default_factory=list)
    pages: List[DocumentPage] = Field(default_factory=list)
    processing: ProcessingMetadata = Field(default_factory=ProcessingMetadata)
    user_edited: bool = False
    original_backup: Optional[Dict[str, Any]] = None

    def get_all_blocks(self) -> List[DocumentBlock]:
        blocks = []
        for page in sorted(self.pages, key=lambda p: p.page_number):
            for block in sorted(page.blocks, key=lambda b: b.reading_order):
                blocks.append(block)
        return blocks

    def get_block_by_id(self, block_id: str) -> Optional[DocumentBlock]:
        for page in self.pages:
            for block in page.blocks:
                if block.id == block_id:
                    return block
        return None

    def get_total_uncertainties(self) -> int:
        count = 0
        for block in self.get_all_blocks():
            count += len(block.uncertainties)
            if block.review_status in ("needs_review", "unreadable"):
                count += 1
        return count

    def get_plain_text(self, mode: Literal["verbatim", "cleaned"] = "cleaned") -> str:
        lines: List[str] = []
        for page in sorted(self.pages, key=lambda p: p.page_number):
            if len(self.pages) > 1:
                lines.append(f"--- Page {page.page_number} ---")
            for block in sorted(page.blocks, key=lambda b: b.reading_order):
                txt = block.cleaned_text if mode == "cleaned" else block.verbatim_text
                if not txt:
                    txt = block.verbatim_text
                
                if block.type in ("title", "heading"):
                    lines.append(f"\n# {txt}\n")
                elif block.type == "subheading":
                    lines.append(f"\n## {txt}\n")
                elif block.type == "list" and block.list_items:
                    for item in block.list_items:
                        itxt = item.cleaned_text if (mode == "cleaned" and item.cleaned_text) else item.verbatim_text
                        prefix = "- "
                        if item.list_type == "numbered":
                            prefix = f"{item.order}. "
                        elif item.list_type == "checkbox":
                            prefix = "[x] " if item.is_checked else "[ ] "
                        lines.append(f"{'  ' * item.level}{prefix}{itxt}")
                elif block.type == "table" and block.table_data:
                    td = block.table_data
                    headers = (td.cleaned_headers if mode == "cleaned" and td.cleaned_headers else td.headers) or []
                    rows = (td.cleaned_rows if mode == "cleaned" and td.cleaned_rows else td.rows) or []
                    if headers:
                        lines.append(" | ".join(headers))
                        lines.append(" | ".join(["---"] * len(headers)))
                    for r in rows:
                        lines.append(" | ".join(r))
                elif block.type == "key_value" and block.key_values:
                    for kv in block.key_values:
                        k = kv.cleaned_key if mode == "cleaned" and kv.cleaned_key else kv.key
                        v = kv.cleaned_value if mode == "cleaned" and kv.cleaned_value else kv.value
                        lines.append(f"{k}: {v}")
                else:
                    lines.append(txt)
            lines.append("")
        return "\n".join(lines).strip()

