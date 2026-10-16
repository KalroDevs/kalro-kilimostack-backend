# advisory/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WorkbookUpload
from .workbook_ingestion import ingest_workbook


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
        # The upload row records the actionable failure in ``log``. Avoid
        # turning a saved upload into an unhandled server error in the admin.
        return
