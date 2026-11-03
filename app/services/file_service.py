import os
import shutil
import uuid
from pathlib import Path
from typing import Tuple, Optional, Dict
from fastapi import UploadFile, HTTPException
from app.config import config

# Supported Signatures (Magic Bytes)
SIGNATURES: Dict[str, list[bytes]] = {
    "jpg": [b"\xFF\xD8\xFF"],
    "jpeg": [b"\xFF\xD8\xFF"],
    "png": [b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A"],
    "pdf": [b"\x25\x50\x44\x46"],  # %PDF
    "docx": [b"\x50\x4B\x03\x04"],  # PK.. (ZIP archive)
}

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "docx"}


class FileService:
    @staticmethod
    def detect_format_from_bytes(header: bytes, filename: str) -> str:
        """Validates file magic bytes against allowed extensions."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        
        # Check signatures
        detected = None
        for fmt, sigs in SIGNATURES.items():
            for sig in sigs:
                if header.startswith(sig):
                    detected = fmt
                    break
            if detected:
                break
        
        if detected is None:
            # Check for JPEG variations
            if header[:2] == b"\xFF\xD8":
                detected = "jpg"
            elif header[:4] == b"%PDF":
                detected = "pdf"
            elif header[:4] == b"PK\x03\x04":
                detected = "docx"

        if detected == "jpeg":
            detected = "jpg"

        if not detected:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported or corrupted file format. Allowed formats: JPG, JPEG, PNG, PDF, DOCX.",
            )

        # Disallow macro files disguised as docx
        if ext == "docm" or filename.lower().endswith(".docm"):
            raise HTTPException(
                status_code=400,
                detail="Macro-enabled documents (.docm) are not supported for security reasons.",
            )

        # Extension match check: must match signature exactly (treating jpg/jpeg as equivalent)
        is_jpeg_match = ext in ("jpg", "jpeg") and detected == "jpg"
        if ext == detected or is_jpeg_match:
            return detected

        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' does not match detected file signature '{detected}'.",
        )

    @classmethod
    async def save_uploaded_file(cls, upload_file: UploadFile) -> Tuple[str, str, Path, int]:
        """
        Validates and saves an uploaded file into a private job directory.
        Returns: (job_id, file_format, saved_file_path, file_size_bytes)
        """
        if not upload_file.filename:
            raise HTTPException(status_code=400, detail="No file selected.")

        # Read initial bytes to check signature and size
        max_bytes = config.max_upload_mb * 1024 * 1024
        header = await upload_file.read(32)
        if not header:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        file_format = cls.detect_format_from_bytes(header, upload_file.filename)

        # Generate unique job id and directory
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job_dir = config.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "previews").mkdir(exist_ok=True)
        (job_dir / "extracted_assets").mkdir(exist_ok=True)
        (job_dir / "exports").mkdir(exist_ok=True)

        # Safe local filename
        safe_name = f"source.{file_format}"
        target_path = job_dir / safe_name

        # Stream rest of file and check size limit
        bytes_written = len(header)
        with open(target_path, "wb") as f:
            f.write(header)
            while True:
                chunk = await upload_file.read(1024 * 1024)  # 1MB chunk
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    # Cleanup and reject
                    f.close()
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {config.max_upload_mb} MB.",
                    )
                f.write(chunk)

        return job_id, file_format, target_path, bytes_written

    @staticmethod
    def get_job_dir(job_id: str) -> Path:
        """Returns the private filesystem directory for a job."""
        # Sanitize job_id to prevent path traversal
        clean_id = Path(job_id).name
        return config.jobs_dir / clean_id

    @staticmethod
    def delete_job_files(job_id: str) -> bool:
        """Safely removes all local files associated with a job."""
        clean_id = Path(job_id).name
        job_dir = config.jobs_dir / clean_id
        if job_dir.exists() and job_dir.is_dir():
            shutil.rmtree(job_dir, ignore_errors=True)
            return True
        return False
