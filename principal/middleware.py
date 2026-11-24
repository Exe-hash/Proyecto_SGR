from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForzarCambioClaveMiddleware:
    """Obliga a usuarios con contraseña temporal a cambiarla antes de navegar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario and usuario.is_authenticated:
            perfil = getattr(usuario, "perfil", None)
            if perfil and perfil.debe_cambiar_clave:
                rutas_permitidas = {
                    reverse("principal:cambiar_password_inicial"),
                    reverse("principal:cerrar_sesion"),
                }
                static_url = settings.STATIC_URL if settings.STATIC_URL.startswith("/") else f"/{settings.STATIC_URL}"
                if (
                    request.path not in rutas_permitidas
                    and not request.path.startswith(static_url)
                ):
                    return redirect("principal:cambiar_password_inicial")

        return self.get_response(request)