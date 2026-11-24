import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


# =====================================================================
# 1. ESTRUCTURA ORGANIZACIONAL Y TERRITORIAL
# =====================================================================

class Delegacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "delegación"
        verbose_name_plural = "delegaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Territorio(models.Model):
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="territorios",
    )
    nombre = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "territorio"
        verbose_name_plural = "territorios"
        ordering = ["delegacion__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["delegacion", "nombre"],
                name="uq_territorio_por_delegacion",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.delegacion.nombre})"


class Cargo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    es_area_social = models.BooleanField(default=False)
    meta_minima_porcentaje = models.PositiveSmallIntegerField(
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name="Cumplimiento mínimo esperado (%)",
    )
    activo = models.BooleanField(default=True)

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
    es_delegado = models.BooleanField(
        default=False,
        verbose_name="Es Delegado/a de la delegación",
    )
    debe_cambiar_clave = models.BooleanField(
        default=False,
        verbose_name="Debe cambiar contraseña en el próximo ingreso",
    )

    class Meta:
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"Perfil de {self.usuario.get_username()}"


# =====================================================================
# 2. CIUDADANOS, ORGANIZACIONES, DIRIGENCIAS E HITOS
# =====================================================================

class Vecino(models.Model):
    rut = models.CharField(max_length=15, unique=True, db_index=True, verbose_name="RUT")
    nombre_completo = models.CharField(max_length=150, db_index=True, verbose_name="Nombre completo")
    telefono = models.CharField(max_length=30, blank=True, default="")
    correo = models.EmailField(blank=True, default="")
    direccion = models.CharField(max_length=255, blank=True, default="")
    territorio = models.ForeignKey(
        Territorio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vecinos",
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vecino"
        verbose_name_plural = "vecinos"
        ordering = ["nombre_completo"]

    def __str__(self):
        return f"{self.rut} - {self.nombre_completo}"

    @property
    def tiene_contacto_valido(self):
        return bool(self.nombre_completo.strip() and self.telefono.strip())


class JuntaVecinos(models.Model):
    TIPO_CHOICES = [
        ("Junta de Vecinos", "Junta de Vecinos"),
        ("Club Adulto Mayor", "Club Adulto Mayor"),
        ("Organización Deportiva", "Organización Deportiva"),
        ("Centro Cultural / Juvenil / Madres", "Centro Cultural / Juvenil / Madres"),
        ("Comité de Vecinos / Seguridad", "Comité de Vecinos / Seguridad"),
        ("Organización Funcional", "Organización Funcional"),
    ]

    nombre = models.CharField(max_length=190, db_index=True, verbose_name="Organización")
    tipo_organizacion = models.CharField(max_length=60, choices=TIPO_CHOICES, default="Organización Funcional")
    territorio = models.ForeignKey(
        Territorio,
        on_delete=models.PROTECT,
        related_name="organizaciones",
        verbose_name="Territorio / Delegación",
    )
    direccion = models.CharField(max_length=255, blank=True, default="", verbose_name="Domicilio legal")
    socios_activos = models.PositiveIntegerField(default=0, verbose_name="Socios activos")
    fecha_constitucion = models.DateField(null=True, blank=True, verbose_name="Fecha de constitución")
    personalidad_juridica = models.CharField(
        max_length=60,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Nº Registro P.J.",
    )
    fecha_inscripcion_registro = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha inscripción en registro",
    )
    registro_directorio_numero = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Registro Directorio Nº",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "junta de vecinos u organización"
        verbose_name_plural = "juntas de vecinos y organizaciones"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["territorio", "nombre"],
                name="uq_jjvv_por_territorio",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.territorio.nombre})"

class Dirigencia(models.Model):
    CARGO_DIRIGENCIA_CHOICES = [
        ("Presidente", "Presidente/a"),
        ("Secretario", "Secretario/a"),
        ("Tesorero", "Tesorero/a"),
        ("Director", "Director/a"),
        ("Socio", "Socio/a"),
    ]

    vecino = models.ForeignKey(
        Vecino,
        on_delete=models.CASCADE,
        related_name="dirigencias",
    )
    junta_vecinos = models.ForeignKey(
        JuntaVecinos,
        on_delete=models.CASCADE,
        related_name="dirigencias",
    )
    cargo_dirigencia = models.CharField(max_length=30, choices=CARGO_DIRIGENCIA_CHOICES, default="Socio")
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)
    vigente = models.BooleanField(default=True)

    class Meta:
        verbose_name = "membresía o dirigencia"
        verbose_name_plural = "membresías y dirigencias"
        ordering = ["-vigente", "junta_vecinos__nombre"]

    def __str__(self):
        return f"{self.vecino.nombre_completo} - {self.cargo_dirigencia} ({self.junta_vecinos.nombre})"


