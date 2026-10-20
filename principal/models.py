from django.conf import settings
from django.db import models


class Delegacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "delegación"
        verbose_name_plural = "delegaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Cargo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    #aquí "usuario" relaciona el perfil con una cuenta que ya existe en Django. "OneToOneField" permite un solo perfil por cada usuario.
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,#esto indica que si se elimina un usuario, tambien se elimina su perfil.
        related_name="perfil",
    )


    #DELEGACION Y CARGO relacionan el perfil con los registros ya creados.
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,#PROTECT evita borrar un cargo o alguna delegacion mientras estén siendo usados por algun perfil.
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.PROTECT,
    )

    class Meta:
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"Perfil de {self.usuario.get_username()}"