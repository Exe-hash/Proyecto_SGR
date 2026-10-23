from django.conf import settings
from django.db import models

# --- TABLAS ORIGINALES DE TU COMPAÑERO ---

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
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil",
    )
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
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

# --- NUEVAS TABLAS PARA EL CRUD ---

class Compromiso(models.Model):
    ESTADOS_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('En proceso', 'En proceso'),
        ('Completado', 'Completado'),
        ('Rechazado', 'Rechazado'),
    ]

    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código")
    titulo = models.CharField(max_length=255, verbose_name="Título del compromiso")
    territorio = models.ForeignKey(Delegacion, on_delete=models.PROTECT, verbose_name="Territorio")
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Responsable")
    estado = models.CharField(max_length=20, choices=ESTADOS_CHOICES, default='Pendiente', verbose_name="Estado")
    area = models.CharField(max_length=100, verbose_name="Área")
    solicitante = models.CharField(max_length=150, verbose_name="Solicitante")
    fecha = models.DateField(verbose_name="Fecha de solicitud")
    plazo = models.CharField(max_length=50, verbose_name="Plazo (Ej: 30 DÍAS)")

    class Meta:
        verbose_name = "compromiso"
        verbose_name_plural = "compromisos"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.codigo} - {self.titulo}"


class Evidencia(models.Model):
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código Verificador")
    funcionario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Funcionario")
    estado = models.CharField(max_length=20, default='En revisión', verbose_name="Estado")
    
    fecha_registro = models.DateField(verbose_name="Fecha de Registro")
    item_medir = models.CharField(max_length=150, verbose_name="Ítem a Medir")
    solicitud = models.TextField(verbose_name="Actividad / Solicitud / Problema")
    accion = models.TextField(verbose_name="Acción Realizada")
    
    contacto_nombre = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre de contacto")
    contacto_telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    
    fotografia = models.ImageField(upload_to='evidencias/%Y/%m/', verbose_name="Fotografía de evidencia")
    
    compromiso_vinculado = models.OneToOneField(Compromiso, on_delete=models.SET_NULL, null=True, blank=True, related_name='evidencia_origen')
    observacion = models.TextField(null=True, blank=True)

    # Agrega esta línea dentro de tu modelo Evidencia
    meta_relacionada = models.ForeignKey('Meta', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Meta a la que aporta")

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ["-fecha_registro"]

    def __str__(self):
        return f"{self.codigo} - {self.funcionario.get_username()}"

class Observacion(models.Model):
    compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name='observaciones')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True) # Guarda la fecha y hora exacta automáticamente
    texto = models.TextField()

    revisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='evidencias_evaluadas')
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha'] # Las más nuevas salen primero

class Meta(models.Model):
    """Almacena los indicadores y ponderaciones requeridos en HU-04 y HU-05"""
    cargo = models.ForeignKey('Cargo', on_delete=models.CASCADE, related_name='metas', null=True, blank=True)
    nombre = models.CharField(max_length=250, verbose_name="Ítem a evaluar (Ej: Atención de usuario)")
    valor_objetivo = models.IntegerField(verbose_name="Cantidad meta esperada (Ej: 45)")
    ponderacion = models.IntegerField(verbose_name="Ponderación en % (Ej: 10)")
    vigente = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.ponderacion}%] {self.nombre} - Meta: {self.valor_objetivo}"