class Hito(models.Model):
    ESTADOS_HITO = [
        ("Planificado", "Planificado"),
        ("En ejecución", "En ejecución"),
        ("Completado", "Completado"),
        ("Suspendido", "Suspendido"),
    ]

    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default="")
    territorio = models.ForeignKey(
        Territorio,
        on_delete=models.PROTECT,
        related_name="hitos",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hitos_asignados",
    )
    fecha_comprometida = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS_HITO, default="Planificado", db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "hito"
        verbose_name_plural = "hitos"
        ordering = ["-fecha_comprometida"]

    def __str__(self):
        return f"{self.nombre} ({self.fecha_comprometida})"


# =====================================================================
# 3. CATÁLOGOS DE ATENCIÓN, TRIMESTRES Y METAS NORMALIZADAS
# =====================================================================

class TipoAtencion(models.Model):
    AREA_CHOICES = [
        ("Territorial", "Gestión Territorial"),
        ("Social", "Área Social"),
        ("General", "General"),
    ]

    nombre = models.CharField(max_length=100, unique=True)
    area = models.CharField(max_length=20, choices=AREA_CHOICES, default="General")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "tipo de atención"
        verbose_name_plural = "tipos de atención"
        ordering = ["area", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.area})"


class SubtipoAtencion(models.Model):
    tipo_atencion = models.ForeignKey(
        TipoAtencion,
        on_delete=models.CASCADE,
        related_name="subtipos",
    )
    nombre = models.CharField(max_length=120)
    es_coordinacion = models.BooleanField(
        default=False,
        verbose_name="Es coordinación preparatoria (no pondera puntaje)",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "subtipo de atención"
        verbose_name_plural = "subtipos de atención"
        ordering = ["tipo_atencion__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_atencion", "nombre"],
                name="uq_subtipo_por_tipo",
            ),
        ]

    def __str__(self):
        etiqueta = " [Sin puntaje]" if self.es_coordinacion else ""
        return f"{self.tipo_atencion.nombre} - {self.nombre}{etiqueta}"


class Trimestre(models.Model):
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código (Ej: 2026-Q4)")
    nombre = models.CharField(max_length=80, verbose_name="Nombre (Ej: Trimestre Oct - Dic 2026)")
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField()
    dias_computables = models.PositiveSmallIntegerField(default=63)
    tope_maximo_porcentaje = models.PositiveSmallIntegerField(
        default=120,
        validators=[MinValueValidator(100), MaxValueValidator(150)],
    )
    cerrado = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "trimestre"
        verbose_name_plural = "trimestres"
        ordering = ["-fecha_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_termino__gte=F("fecha_inicio")),
                name="chk_trimestre_fechas_validas",
            ),
        ]

    def __str__(self):
        estado = "Cerrado" if self.cerrado else "Abierto"
        return f"{self.nombre} ({estado})"


class CatalogoMeta(models.Model):
    """Plantilla general de ítems evaluables (separada de la asignación por funcionario)."""
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default="")
    cargo_sugerido = models.ForeignKey(
        Cargo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catalogo_metas",
    )
    es_porcentual = models.BooleanField(
        default=False,
        verbose_name="La meta se mide como porcentaje (Ej: 80% soluciones del Tubo)",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "meta de catálogo"
        verbose_name_plural = "catálogo de metas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class AsignacionMeta(models.Model):
    """Meta asignada específicamente a un funcionario en un trimestre con cantidad y ponderación propias."""
    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="metas_asignadas",
    )
    trimestre = models.ForeignKey(
        Trimestre,
        on_delete=models.PROTECT,
        related_name="asignaciones_meta",
    )
    catalogo_meta = models.ForeignKey(
        CatalogoMeta,
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    cantidad_exigida = models.PositiveIntegerField(verbose_name="Cantidad o % exigido")
    ponderacion = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Ponderación (%)",
    )
    tope_cumplimiento = models.PositiveSmallIntegerField(
        default=120,
        validators=[MinValueValidator(100), MaxValueValidator(150)],
        verbose_name="Tope máximo de cumplimiento (%)",
    )

    class Meta:
        verbose_name = "asignación de meta"
        verbose_name_plural = "asignaciones de metas"
        ordering = ["trimestre", "funcionario", "catalogo_meta__codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["funcionario", "trimestre", "catalogo_meta"],
                name="uq_asignacion_meta_funcionario_trimestre",
            ),
            models.CheckConstraint(
                condition=Q(ponderacion__gte=0, ponderacion__lte=100),
                name="chk_asig_meta_ponderacion_rango",
            ),
            models.CheckConstraint(
                condition=Q(tope_cumplimiento__gte=100, tope_cumplimiento__lte=150),
                name="chk_asig_meta_tope_rango",
            ),
        ]

    def __str__(self):
        return f"{self.funcionario.get_username()} | {self.trimestre.codigo} | {self.catalogo_meta.nombre} ({self.ponderacion}%)"


