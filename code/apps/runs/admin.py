from django.contrib import admin
from apps.runs.models import Run, RunOutput


class RunOutputInline(admin.TabularInline):
    model = RunOutput
    extra = 0
    readonly_fields = ("key", "uri", "path", "content_type", "size_bytes", "etag", "sha256")


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "ref", "world", "caller_agent", "status", "mode", "adapter", "started_at")
    list_filter = ("status", "mode", "adapter", "started_at")
    search_fields = ("id", "ref")
    readonly_fields = ("id", "started_at", "ended_at", "duration_ms")
    inlines = [RunOutputInline]

    fieldsets = (
        ("Identity", {"fields": ("id", "ref", "world", "caller_agent")}),
        ("Execution", {"fields": ("mode", "adapter", "status")}),
        ("Timing", {"fields": ("started_at", "ended_at", "duration_ms")}),
        ("Error", {"fields": ("error_code", "error_message")}),
        ("Image", {"fields": ("image_digest_expected", "image_digest_actual", "drift_ok")}),
        ("Cost & Usage", {"fields": ("cost_micro", "usage")}),
        ("Metadata", {"fields": ("meta", "inputs")}),
    )


@admin.register(RunOutput)
class RunOutputAdmin(admin.ModelAdmin):
    list_display = ("run_id", "key", "path", "content_type", "size_bytes")
    search_fields = ("run__id", "key", "uri", "path")
    readonly_fields = ("run", "key", "uri", "path", "content_type", "size_bytes", "etag", "sha256")
