from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import path, reverse_lazy

from . import views

app_name = "principal"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("ingresar/", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("actividades/", views.actividades, name="actividades"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/cartas/crear/", views.crear_carta, name="crear_carta"),
    path("agenda/cartas/editar/", views.editar_carta, name="editar_carta"),
    path("evidencias/", views.evidencias, name="evidencias"),
    path("equipo/", views.equipo, name="equipo"),
    path("equipo/ajuste/", views.registrar_ajuste_desempeno, name="registrar_ajuste_desempeno"),
    path("equipo/ausencia/", views.registrar_ausencia, name="registrar_ausencia"),
    path("asignar-tareas/", views.asignar_tareas, name="asignar_tareas"),
    path("verificacion/", views.verificacion, name="verificacion"),
    path("administracion/", views.administracion, name="administracion"),


    path("usuarios/", views.listar_usuarios, name="listar_usuarios"),
    path("usuarios/crear/", views.crear_usuario, name="crear_usuario"),
    path("usuarios/editar/<int:usuario_id>/", views.editar_usuario, name="editar_usuario"),
    path("usuarios/desactivar/<int:usuario_id>/", views.desactivar_usuario, name="desactivar_usuario"),


    path("cerrar-sesion/", LogoutView.as_view(next_page="principal:landing"), name="cerrar_sesion"),
    path("cambiar-password-inicial/", views.cambiar_password_inicial, name="cambiar_password_inicial"),
    path(
        "recuperar-password/",
        auth_views.PasswordResetView.as_view(
            template_name="principal/password_reset.html",
            email_template_name="principal/password_reset_email.html",
            success_url=reverse_lazy("principal:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "recuperar-password/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="principal/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "recuperar/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="principal/password_reset_confirm.html",
            success_url=reverse_lazy("principal:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "recuperar/completado/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="principal/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),


    path("area-social/", views.area_social, name="area_social"),
    path("area-social/crear/", views.crear_caso_social, name="crear_caso_social"),
    path("area-social/editar/", views.editar_caso_social, name="editar_caso_social"),


    path("archivos/evidencia/<int:evidencia_id>/", views.descargar_evidencia, name="descargar_evidencia"),
    path("archivos/social/<int:gestion_id>/", views.descargar_evidencia_social, name="descargar_evidencia_social"),
    path("archivos/respaldo/<int:ajuste_id>/", views.descargar_respaldo_ajuste, name="descargar_respaldo_ajuste"),


    path("api/vecino/", views.api_buscar_vecino, name="api_buscar_vecino"),
]