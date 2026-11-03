import asyncio
import json
import logging
import re
import time
from typing import List, Dict, Any, Tuple, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import config
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

logger = logging.getLogger("nobeth.gemini_service")


class GeminiService:
    _client: Optional[genai.Client] = None

    @classmethod
    def get_client(cls) -> genai.Client:
        """Returns or creates a reusable Gemini Client instance."""
        if cls._client is None:
            api_key = config.gemini_api_key
            if not api_key:
                raise ValueError(
                    "Gemini API key is not configured. Please set GEMINI_API_KEY in the .env file."
                )
            cls._client = genai.Client(api_key=api_key)
        return cls._client

    @classmethod
    def is_configured(cls) -> bool:
        """Returns True if a non-empty API key is present."""
        return bool(config.gemini_api_key and config.gemini_api_key.strip())

    @classmethod
    def reload_client(cls) -> None:
        """Forces recreation of the client if config changes."""
        cls._client = None

    @classmethod
    async def extract_page_content(
        cls,
        image_bytes: bytes,
        page_number: int = 1,
        page_width: int = 800,
        page_height: int = 1100,
        additional_context: str = "",
    ) -> Tuple[Dict[str, Any], str, bool, int]:
        """
        Calls Gemini Multimodal to transcribe and structure document content.
        Tries primary model first; if recoverable failure, tries fallback model.
        Returns: (parsed_data_dict, actual_model_used, fallback_used, duration_ms)
        """
        client = cls.get_client()

        system_instruction = (
            "You are Nobeth Document Intelligence, an enterprise document understanding and "
            "handwriting transcription system created for Nobeth Analytics.\n"
            "Analyze the document image, identify structure, detect language and document type, "
            "and extract handwritten and printed text with verbatim accuracy.\n\n"
            "STRICT RULES:\n"
            "1. VERBATIM ACCURACY: Preserve the exact words, original spelling, grammar mistakes, "
            "punctuation, numbers, amounts, dates, and language. Do NOT paraphrase, summarize, or invent words.\n"
            "2. NO TRANSLATION: Keep original languages (English, Tamil, Hindi, or mixed). Never translate.\n"
            "3. UNCERTAIN HANDWRITING: If text is unclear, messy, or ambiguous (e.g. 1 vs 7, 0 vs O, rn vs m), "
            "transcribe best estimate or '[unclear]', and add an entry to 'uncertainties' with a helpful reason. "
            "Set review_status to 'needs_review' or 'unreadable'.\n"
            "4. STRUCTURE RECONSTRUCTION: Classify each content block into: 'title', 'heading', 'subheading', "
            "'paragraph', 'list', 'table', 'key_value', 'equation', 'form_field', 'marginal_note', 'signature'.\n"
            "   - If tables are present, structure into table_data (headers, rows).\n"
            "   - If lists are present, structure into list_items (order, verbatim_text, list_type, is_checked, level).\n"
            "   - If mathematical or scientific formulas appear, use LaTeX notation (e.g., $x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$).\n"
            "   - For receipts/invoices/forms, extract key_values (merchant, date, total, tax, line items).\n"
            "5. BOUNDING BOXES: Provide normalized bounding boxes (x, y, width, height between 0.0 and 1.0) when visible.\n"
            "6. DOCUMENT TYPE: Identify document_type (e.g., student_notes, general_notes, shopping_list, "
            "receipt, bill, invoice, personal_letter, meeting_notes, form, application, business_document, general_handwritten_document).\n"
            "7. Return strictly valid JSON matching the specified JSON schema."
        )

        user_prompt = (
            f"Analyze page {page_number} of this document. "
            f"{additional_context}\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "document_title": "string",\n'
            '  "document_type": "string",\n'
            '  "languages": [\n'
            '    {"code": "en", "name": "English", "script": "Latin", "is_primary": true}\n'
            "  ],\n"
            '  "blocks": [\n'
            "    {\n"
            '      "id": "blk-1",\n'
            '      "type": "heading | paragraph | list | table | key_value | equation | form_field | marginal_note",\n'
            '      "reading_order": 1,\n'
            '      "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.05},\n'
            '      "language": "en",\n'
            '      "source_type": "handwritten | printed | mixed",\n'
            '      "verbatim_text": "Exact text here",\n'
            '      "uncertainties": [\n'
            '        {"text": "word", "reason": "ambiguous cursive stroke", "page_number": 1}\n'
            "      ],\n"
            '      "review_status": "clear | needs_review | unreadable",\n'
            '      "table_data": {"headers": ["Col 1", "Col 2"], "rows": [["A", "B"]]},\n'
            '      "list_items": [{"order": 1, "verbatim_text": "Item", "list_type": "bullet", "is_checked": null, "level": 0}],\n'
            '      "key_values": [{"key": "Total", "value": "$10.00"}]\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

        gen_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system_instruction,
            temperature=0.1,
        )

        models_to_try = [
            (config.gemini_primary_model, False),
            (config.gemini_fallback_model, True),
        ]

        last_error = None
        for model_id, is_fallback in models_to_try:
            start_t = time.perf_counter()
            try:
                logger.info(
                    "Submitting extraction to %s (fallback=%s, page=%d)",
                    model_id,
                    is_fallback,
                    page_number,
                )
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_id,
                        contents=[image_part, user_prompt],
                        config=gen_config,
                    ),
                    timeout=60.0,
                )

                duration_ms = int((time.perf_counter() - start_t) * 1000)

                raw_text = response.text or "{}"
                parsed_json = cls._safe_parse_json(raw_text)
                if not parsed_json or "blocks" not in parsed_json:
                    raise ValueError(f"Model returned invalid or empty document JSON: {raw_text[:200]}")

                logger.info(
                    "Extraction successful via %s in %dms (page %d, %d blocks)",
                    model_id,
                    duration_ms,
                    page_number,
                    len(parsed_json.get("blocks", [])),
                )
                return parsed_json, model_id, is_fallback, duration_ms

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                last_error = e
                logger.warning(
                    "Model %s failed during extraction (page %d, duration %dms): %s",
                    model_id,
                    page_number,
                    duration_ms,
                    str(e),
                )
                if not is_fallback:
                    logger.info("Attempting configured fallback model: %s", config.gemini_fallback_model)
                    await asyncio.sleep(1.0)  # Brief backoff before fallback
                    continue
                else:
                    break

        raise RuntimeError(
            f"Document extraction failed on both primary ({config.gemini_primary_model}) "
            f"and fallback ({config.gemini_fallback_model}) models. Error: {str(last_error)}"
        )

    @classmethod
    async def generate_cleaned_version(
        cls,
        document_title: str,
        blocks: List[DocumentBlock],
        document_type: str,
    ) -> Tuple[Dict[str, Any], str, bool, int]:
        """
        Generates the cleaned version strictly from validated verbatim content.
        Attempts primary model, with fallback on failure.
        """
        client = cls.get_client()

        system_instruction = (
            "You are Nobeth Document Intelligence Cleaned Version Generator for Nobeth Analytics.\n"
            "Your task is to take extracted verbatim document blocks and generate an organized, "
            "professionally formatted digital version.\n\n"
            "STRICT RULES:\n"
            "1. START FROM VERBATIM: Base all cleaned content strictly on the provided verbatim text.\n"
            "2. GRAMMAR & SPELLING: Confidently correct clear spelling errors and grammar mistakes. "
            "Improve punctuation, casing, and sentence structure.\n"
            "3. PRESERVE MEANING & FACTS: Do NOT summarize, remove information, or introduce new facts.\n"
            "4. PRESERVE CRITICAL VALUES: Never change numbers, amounts, dates, names, equations, "
            "codes, or key values without explicit evidence.\n"
            "5. NO TRANSLATION: Preserve the original languages (English, Tamil, Hindi, etc.).\n"
            "6. Return strictly valid JSON mapping block IDs to their cleaned versions."
        )

        # Build compact representation of verbatim blocks
        simplified_blocks = []
        for b in blocks:
            b_dict = {
                "id": b.id,
                "type": b.type,
                "verbatim_text": b.verbatim_text,
            }
            if b.table_data:
                b_dict["table_data"] = {
                    "headers": b.table_data.headers,
                    "rows": b.table_data.rows,
                }
            if b.list_items:
                b_dict["list_items"] = [
                    {"order": li.order, "text": li.verbatim_text, "type": li.list_type}
                    for li in b.list_items
                ]
            if b.key_values:
                b_dict["key_values"] = [{"key": kv.key, "value": kv.value} for kv in b.key_values]
            simplified_blocks.append(b_dict)

        user_prompt = (
            f"Generate the cleaned version for this {document_type} document.\n"
            f"Title: {document_title}\n"
            f"Verbatim Blocks Input:\n{json.dumps(simplified_blocks, ensure_ascii=False, indent=1)}\n\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "cleaned_title": "string",\n'
            '  "blocks": [\n'
            "    {\n"
            '      "id": "block id from input",\n'
            '      "cleaned_text": "professionally corrected and formatted text",\n'
            '      "cleaned_table_data": {"headers": [...], "rows": [[...]]},\n'
            '      "cleaned_list_items": [{"order": 1, "cleaned_text": "..."}],\n'
            '      "cleaned_key_values": [{"key": "...", "cleaned_key": "...", "cleaned_value": "..."}]\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        gen_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system_instruction,
            temperature=0.1,
        )

        models_to_try = [
            (config.gemini_primary_model, False),
            (config.gemini_fallback_model, True),
        ]

        last_error = None
        for model_id, is_fallback in models_to_try:
            start_t = time.perf_counter()
            try:
                logger.info(
                    "Submitting cleaning to %s (fallback=%s, blocks=%d)",
                    model_id,
                    is_fallback,
                    len(blocks),
                )
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_id,
                        contents=[user_prompt],
                        config=gen_config,
                    ),
                    timeout=60.0,
                )

                duration_ms = int((time.perf_counter() - start_t) * 1000)
                raw_text = response.text or "{}"
                parsed_json = cls._safe_parse_json(raw_text)
                if not parsed_json or "blocks" not in parsed_json:
                    raise ValueError(f"Model returned invalid or empty cleaned JSON: {raw_text[:200]}")

                logger.info(
                    "Cleaning successful via %s in %dms (%d blocks cleaned)",
                    model_id,
                    duration_ms,
                    len(parsed_json.get("blocks", [])),
                )
                return parsed_json, model_id, is_fallback, duration_ms

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_t) * 1000)
                last_error = e
                logger.warning(
                    "Model %s failed during cleaning (duration %dms): %s",
                    model_id,
                    duration_ms,
                    str(e),
                )
                if not is_fallback:
                    logger.info("Attempting configured fallback model for cleaning: %s", config.gemini_fallback_model)
                    await asyncio.sleep(1.0)
                    continue
                else:
                    break

        raise RuntimeError(
            f"Document cleaning failed on both primary ({config.gemini_primary_model}) "
            f"and fallback ({config.gemini_fallback_model}) models. Error: {str(last_error)}"
        )

    @staticmethod
    def _safe_parse_json(text: str) -> Dict[str, Any]:
        """Parses JSON safely, stripping code fences or leading/trailing noise if present."""
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Attempt to extract outermost { ... }
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

