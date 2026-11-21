from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Cargo, Delegacion, PerfilUsuario, CasoSocial, GestionSocial

@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)

# --- FUSIÓN DE USER Y PERFILUSUARIO EN EL ADMIN ---

class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil Organizacional (Cargo y Delegación)'
    fk_name = 'usuario'

# Desregistramos el modelo User nativo para inyectarle nuestro perfil
admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (PerfilUsuarioInline, )
    list_display = ('username', 'first_name', 'last_name', 'get_cargo', 'get_delegacion', 'is_active')
    list_select_related = ('perfil', )

    def get_cargo(self, instance):
        return instance.perfil.cargo.nombre if hasattr(instance, 'perfil') and instance.perfil.cargo else '-'
    get_cargo.short_description = 'Cargo SGR'

    def get_delegacion(self, instance):
        return instance.perfil.delegacion.nombre if hasattr(instance, 'perfil') and instance.perfil.delegacion else '-'
    get_delegacion.short_description = 'Delegación'

# Registramos los modelos nuevos
admin.site.register(CasoSocial)
admin.site.register(GestionSocial)