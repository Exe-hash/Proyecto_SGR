from django.contrib import admin

from .models import Cargo, Delegacion, PerfilUsuario


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)

#ESTO AGREGARÁ LA SECCIÓN: Perfiles de Usuario A DJANGO
@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "delegacion", "cargo")
    search_fields = ("usuario__username",)
    list_filter = ("delegacion", "cargo")