"""
Guards against django-import-export form field collisions.

SelectableFieldsExportForm normalizes boolean export fields back to their
ModelResource field names. A Resource field named ``resource`` overwrites
the form's resource-class index (``int(True) == 1`` -> IndexError).
"""
from config.safe_export_form import SafeSelectableFieldsExportForm


class SafeResourceIndexMixin:
    export_form_class = SafeSelectableFieldsExportForm

    def get_resource_index(self, form):
        classes = self.get_resource_classes(None)
        if not classes:
            return 0
        if len(classes) == 1:
            return 0

        raw = None
        if form is not None and hasattr(form, "cleaned_data"):
            raw = form.cleaned_data.get("resource")

        if isinstance(raw, bool) or raw in (None, ""):
            return 0

        try:
            idx = int(raw)
        except (TypeError, ValueError):
            return 0

        if idx < 0 or idx >= len(classes):
            return 0
        return idx
