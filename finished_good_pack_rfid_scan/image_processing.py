"""Decode untrusted images and persist only metadata-free WebP derivatives."""
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from finished_good_pack_rfid_scan.errors import RfidError

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000


def optimize(content):
    if not content or len(content) > MAX_BYTES:
        raise RfidError("error.photo_size", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                    raise RfidError("error.photo_format")
                if source.width * source.height > MAX_PIXELS:
                    raise RfidError("error.photo_size", 413)
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
                converted = oriented.convert(mode)
                converted.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                # A fresh image cannot inherit EXIF, ICC, XMP or comments.
                clean = Image.new(mode, converted.size)
                clean.paste(converted)
                full = BytesIO()
                clean.save(full, "WEBP", quality=80, method=6)
                width, height = clean.size
                clean.thumbnail((320, 320), Image.Resampling.LANCZOS)
                thumbnail = BytesIO()
                clean.save(thumbnail, "WEBP", quality=80, method=6)
                return full.getvalue(), thumbnail.getvalue(), width, height
    except RfidError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise RfidError("error.photo_size", 413) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise RfidError("error.photo_format") from None
