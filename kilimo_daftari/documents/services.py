import logging
import mimetypes
from pathlib import Path

import httpx
from django.conf import settings

from .models import Document

logger = logging.getLogger(__name__)


def process_document(document: Document) -> bool:
    document.status = Document.STATUS_PROCESSING
    document.processing_error = ""
    document.save(update_fields=["status", "processing_error", "updated_at"])

    url = f"{settings.AI_LAYER_BASE_URL}{settings.AI_LAYER_DOCUMENT_INGEST_PATH}"
    headers = {}
    if settings.AI_LAYER_INGEST_API_KEY:
        headers["X-API-Key"] = settings.AI_LAYER_INGEST_API_KEY

    try:
        with document.file.open("rb") as file_handle:
            response = httpx.post(
                url,
                data={"document_id": str(document.pk), "name": document.name},
                files={
                    "file": (
                        Path(document.file.name).name,
                        file_handle,
                        mimetypes.guess_type(document.file.name)[0]
                        or "application/octet-stream",
                    )
                },
                headers=headers,
                timeout=settings.AI_LAYER_DOCUMENT_TIMEOUT_SECONDS,
            )

        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(
                f"AI Layer returned HTTP {response.status_code}: {detail}"
            )

        result = response.json()
        if (
            not isinstance(result, dict)
            or result.get("document_id") != str(document.pk)
            or result.get("status") != Document.STATUS_VERIFIED
            or not isinstance(result.get("chunks_indexed"), int)
            or result["chunks_indexed"] < 1
        ):
            raise ValueError("AI Layer returned an invalid document-ingestion response.")

    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
        document.status = Document.STATUS_FAILED
        document.processing_error = str(exc)[:4000]
        document.save(
            update_fields=["status", "processing_error", "updated_at"]
        )
        logger.warning("Document %s failed AI Layer processing: %s", document.pk, exc)
        return False

    document.status = Document.STATUS_VERIFIED
    document.chunks_indexed = result["chunks_indexed"]
    document.processing_error = ""
    document.save(
        update_fields=[
            "status",
            "chunks_indexed",
            "processing_error",
            "updated_at",
        ]
    )
    return True