class Ausencia(models.Model):
    """Ausencias informadas por el Delegado para ajustar días computables del semáforo."""
    TIPO_AUSENCIA_CHOICES = [
        ("Vacaciones", "Vacaciones"),
        ("Día Administrativo", "Día Administrativo"),
        ("Licencia Médica", "Licencia Médica"),
        ("Día Libre", "Día Libre"),
    ]

    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ausencias",
    )
    trimestre = models.ForeignKey(
        Trimestre,
        on_delete=models.PROTECT,
        related_name="ausencias",
    )
    tipo_ausencia = models.CharField(max_length=30, choices=TIPO_AUSENCIA_CHOICES)
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField()
    dias_descontados = models.PositiveSmallIntegerField(default=1)
    observacion = models.TextField(blank=True, default="")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ausencias_registradas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ausencia"
        verbose_name_plural = "ausencias"
        ordering = ["-fecha_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_termino__gte=F("fecha_inicio")),
                name="chk_ausencia_fechas_validas",
            ),
        ]

    def __str__(self):
        return f"{self.funcionario.get_username()} - {self.tipo_ausencia} ({self.dias_descontados} días)"


class AjusteDesempeno(models.Model):
    """Felicitaciones (requieren respaldo formal del Delegado) y Reclamos/Penalizaciones."""
    TIPO_AJUSTE_CHOICES = [
        ("Felicitación", "Felicitación"),
        ("Penalización", "Reclamo / Penalización"),
    ]

    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ajustes_desempeno",
    )
    trimestre = models.ForeignKey(
        Trimestre,
        on_delete=models.PROTECT,
        related_name="ajustes_desempeno",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_AJUSTE_CHOICES)
    porcentaje_ajuste = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Positivo para felicitación (ej. 2.00 o 10.00), negativo para reclamo (ej. -20.00 o -30.00).",
    )
    motivo = models.TextField()
    archivo_respaldo = models.FileField(
        upload_to="respaldos_desempeno/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Respaldo formal (obligatorio para felicitaciones)",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ajustes_registrados",
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ajuste de desempeño"
        verbose_name_plural = "ajustes de desempeño"
        ordering = ["-fecha_registro"]

    def __str__(self):
        return f"{self.tipo} ({self.porcentaje_ajuste}%) - {self.funcionario.get_username()}"


# =====================================================================
# 4. OPERACIÓN: COMPROMISOS (TUBO), EVIDENCIAS, OBSERVACIONES Y METAS LEGACY
# =====================================================================

class Compromiso(models.Model):
    ESTADOS_CHOICES = [
        ("Pendiente", "Pendiente"),
        ("En proceso", "En proceso"),
        ("Completado", "Completado"),
        ("Rechazado", "Rechazado"),
        ("Vencido", "Vencido"),
    ]
    PRIORIDAD_CHOICES = [
        ("Baja", "Baja"),
        ("Media", "Media"),
        ("Alta", "Alta"),
        ("Urgente", "Urgente"),
    ]

    codigo = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="Código")
    titulo = models.CharField(max_length=255, verbose_name="Título del compromiso")
    descripcion = models.TextField(blank=True, default="", verbose_name="Descripción / Instrucciones")
    territorio = models.ForeignKey(Delegacion, on_delete=models.PROTECT, verbose_name="Delegación")
    sector = models.ForeignKey(
        Territorio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compromisos",
        verbose_name="Territorio / Sector",
    )
    vecino = models.ForeignKey(
        Vecino,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compromisos",
    )
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Responsable")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compromisos_creados",
    )
    trimestre = models.ForeignKey(
        Trimestre,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compromisos",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS_CHOICES, default="Pendiente", db_index=True, verbose_name="Estado")
    prioridad = models.CharField(max_length=15, choices=PRIORIDAD_CHOICES, default="Media")
    area = models.CharField(max_length=100, verbose_name="Área")
    solicitante = models.CharField(max_length=150, db_index=True, verbose_name="Solicitante")
    fecha = models.DateField(db_index=True, verbose_name="Fecha de solicitud")
    plazo = models.CharField(max_length=50, verbose_name="Plazo (Ej: 30 DÍAS)")
    fecha_limite = models.DateField(null=True, blank=True, verbose_name="Fecha límite exacta")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "compromiso"
        verbose_name_plural = "compromisos"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["territorio", "estado"], name="idx_comp_deleg_estado"),
            models.Index(fields=["responsable", "estado"], name="idx_comp_resp_estado"),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.titulo}"


