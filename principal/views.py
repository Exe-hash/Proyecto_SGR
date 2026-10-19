"""Vistas de presentación del SGR con datos ficticios de demostración."""
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .datos_demo import COMPROMISOS, EQUIPO, EVIDENCIAS, METAS

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

@login_required(login_url="principal:inicio")
def panel(request):
    return render(
        request,
        "principal/panel.html",
        {
            "pagina": "panel",
            "metas": METAS,
            "compromisos": COMPROMISOS[:3],
        },
    )


@login_required(login_url="principal:inicio")
def actividades(request):
    return render(
        request,
        "principal/actividades.html",
        {"pagina": "actividades", "metas": METAS},
    )


@login_required(login_url="principal:inicio")
def agenda(request):
    return render(
        request,
        "principal/agenda.html",
        {"pagina": "agenda", "compromisos": COMPROMISOS},
    )


@login_required(login_url="principal:inicio")
def evidencias(request):
    return render(
        request,
        "principal/evidencias.html",
        {"pagina": "evidencias", "evidencias": EVIDENCIAS},
    )


@login_required(login_url="principal:inicio")
def equipo(request):
    return render(
        request,
        "principal/equipo.html",
        {"pagina": "equipo", "supervision": True, "equipo": EQUIPO},
    )


@login_required(login_url="principal:inicio")
def verificacion(request):
    return render(
        request,
        "principal/verificacion.html",
        {
            "pagina": "verificacion",
            "supervision": True,
            "evidencias": EVIDENCIAS,
        },
    )