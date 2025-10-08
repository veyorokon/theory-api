from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import GraphQLView

from backend.schema import schema


@csrf_exempt
def health_check(request):
    """Health check endpoint for App Runner / load balancers."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health_check, name="health"),
    path("admin/", admin.site.urls),
    path(
        "graphql/",
        GraphQLView.as_view(schema=schema, graphiql=settings.DEBUG),
    ),
]
