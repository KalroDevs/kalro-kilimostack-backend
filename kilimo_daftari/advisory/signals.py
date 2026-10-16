# advisory/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WorkbookUpload
from .services import ingest_workbook


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
    ingest_workbook(instance)