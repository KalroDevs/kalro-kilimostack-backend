"""
Usage:

    python manage.py sync_to_ai_layer
    python manage.py sync_to_ai_layer --resync-all
    python manage.py sync_to_ai_layer --publication-id kalro-livestock-camel-calf-management-2017-043

Populates (or backfills) the FastAPI AI Layer's Chroma vector index from
AdvisoryResource rows already in the Django database, without going through
the HTTP API (POST /api/v1/resources/sync-ready/) or the admin action --
useful for scripting, cron, or a one-off backfill after a bulk import.

Only resources with quality_flag == 'ready_to_certify' are ever sent, same
guard as the API-triggered sync path in advisory/services.py.
"""

from django.core.management.base import BaseCommand, CommandError

from advisory.models import AdvisoryResource
from advisory.services import sync_resource_to_ai_layer


class Command(BaseCommand):
    help = "Bulk-sync certified (ready_to_certify) AdvisoryResource rows to the AI Layer's vector index"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resync-all",
            action="store_true",
            help="Re-sync every certified resource, including ones already marked 'synced' "
            "(use after re-embedding, changing chunking logic, or rebuilding the Chroma volume)",
        )
        parser.add_argument(
            "--publication-id",
            type=str,
            default=None,
            help="Sync only this one resource, by publication_id",
        )

    def handle(self, *args, **options):
        qs = AdvisoryResource.objects.filter(quality_flag="ready_to_certify")

        if options["publication_id"]:
            qs = qs.filter(publication_id=options["publication_id"])
            if not qs.exists():
                raise CommandError(
                    f"No certified resource found with publication_id={options['publication_id']!r} "
                    "(it may not exist, or isn't marked ready_to_certify)"
                )
        elif not options["resync_all"]:
            qs = qs.exclude(vector_sync_status="synced")

        total = qs.count()
        if total == 0:
            self.stdout.write("Nothing to sync — no certified resources match these options.")
            return

        self.stdout.write(f"Syncing {total} resource(s) to the AI Layer...")
        synced, failed = 0, 0
        for resource in qs:
            ok = sync_resource_to_ai_layer(resource)
            if ok:
                synced += 1
                self.stdout.write(self.style.SUCCESS(f"  OK    {resource.publication_id}"))
            else:
                failed += 1
                reason = resource.vector_sync_error or "sync disabled or not yet certified"
                self.stdout.write(self.style.ERROR(f"  FAIL  {resource.publication_id}: {reason}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. synced={synced} failed={failed}"))
        if failed:
            self.stdout.write(
                "Failures usually mean the AI Layer (AI_LAYER_BASE_URL) or Ollama isn't reachable — "
                "check `curl $AI_LAYER_BASE_URL/health`."
            )
