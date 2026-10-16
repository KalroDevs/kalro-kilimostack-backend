from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("advisory", "0006_workbookupload"),
    ]

    operations = [
        migrations.AddField(
            model_name="advisoryresource",
            name="workbook_resource_id",
            field=models.CharField(blank=True, db_index=True, max_length=120, null=True, unique=True),
        ),
    ]
