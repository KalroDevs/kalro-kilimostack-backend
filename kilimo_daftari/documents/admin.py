from pathlib import Path

from django.contrib import admin
from django.contrib import messages
from django import forms

from .models import Document
from .services import process_document


class DocumentAdminForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = "__all__"

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if uploaded_file is None:
            return uploaded_file
        if Document.file_type_for_name(uploaded_file.name) is None:
            supported = ", ".join(Document.FILE_TYPE_BY_EXTENSION)
            raise forms.ValidationError(
                f"Unsupported file type. Supported extensions: {supported}."
            )
        if uploaded_file.size > 25 * 1024 * 1024:
            raise forms.ValidationError("The maximum document size is 25 MB.")
        return uploaded_file


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ("name", "file_type", "status", "chunks_indexed", "created_at", "updated_at",)
    list_filter = ("file_type", "status", "created_at")
    search_fields = ("name", "file")
    readonly_fields = ("file_type", "status", "chunks_indexed", "processing_error", "created_at", "updated_at",)
    actions = ("process_selected_documents",)

    def save_model(self, request, obj, form, change):
        if obj.file:
            obj.file_type = Document.file_type_for_name(obj.file.name)
        if not obj.name and obj.file:
            obj.name = Path(obj.file.name).stem
        super().save_model(request, obj, form, change)
        if not change or "file" in form.changed_data:
            self._process_and_notify(request, obj)

    def _process_and_notify(self, request, document):
        if process_document(document):
            self.message_user(
                request,
                f"{document.name} verified and indexed in the training-document store.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{document.name} processing failed: {document.processing_error}",
                level=messages.ERROR,
            )

    @admin.action(description="Process selected documents")
    def process_selected_documents(self, request, queryset):
        for document in queryset:
            self._process_and_notify(request, document)