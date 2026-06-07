from django.urls import path

from .consumers import LensNodeConsumer

websocket_urlpatterns = [
    path("ws/lens/lensnodes/", LensNodeConsumer.as_asgi()),
]