class Meta(models.Model):
    """Modelo vigente de metas por cargo (se mantiene para compatibilidad gradual)."""
    cargo = models.ForeignKey("Cargo", on_delete=models.CASCADE, related_name="metas", null=True, blank=True)
    nombre = models.CharField(max_length=250, verbose_name="Ítem a evaluar (Ej: Atención de usuario)")
    valor_objetivo = models.IntegerField(verbose_name="Cantidad meta esperada (Ej: 45)")
    ponderacion = models.IntegerField(verbose_name="Ponderación en % (Ej: 10)")
    vigente = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.ponderacion}%] {self.nombre} - Meta: {self.valor_objetivo}"


class Evidencia(models.Model):
    ESTADOS_VERIFICACION = [
        ("Pendiente", "Pendiente"),
        ("En revisión", "En revisión"),
        ("Aprobada", "Aprobada"),
        ("Rechazada", "Rechazada"),
        ("Solicitud de más antecedentes", "Solicitud de más antecedentes"),
    ]

    codigo = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="Código Verificador")
    funcionario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Funcionario")
    estado = models.CharField(
        max_length=40,
        choices=ESTADOS_VERIFICACION,
        default="En revisión",
        db_index=True,
        verbose_name="Estado",
    )

    fecha_registro = models.DateField(db_index=True, verbose_name="Fecha de Registro")
    item_medir = models.CharField(max_length=150, verbose_name="Ítem a Medir")
    solicitud = models.TextField(verbose_name="Actividad / Solicitud / Problema")
    accion = models.TextField(verbose_name="Acción Realizada")

    vecino = models.ForeignKey(
        Vecino,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias",
    )
    contacto_nombre = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Nombre de contacto")
    contacto_telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")

    subtipo_atencion = models.ForeignKey(
        SubtipoAtencion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias",
    )
    hito = models.ForeignKey(
        Hito,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias",
    )
    trimestre = models.ForeignKey(
        Trimestre,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias",
    )
    es_usuario_delegado = models.BooleanField(
        default=False,
        verbose_name="El solicitante es el propio Delegado (no contabiliza)",
    )

    fotografia = models.ImageField(upload_to="evidencias/%Y/%m/", verbose_name="Fotografía de evidencia")

    compromiso_vinculado = models.OneToOneField(
        Compromiso,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencia_origen",
    )
    observacion = models.TextField(null=True, blank=True)
    meta_relacionada = models.ForeignKey(
        "Meta",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Meta a la que aporta",
    )
    asignacion_meta = models.ForeignKey(
        AsignacionMeta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias",
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias_revisadas",
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    observacion_revision = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ["-fecha_registro"]
        indexes = [
            models.Index(fields=["funcionario", "estado"], name="idx_ev_func_estado"),
            models.Index(fields=["funcionario", "fecha_registro"], name="idx_ev_func_fecha"),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.funcionario.get_username()}"

    @property
    def puntaje_valido(self):
        """
        Reglas de negocio:
        - Solo cuenta si está Aprobada.
        - Si el solicitante es el delegado -> 0 puntos.
        - Si es coordinación preparatoria -> 0 puntos.
        - Sin nombre y teléfono del vecino -> 0 puntos.
        """
        if self.estado != "Aprobada":
            return 0
        if self.es_usuario_delegado:
            return 0
        if self.subtipo_atencion and self.subtipo_atencion.es_coordinacion:
            return 0
        nombre_ok = bool((self.contacto_nombre or "").strip()) or bool(self.vecino and self.vecino.nombre_completo.strip())
        fono_ok = bool((self.contacto_telefono or "").strip()) or bool(self.vecino and self.vecino.telefono.strip())
        if not (nombre_ok and fono_ok):
            return 0
        return 1


class Observacion(models.Model):
    compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name="observaciones")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    texto = models.TextField()
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidencias_evaluadas",
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]


