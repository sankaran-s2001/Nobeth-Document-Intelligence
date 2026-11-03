import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.gemini_service import GeminiService
from app.config import config


def test_gemini_fallback_sequence():
    """
    Verifies that a recoverable failure on the primary model (gemini-3.5-flash-lite)
    automatically triggers the fallback model (gemini-3.1-flash-lite) with identical schema,
    and returns fallback_used=True and the fallback model identifier.
    """
    mock_success_json = {
        "document_title": "Biology Lecture Notes",
        "document_type": "student_notes",
        "languages": [{"code": "en", "name": "English", "script": "Latin", "is_primary": True}],
        "blocks": [
            {
                "id": "blk-1",
                "type": "heading",
                "reading_order": 1,
                "verbatim_text": "Cell Structure and Mitosis",
                "review_status": "clear",
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_success_json)

    # Primary model throws temporary service error; fallback succeeds
    call_history = []

    async def fake_generate_content(model, contents, config):
        call_history.append(model)
        if model == "gemini-3.5-flash-lite":
            raise RuntimeError("503 Service Unavailable / Rate Limit Exceeded")
        elif model == "gemini-3.1-flash-lite":
            return mock_response
        raise ValueError(f"Unexpected model: {model}")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_generate_content)

    async def run_test():
        with patch.object(GeminiService, "get_client", return_value=mock_client):
            return await GeminiService.extract_page_content(
                image_bytes=b"fake-image-bytes",
                page_number=1,
            )

    parsed_data, actual_model, fallback_used, duration_ms = asyncio.run(run_test())

    # Assertions
    assert call_history == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    assert fallback_used is True
    assert actual_model == "gemini-3.1-flash-lite"
    assert parsed_data["document_title"] == "Biology Lecture Notes"
    assert parsed_data["blocks"][0]["verbatim_text"] == "Cell Structure and Mitosis"
