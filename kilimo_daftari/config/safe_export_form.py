"""
Export form that does not break when a ModelResource field is named
``resource`` (collides with django-import-export's resource-class selector).
"""
from django import forms
from django.utils.translation import gettext_lazy as _
from import_export.forms import ExportForm, SelectableFieldsExportForm


class SafeSelectableFieldsExportForm(SelectableFieldsExportForm):
    """Preserve resource-class index across selectable-field normalization."""

    def get_selected_resource(self):
        if not getattr(self, "cleaned_data", None):
            raise forms.ValidationError(
                _("Form is not validated, call `is_valid` first")
            )

        if hasattr(self, "_selected_resource_index"):
            idx = self._selected_resource_index
        else:
            idx = 0
            raw = self.cleaned_data.get("resource")
            if raw is not None and not isinstance(raw, bool):
                try:
                    idx = int(raw)
                except (TypeError, ValueError):
                    idx = 0
            if idx < 0 or idx >= len(self.resources):
                idx = 0
            self._selected_resource_index = idx

        return self.resources[idx]

    def _normalize_resource_fields(self, selected_resource):
        # Keep the class-selector value; field named "resource" must not wipe it
        class_selector = self.cleaned_data.get("resource")
        if isinstance(class_selector, bool):
            class_selector = str(getattr(self, "_selected_resource_index", 0))
        super()._normalize_resource_fields(selected_resource)
        # If a model field named "resource" overwrote the selector, restore it
        if isinstance(self.cleaned_data.get("resource"), bool):
            # Move FK export checkbox under a safe key used only for field list
            self.cleaned_data["advisory_resource_selected"] = self.cleaned_data["resource"]
            if self.cleaned_data["resource"] is True:
                fields = getattr(self, "_selected_resource_fields", [])
                if "resource" in fields:
                    # keep "resource" in selected fields for export columns
                    pass
            self.cleaned_data["resource"] = class_selector if class_selector is not None else "0"
