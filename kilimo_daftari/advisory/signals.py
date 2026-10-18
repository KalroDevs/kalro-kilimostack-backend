# advisory/signals.py
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WorkbookUpload
from .workbook_ingestion import ingest_workbook

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkbookUpload)
def _run_ingest(sender, instance, created, **kwargs):
    """
    Run ingestion once, right after a new WorkbookUpload is created.
    We guard with `created` so re-saving the same row (e.g. after the
    service updated counters) does NOT re-trigger ingestion.
    """
    if not created:
        return
    if not instance.file:
        return
    try:
        ingest_workbook(instance)
    except Exception:
        # The ingestion service records the failure on the upload. Keep an
        # invalid workbook from turning the admin save into a server error.
        logger.exception("Workbook upload %s ingestion failed", instance.pk)
