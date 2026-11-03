from django.apps import AppConfig
from django.db.models.signals import post_migrate

def crear_roles_por_defecto(sender, **kwargs):
    """Crea los 3 roles base en la base de datos automáticamente tras cada migración."""
    from django.contrib.auth.models import Group
    
    roles_base = ["Funcionario", "Supervisor", "Administrador"]
    for rol in roles_base:
        Group.objects.get_or_create(name=rol)
    
    print("Verificación de roles completada: Funcionario, Supervisor, Administrador confirmados.")

class PrincipalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'principal'

    def ready(self):
        post_migrate.connect(crear_roles_por_defecto, sender=self)