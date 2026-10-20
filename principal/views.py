"""Vistas de presentación del SGR con datos ficticios de demostración."""

from functools import wraps

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from .datos_demo import COMPROMISOS, EQUIPO, EVIDENCIAS, METAS


def usuario_tiene_rol(usuario, *roles):
    """Indica si un usuario posee al menos uno de los roles solicitados."""
    return (
        usuario.is_authenticated
        and (
            usuario.is_superuser
            or usuario.groups.filter(name__in=roles).exists()
        )
    )


def requiere_roles(*roles):
    """Protege una vista y devuelve error 403 si el rol no está autorizado."""

    def decorador(vista):
        @login_required(login_url="principal:inicio")
        @wraps(vista)
        def vista_protegida(request, *args, **kwargs):
            if not usuario_tiene_rol(request.user, *roles):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return vista_protegida

    return decorador


def contexto_usuario(request, **contexto):
    """
    Agrega al template los permisos visuales y los datos reales
    del perfil del usuario que inició sesión.
    """
    perfil = getattr(request.user, "perfil", None)

    contexto.update(
        {
            "puede_registrar_actividades": usuario_tiene_rol(
                request.user, "Funcionario"
            ),
            "puede_ver_agenda": usuario_tiene_rol(
                request.user, "Funcionario", "Jefatura"
            ),
            "puede_ver_equipo": usuario_tiene_rol(
                request.user, "Jefatura"
            ),
            "puede_verificar_evidencias": usuario_tiene_rol(
                request.user, "Verificador"
            ),
            "nombre_usuario": (
                request.user.get_full_name().strip()
                or request.user.get_username()
            ),
            "cargo_usuario": (
                perfil.cargo.nombre if perfil else "Sin cargo asignado"
            ),
            "delegacion_usuario": (
                perfil.delegacion.nombre
                if perfil
                else "Sin delegación asignada"
            ),
        }
    )

    return contexto


def renderizar(request, plantilla, contexto=None):
    """Renderiza una plantilla incluyendo el contexto del usuario conectado."""
    return render(
        request,
        plantilla,
        contexto_usuario(request, **(contexto or {})),
    )


def inicio(request):
    if request.method == "POST":
        nombre_usuario = request.POST.get("username", "").strip()
        contrasena = request.POST.get("password", "")

        usuario = authenticate(
            request,
            username=nombre_usuario,
            password=contrasena,
        )

        if usuario is not None:
            login(request, usuario)
            return redirect("principal:panel")

        return render(
            request,
            "principal/inicio.html",
            {"error_inicio": "Usuario o contraseña incorrectos."},
        )

    return render(request, "principal/inicio.html")


@requiere_roles("Funcionario", "Jefatura", "Verificador")
def panel(request):
    return renderizar(
        request,
        "principal/panel.html",
        {
            "pagina": "panel",
            "metas": METAS,
            "compromisos": COMPROMISOS[:3],
        },
    )


@requiere_roles("Funcionario")
def actividades(request):
    return renderizar(
        request,
        "principal/actividades.html",
        {
            "pagina": "actividades",
            "metas": METAS,
        },
    )


@requiere_roles("Funcionario", "Jefatura")
def agenda(request):
    return renderizar(
        request,
        "principal/agenda.html",
        {
            "pagina": "agenda",
            "compromisos": COMPROMISOS,
        },
    )


@requiere_roles("Funcionario")
def evidencias(request):
    return renderizar(
        request,
        "principal/evidencias.html",
        {
            "pagina": "evidencias",
            "evidencias": EVIDENCIAS,
        },
    )


@requiere_roles("Jefatura")
def equipo(request):
    return renderizar(
        request,
        "principal/equipo.html",
        {
            "pagina": "equipo",
            "equipo": EQUIPO,
        },
    )


@requiere_roles("Verificador")
def verificacion(request):
    return renderizar(
        request,
        "principal/verificacion.html",
        {
            "pagina": "verificacion",
            "evidencias": EVIDENCIAS,
        },
    )