"""
Usage:

    python manage.py import_advisory_json path/to/resource_or_resources.json
    python manage.py import_advisory_json path/to/file.json --sync

Imports one or more resources conforming to the Advisory Content Import
JSON Specification v0.1 (a single object or an array of objects). Upserts
by ``publication_id``. Pass --sync to immediately push any
'ready_to_certify' resources to the AI Layer after import.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from advisory.serializers import AdvisoryResourceSerializer
from advisory.services import sync_resource_to_ai_layer
from advisory.models import AdvisoryResource


class Command(BaseCommand):
    help = "Import advisory resources from a JSON file matching the Advisory Content Import JSON Specification v0.1"

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str)
        parser.add_argument(
            "--sync", action="store_true", help="Push ready_to_certify resources to the AI Layer after import"
        )

    def handle(self, *args, **options):
        path = Path(options["json_path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = [data]

        created, updated, failed = 0, 0, 0
        for item in data:
            publication_id = item.get("publication_id")
            instance = AdvisoryResource.objects.filter(publication_id=publication_id).first()
            serializer = AdvisoryResourceSerializer(instance, data=item, partial=instance is not None)
            if serializer.is_valid():
                obj = serializer.save()
                if instance:
                    updated += 1
                else:
                    created += 1
                self.stdout.write(self.style.SUCCESS(f"OK  {obj.publication_id}"))
                if options["sync"]:
                    sync_resource_to_ai_layer(obj)
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f"FAIL {publication_id}: {serializer.errors}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. created={created} updated={updated} failed={failed}")
        )