# =====================================================================
# 5. MÓDULO ÁREA SOCIAL (ALINEADO A EXCEL REAL Y MÁXIMO 3 GESTIONES)
# =====================================================================

class CasoSocial(models.Model):
    """Agrupa hasta 3 gestiones de una persona por RUT, con código SOC automático."""
    codigo = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True, verbose_name="Código SOC")
    vecino = models.ForeignKey(
        Vecino,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="casos_sociales",
    )
    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="casos_sociales",
    )
    rut = models.CharField(max_length=15, unique=True, db_index=True, verbose_name="RUT del Ciudadano")
    usuario_nombre = models.CharField(max_length=150, db_index=True, verbose_name="Nombre Completo")
    telefono = models.CharField(max_length=50, blank=True, null=True)
    fecha_ingreso = models.DateField(auto_now_add=True, db_index=True)
    funcionario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "caso social"
        verbose_name_plural = "casos sociales"
        ordering = ["-fecha_ingreso"]

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = f"SOC-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo or 'SIN-COD'} | {self.rut} - {self.usuario_nombre}"

    @property
    def gestiones_realizadas(self):
        return self.gestiones.count()


class GestionSocial(models.Model):
    """Detalle individual de cada atención dentro de un Caso Social (1ª, 2ª o 3ª gestión)."""
    ESTADOS_VALIDACION = [
        ("Pendiente", "Pendiente"),
        ("Aprobada", "Aprobada"),
        ("Rechazada", "Rechazada"),
        ("Solicitud de más antecedentes", "Solicitud de más antecedentes"),
    ]

    caso = models.ForeignKey(CasoSocial, on_delete=models.CASCADE, related_name="gestiones")
    tipo_atencion = models.ForeignKey(
        TipoAtencion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_sociales",
    )
    subtipo_atencion = models.ForeignKey(
        SubtipoAtencion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_sociales",
    )
    sub_atencion = models.CharField(max_length=100, verbose_name="Tipo de Atención")
    accion_realizada = models.CharField(max_length=100)
    fecha_programada = models.DateField(null=True, blank=True, verbose_name="Fecha programada de visita")
    fecha_ejecucion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de ejecución (visita / entrega informe / entrega beneficio)",
    )
    detalle_accion = models.TextField()
    evidencia_codigo = models.CharField(max_length=50, blank=True, null=True)
    imagen_verificacion = models.FileField(
        upload_to="evidencias_social/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Imagen o documento de verificación",
    )
    validacion = models.CharField(max_length=50, choices=ESTADOS_VALIDACION, default="Pendiente", db_index=True)

    requiere_terreno = models.BooleanField(default=False)
    derivar_agenda = models.BooleanField(default=False)
    compromiso_derivado = models.ForeignKey(
        Compromiso,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_sociales_origen",
    )
    asignacion_meta = models.ForeignKey(
        AsignacionMeta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_sociales",
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestiones_sociales_revisadas",
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    observacion_revision = models.TextField(blank=True, default="")
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "gestión social"
        verbose_name_plural = "gestiones sociales"
        ordering = ["fecha_registro"]
        indexes = [
            models.Index(fields=["validacion", "accion_realizada"], name="idx_gsoc_val_accion"),
        ]

    def __str__(self):
        return f"Gestión {self.id} de {self.caso.rut}"

    @property
    def puntaje_valido(self):
        """Suma 1 punto si está aprobada, no es coordinación preparatoria y tiene nombre y teléfono."""
        if self.validacion not in ("Aprobado", "Aprobada"):
            return 0
        if self.subtipo_atencion and self.subtipo_atencion.es_coordinacion:
            return 0
        if not ((self.caso.usuario_nombre or "").strip() and (self.caso.telefono or "").strip()):
            return 0
        return 1