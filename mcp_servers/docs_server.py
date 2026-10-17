"""Docs MCP Server for DispatchMind.

Provides document and file storage operations (invoices, e-way bills, POD photos)
stored in local storage (data/docs/) or GCS with reliable local fallback.
All operations are resiliently wrapped.
"""

import base64
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict
import uuid

from fastmcp import FastMCP
from core.config import BASE_DIR, GCS_BUCKET
from core.resilience import resilient

logger = logging.getLogger(__name__)

mcp = FastMCP("DocsServer")

DOCS_DIR = BASE_DIR / "data" / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def fallback_save_file(filename: str, content_base64: str, category: str = "general") -> Dict[str, Any]:
    """Fallback file saver saving directly to local data/docs directory."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    file_id = f"doc_{uuid.uuid4().hex[:8]}"
    safe_name = Path(filename).name
    save_filename = f"{file_id}_{safe_name}"
    target_path = DOCS_DIR / save_filename

    raw_bytes = base64.b64decode(content_base64)
    with open(target_path, "wb") as f:
        f.write(raw_bytes)

    return {
        "file_id": file_id,
        "filename": safe_name,
        "path": str(target_path),
        "url": f"file:///{target_path.as_posix()}",
        "category": category,
        "size_bytes": len(raw_bytes),
        "storage": "local_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fallback_get_file(file_id_or_path: str) -> Dict[str, Any]:
    """Fallback file retrieval from local data/docs directory."""
    target_path = Path(file_id_or_path)

    # If it is not a direct path, check by file_id prefix or filename in DOCS_DIR
    if not target_path.exists():
        candidates = list(DOCS_DIR.glob(f"*{file_id_or_path}*"))
        if candidates:
            target_path = candidates[0]
        else:
            raise FileNotFoundError(f"File not found for identifier: {file_id_or_path}")

    with open(target_path, "rb") as f:
        content_bytes = f.read()

    return {
        "file_id": file_id_or_path,
        "filename": target_path.name,
        "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
        "size_bytes": len(content_bytes),
        "path": str(target_path),
    }


@mcp.tool()
@resilient(fallback=fallback_save_file, retries=2)
def save_file(filename: str, content_base64: str, category: str = "general") -> Dict[str, Any]:
    """Save a document, e-way bill, or delivery photo from base64 content.

    Args:
        filename: Original or descriptive filename.
        content_base64: Base64-encoded file bytes.
        category: Document category (e.g., 'invoice', 'eway_bill', 'pod', 'general').

    Returns:
        Dict with 'file_id', 'path', and 'url'.
    """
    # If GCS_BUCKET is configured, attempt upload, else use local folder
    if GCS_BUCKET:
        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            file_id = f"doc_{uuid.uuid4().hex[:8]}"
            blob_name = f"{category}/{file_id}_{Path(filename).name}"
            blob = bucket.blob(blob_name)
            raw_bytes = base64.b64decode(content_base64)
            blob.upload_from_string(raw_bytes)

            return {
                "file_id": file_id,
                "filename": filename,
                "path": blob_name,
                "url": f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_name}",
                "category": category,
                "size_bytes": len(raw_bytes),
                "storage": "gcs",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("GCS upload failed (%s). Falling back to local docs storage.", exc)

    return fallback_save_file(filename, content_base64, category)


@mcp.tool()
@resilient(fallback=fallback_get_file, retries=2)
def get_file(file_id_or_path: str) -> Dict[str, Any]:
    """Retrieve a stored document and return base64-encoded contents.

    Args:
        file_id_or_path: Stored file ID, relative path, or absolute path.

    Returns:
        Dict with 'filename' and 'content_base64'.
    """
    if GCS_BUCKET and not Path(file_id_or_path).exists():
        try:
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            blob = bucket.blob(file_id_or_path)
            if blob.exists():
                content_bytes = blob.download_as_bytes()
                return {
                    "file_id": file_id_or_path,
                    "filename": Path(file_id_or_path).name,
                    "content_base64": base64.b64encode(content_bytes).decode("utf-8"),
                    "size_bytes": len(content_bytes),
                    "path": file_id_or_path,
                }
        except Exception as exc:
            logger.warning("GCS retrieval failed (%s). Attempting local lookup.", exc)

    return fallback_get_file(file_id_or_path)


if __name__ == "__main__":
    mcp.run()
