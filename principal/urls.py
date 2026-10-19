from django.urls import path

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
]
