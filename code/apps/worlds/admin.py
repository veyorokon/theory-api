from django.contrib import admin
from apps.worlds.models import World, WorldAgent


@admin.register(World)
class WorldAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "owner", "created_at")
    search_fields = ("name", "title")
    list_filter = ("created_at",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(WorldAgent)
class WorldAgentAdmin(admin.ModelAdmin):
    list_display = ("world", "agent", "role", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("world__name", "agent__name")
