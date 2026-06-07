from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include

from accounts.views import OAuthCallbackRedirectView
from .swagger import schema_view, swagger_view, redoc_view

# Define project URL routing configuration
urlpatterns = [
    # Health check endpoint
    # Used by Docker/Kubernetes for container health monitoring
    # Returns a simple 'OK' response to indicate the application is running
    path('health', lambda _: JsonResponse({'health': 'OK'}, status=200)),

    # API Schema endpoint
    # Provides the OpenAPI schema in JSON format
    path('api/schema', schema_view, name='schema'),

    # Swagger UI documentation route
    # Displays the API documentation using Swagger UI.
    path('swagger', swagger_view, name='swagger-ui'),

    # ReDoc documentation route
    # Displays the API documentation using ReDoc.
    path('redoc', redoc_view, name='redoc'),

    # Django admin site route
    # Provides access to the Django Admin interface for managing models and
    # data.
    path('admin', admin.site.urls),

    # Authentication routes
    # Includes authentication endpoints provided by custom accounts.urls
    path('', include('accounts.urls')),

    # Task management routes (agentcore-task)
    path('api/v1/tasks/', include('agentcore_task.adapters.django.urls')),

    # Lens MVP API
    path('api/lens/', include('lens.urls')),

    # Notifier admin API (agentcore-notifier: must be before admin/ to match)
    path(
        'api/v1/admin/notifications/',
        include('agentcore_notifier.adapters.django.urls')
    ),
    # LLM metering admin API (agentcore-metering submodule)
    path('api/v1/admin/', include('agentcore_metering.adapters.django.urls')),

    # Custom OAuth callback redirect with JWT tokens
    # This must come BEFORE allauth.urls to intercept the redirect
    path(
        'accounts/oauth/callback/',
        OAuthCallbackRedirectView.as_view(),
        name='oauth_callback_redirect'
    ),

    # Django-allauth OAuth callback routes
    # Required for OAuth provider callbacks (e.g., Google)
    # Even with Headless API, these endpoints are needed for OAuth handshake
    path('accounts/', include('allauth.urls')),

    # Django-allauth Headless API endpoints
    # REST API for frontend-backend separation (allauth >= 65.0.0)
    # Provides authentication APIs without Django form views
    path('_allauth/', include('allauth.headless.urls')),
]
