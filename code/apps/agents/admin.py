from django.contrib import admin
from apps.agents.models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "user", "created_at")
    search_fields = ("name",)
    list_filter = ("kind", "created_at")
    readonly_fields = ("id", "created_at", "updated_at")
