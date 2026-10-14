from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from ..config import settings
from ..document_ingestion import (
    MAX_DOCUMENT_BYTES,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    ingest_document,
)
from ..schemas import DocumentIngestResponse

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _check_api_key(x_api_key: str | None) -> None:
    if settings.ingest_api_key and x_api_key != settings.ingest_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.post("/ingest", response_model=DocumentIngestResponse)
async def ingest_uploaded_document(
    document_id: str = Form(...),
    name: str = Form(...),
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
) -> DocumentIngestResponse:
    _check_api_key(x_api_key)

    if not name.strip():
        raise HTTPException(status_code=422, detail="Document name cannot be empty.")
    filename = file.filename or ""
    if file.size is not None and file.size > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="The maximum document size is 25 MB.")
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_DOCUMENT_EXTENSIONS):
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Supported extensions: {supported}.",
        )

    content = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="The maximum document size is 25 MB.")
    try:
        chunks_indexed = await ingest_document(
            document_id=document_id,
            name=name.strip(),
            filename=filename,
            content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DocumentIngestResponse(
        document_id=document_id,
        status="verified",
        chunks_indexed=chunks_indexed,
    )
