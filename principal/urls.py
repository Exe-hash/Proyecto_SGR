from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "principal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("actividades/", views.actividades, name="actividades"),
    path("agenda/", views.agenda, name="agenda"),
    path("evidencias/", views.evidencias, name="evidencias"),
    path("equipo/", views.equipo, name="equipo"),
    path("verificacion/", views.verificacion, name="verificacion"),
    path("administracion/", views.administracion, name="administracion"),
    
    # --- CRUD USUARIOS ---
    path("usuarios/", views.listar_usuarios, name="listar_usuarios"),
    path("usuarios/crear/", views.crear_usuario, name="crear_usuario"),
    path("usuarios/editar/<int:usuario_id>/", views.editar_usuario, name="editar_usuario"),
    path("usuarios/desactivar/<int:usuario_id>/", views.desactivar_usuario, name="desactivar_usuario"),

    # --- AUTENTICACIÓN Y RECUPERACIÓN DE CONTRASEÑA ---
    path("cerrar-sesion/", LogoutView.as_view(next_page="principal:inicio"), name="cerrar_sesion"),
    
    path('recuperar-password/', auth_views.PasswordResetView.as_view(
        template_name='principal/password_reset.html',
        email_template_name='principal/password_reset_email.html',
        success_url=reverse_lazy('principal:password_reset_done')
    ), name='password_reset'),
    
    path('recuperar-password/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='principal/password_reset_done.html'
    ), name='password_reset_done'),
    
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='principal/password_reset_confirm.html',
        success_url=reverse_lazy('principal:password_reset_complete')
    ), name='password_reset_confirm'),
    
    path('recuperar/completado/', auth_views.PasswordResetCompleteView.as_view(
        template_name='principal/password_reset_complete.html'
    ), name='password_reset_complete'),
]