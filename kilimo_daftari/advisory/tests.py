import json
from pathlib import Path

from django.test import TestCase

from .models import AdvisoryResource
from .serializers import AdvisoryResourceSerializer

SAMPLE_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "sample_camel_calf_resource.json"


class AdvisoryResourceImportTests(TestCase):
    """
    Round-trips the real KALRO camel-calf example (Advisory Content Import
    JSON Specification v0.1) through the serializer, matching the manual
    verification used to develop this project.
    """

    def setUp(self):
        self.data = json.loads(SAMPLE_JSON.read_text())[0]

    def test_import_creates_resource_with_all_content_sections(self):
        serializer = AdvisoryResourceSerializer(data=self.data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        resource = serializer.save()

        self.assertEqual(resource.publication_id, "kalro-livestock-camel-calf-management-2017-043")
        self.assertEqual(resource.sector, "livestock")
        self.assertEqual(resource.value_chain, "camel")
        self.assertEqual(resource.content_sections.count(), 9)
        self.assertEqual(resource.risk_level, "high")
        self.assertTrue(resource.requires_human_review)

    def test_serialized_output_round_trips_spec_shape(self):
        serializer = AdvisoryResourceSerializer(data=self.data)
        serializer.is_valid(raise_exception=True)
        resource = serializer.save()

        output = AdvisoryResourceSerializer(resource).data
        self.assertEqual(len(output["content"]), 9)
        self.assertEqual(output["advisory_safety"]["risk_level"], "high")
        self.assertIn("arid and semi-arid lands", output["geographic_applicability"]["agro_ecological_zones"])

    def test_default_quality_flag_excludes_resource_from_ai_layer_sync(self):
        serializer = AdvisoryResourceSerializer(data=self.data)
        serializer.is_valid(raise_exception=True)
        resource = serializer.save()
        # Freshly imported resources haven't been screened yet.
        self.assertFalse(resource.is_ready_for_ai_layer)

        resource.quality_flag = "ready_to_certify"
        resource.save()
        self.assertTrue(resource.is_ready_for_ai_layer)


class ScreeningWorkflowTests(TestCase):
    def test_upsert_by_publication_id(self):
        data = json.loads(SAMPLE_JSON.read_text())[0]
        AdvisoryResourceSerializer(data=data).is_valid(raise_exception=True)
        first = AdvisoryResourceSerializer(data=data)
        first.is_valid(raise_exception=True)
        first.save()

        self.assertEqual(AdvisoryResource.objects.count(), 1)

        existing = AdvisoryResource.objects.get(publication_id=data["publication_id"])
        second = AdvisoryResourceSerializer(existing, data=data, partial=True)
        second.is_valid(raise_exception=True)
        second.save()

        self.assertEqual(AdvisoryResource.objects.count(), 1)
