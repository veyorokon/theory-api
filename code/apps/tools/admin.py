from django.contrib import admin
from apps.tools.models import Tool


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ("ref", "enabled", "timeout_s", "cpu", "memory_gb", "gpu")
    list_filter = ("enabled",)
    search_fields = ("ref", "name")
    readonly_fields = ("ref", "name", "namespace", "version", "digest_amd64", "digest_arm64")

    fieldsets = (
        ("Identity", {"fields": ("ref", "name", "namespace", "version", "enabled")}),
        ("Runtime", {"fields": ("timeout_s", "cpu", "memory_gb", "gpu")}),
        ("Images", {"fields": ("digest_amd64", "digest_arm64")}),
        ("Schema", {"fields": ("inputs_schema", "outputs_decl")}),
    )
