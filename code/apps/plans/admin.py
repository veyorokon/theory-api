from django.contrib import admin
from .models import Project, Plan


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("key", "title")
    search_fields = ("key", "title")
    ordering = ("key",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("key", "project", "reserved_micro", "spent_micro")
    list_filter = ("project",)
    search_fields = ("key", "project__key")
    ordering = ("key",)
