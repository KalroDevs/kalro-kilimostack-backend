from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..ingestion import ingest_resource
from ..schemas import AdvisoryResource, IngestResponse

router = APIRouter(prefix="/api/v1", tags=["ingest"])


def _check_api_key(x_api_key: str | None):
    if settings.ingest_api_key and x_api_key != settings.ingest_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.post("/ingest", response_model=IngestResponse)
async def ingest(resources: list[AdvisoryResource], x_api_key: str | None = Header(default=None)):
    """
    Accepts a JSON array of resources (Advisory Content Import JSON
    Specification v0.1 shape, as produced by the Django backend's
    AdvisoryResourceSerializer) and embeds/indexes each into the vector
    database. Only resources with quality_flag == 'ready_to_certify' are
    actually indexed; others are reported back as skipped.
    """
    _check_api_key(x_api_key)

    ingested, skipped, errors, total_chunks = [], [], [], 0
    for resource in resources:
        try:
            if resource.quality_flag and resource.quality_flag != "ready_to_certify":
                skipped.append(resource.publication_id)
                continue
            n_chunks = await ingest_resource(resource)
            total_chunks += n_chunks
            ingested.append(resource.publication_id)
        except Exception as exc:  # noqa: BLE001
            errors.append({"publication_id": resource.publication_id, "error": str(exc)})

    return IngestResponse(ingested=ingested, chunks_indexed=total_chunks, skipped=skipped, errors=errors)
