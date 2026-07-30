import hashlib
import os
import tempfile
from pathlib import Path


SUPPORTED_LOG_SUFFIXES = {".bin", ".ulg"}


def store_uploaded_log(filename, content, root=Path("data/uploads")):
    """Persist an uploaded log by content hash and return its local path."""
    safe_name = Path(str(filename).replace("\\", "/")).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_LOG_SUFFIXES:
        raise ValueError("仅支持 .bin 和 .ulg 日志文件")

    payload = memoryview(content)
    digest = hashlib.sha256(payload).hexdigest()
    upload_root = Path(root)
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / f"{digest}{suffix}"

    if target.exists():
        return str(target)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(upload_root),
            prefix=f".{digest}-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()

    return str(target)
