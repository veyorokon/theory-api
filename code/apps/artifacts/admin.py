from django.contrib import admin
from apps.artifacts.models import Artifact


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ('id', 'world', 'uri_short', 'is_scalar', 'content_type', 'size_bytes', 'created_at')
    list_filter = ('is_scalar', 'content_type', 'created_at', 'world')
    search_fields = ('uri', 'path', 'world__name')
    readonly_fields = ('id', 'uri', 'path', 'created_at', 'etag', 'sha256')

    fieldsets = (
        ('Identity', {
            'fields': ('id', 'world', 'uri', 'path')
        }),
        ('Type', {
            'fields': ('is_scalar', 'content_type')
        }),
        ('Data', {
            'fields': ('data',),
            'description': 'Only populated for scalar artifacts'
        }),
        ('Metadata', {
            'fields': ('size_bytes', 'etag', 'sha256', 'created_at')
        }),
    )

    def uri_short(self, obj):
        """Show shortened URI for list display."""
        if len(obj.uri) > 80:
            return obj.uri[:77] + '...'
        return obj.uri
    uri_short.short_description = 'URI'
