import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from PIL import Image, ImageOps, ImageEnhance
from fastapi import HTTPException
from app.config import config

logger = logging.getLogger("nobeth.image_service")

# Safeguard against decompression bombs
Image.MAX_IMAGE_PIXELS = config.max_image_pixels


class ImageService:
    @staticmethod
    def process_image(
        image_path: Path, output_preview_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Loads, checks EXIF orientation, validates dimensions,
        and optionally creates a web-optimized preview.
        """
        try:
            with Image.open(image_path) as img:
                # 1. Check pixels
                total_pixels = img.width * img.height
                if total_pixels > config.max_image_pixels:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Image resolution ({img.width}x{img.height}) exceeds safety limit.",
                    )

                if img.width < 50 or img.height < 50:
                    raise HTTPException(
                        status_code=400,
                        detail="Image resolution is too low to extract readable handwriting.",
                    )

                # 2. Apply EXIF orientation
                try:
                    corrected = ImageOps.exif_transpose(img)
                    if corrected is not None:
                        img = corrected
                except Exception as e:
                    logger.warning("EXIF transpose skipped: %s", e)

                width, height = img.size

                # 3. Create web preview and normalized RGB image if preview path given
                if output_preview_path:
                    # Convert to RGB if needed (handling RGBA, CMYK, Palette)
                    if img.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        proc_img = background
                    elif img.mode != "RGB":
                        proc_img = img.convert("RGB")
                    else:
                        proc_img = img.copy()

                    # Save high-quality preview for browser display
                    proc_img.save(output_preview_path, format="JPEG", quality=90, optimize=True)

                return {
                    "width": width,
                    "height": height,
                    "format": img.format or "JPEG",
                    "mode": img.mode,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process image %s: %s", image_path, e)
            raise HTTPException(
                status_code=400,
                detail=f"Could not decode image file: {str(e)}",
            )

    @staticmethod
    def get_analysis_bytes(image_path: Path, max_dimension: int = 2400) -> bytes:
        """
        Prepares high-resolution JPEG bytes for multimodal Gemini input,
        resizing smoothly only if larger than max_dimension to preserve network quota.
        """
        with Image.open(image_path) as img:
            try:
                corrected = ImageOps.exif_transpose(img)
                if corrected is not None:
                    img = corrected
            except Exception:
                pass

            if img.mode != "RGB":
                if img.mode in ("RGBA", "LA"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[-1])
                    img = bg
                else:
                    img = img.convert("RGB")

            # Resize if huge while maintaining aspect ratio
            if max(img.width, img.height) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92, optimize=True)
            return buf.getvalue()

