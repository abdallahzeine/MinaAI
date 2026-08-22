import os

from asgiref.typing import ASGI3Application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Backend.settings')
django_asgi_app = get_asgi_application()
from main.core.websocket import websocket_urlpatterns
application: ASGI3Application = ProtocolTypeRouter({"http": django_asgi_app, "websocket": URLRouter(websocket_urlpatterns)})
