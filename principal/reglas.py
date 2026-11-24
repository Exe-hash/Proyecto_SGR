from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import Evidencia, GestionSocial, Trimestre, Vecino

LIMITE_DIARIO_ACTIVIDADES = 7

ESTADOS_APROBADOS = {"Aprobada", "Aprobado"}

ESTADOS_VERIFICACION_OFICIALES = (
    "Pendiente",
    "Aprobada",
    "Rechazada",
    "Solicitud de más antecedentes",
)

ESTADOS_PENDIENTES_REVISION = {
    "Pendiente",
    "En revisión",
    "Solicitud de más antecedentes",
}


def es_registro_aprobado(estado: str | None) -> bool:
    """Indica si un registro ya fue aprobado y, por regla de negocio, es inmutable."""
    return (estado or "").strip() in ESTADOS_APROBADOS


def validar_registro_editable(estado: str | None, etiqueta: str = "El registro") -> None:
    """Impide cualquier modificación o re-dictamen sobre un registro aprobado."""
    if es_registro_aprobado(estado):
        raise ValidationError(
            f"{etiqueta} ya se encuentra en estado Aprobada y no permite modificaciones."
        )


def validar_estado_verificacion(estado: str | None) -> str:
    """Garantiza que el dictamen pertenezca a los 4 estados oficiales del flujo."""
    estado_limpio = (estado or "").strip()
    if estado_limpio not in ESTADOS_VERIFICACION_OFICIALES:
        raise ValidationError(
            "Estado de verificación inválido. Use: Pendiente, Aprobada, Rechazada o Solicitud de más antecedentes."
        )
    return estado_limpio


def inicio_semana_actual(hoy: date | None = None) -> date:
    """Devuelve el lunes de la semana calendario vigente."""
    referencia = hoy or timezone.localdate()
    return referencia - timedelta(days=referencia.weekday())


def validar_semana_abierta(fecha_objetivo: date, hoy: date | None = None) -> None:
    """
    Impide el ingreso tardío de actividades o gestiones correspondientes
    a una semana calendario ya cerrada o a un trimestre cerrado.
    """
    referencia = hoy or timezone.localdate()
    lunes_actual = inicio_semana_actual(referencia)

    if fecha_objetivo < lunes_actual:
        raise ValidationError(
            f"No se permite el ingreso tardío de gestiones de una semana cerrada "
            f"(solo se aceptan fechas desde el lunes {lunes_actual.strftime('%d/%m/%Y')})."
        )

    trimestre_cerrado = Trimestre.objects.filter(
        fecha_inicio__lte=fecha_objetivo,
        fecha_termino__gte=fecha_objetivo,
        cerrado=True,
    ).exists()
    if trimestre_cerrado:
        raise ValidationError(
            "La fecha seleccionada corresponde a un trimestre cerrado y no admite nuevos ingresos."
        )


def contar_actividades_del_dia(
    usuario,
    fecha_objetivo: date,
    excluir_evidencia_id: int | None = None,
    excluir_gestion_id: int | None = None,
) -> int:
    """Cuenta actividades (Evidencias + Gestiones Sociales) registradas por un funcionario en un día."""
    evidencias_qs = Evidencia.objects.filter(
        funcionario=usuario,
        fecha_registro=fecha_objetivo,
    )
    if excluir_evidencia_id:
        evidencias_qs = evidencias_qs.exclude(pk=excluir_evidencia_id)

    gestiones_qs = GestionSocial.objects.filter(
        caso__funcionario=usuario,
    ).filter(
        Q(fecha_ejecucion=fecha_objetivo)
        | Q(fecha_ejecucion__isnull=True, fecha_registro__date=fecha_objetivo)
    )
    if excluir_gestion_id:
        gestiones_qs = gestiones_qs.exclude(pk=excluir_gestion_id)

    return evidencias_qs.count() + gestiones_qs.count()


def validar_limite_diario(
    usuario,
    fecha_objetivo: date,
    excluir_evidencia_id: int | None = None,
    excluir_gestion_id: int | None = None,
) -> None:
    """Aplica el tope máximo de 7 actividades diarias por funcionario."""
    total_actual = contar_actividades_del_dia(
        usuario=usuario,
        fecha_objetivo=fecha_objetivo,
        excluir_evidencia_id=excluir_evidencia_id,
        excluir_gestion_id=excluir_gestion_id,
    )
    if total_actual >= LIMITE_DIARIO_ACTIVIDADES:
        raise ValidationError(
            f"Límite diario alcanzado: no se pueden registrar más de {LIMITE_DIARIO_ACTIVIDADES} "
            f"actividades para el día {fecha_objetivo.strftime('%d/%m/%Y')}."
        )


def obtener_trimestre_para_fecha(fecha_objetivo: date) -> Trimestre | None:
    """Resuelve el trimestre registrado en BD al que pertenece la fecha indicada."""
    return (
        Trimestre.objects.filter(
            fecha_inicio__lte=fecha_objetivo,
            fecha_termino__gte=fecha_objetivo,
        )
        .order_by("-fecha_inicio")
        .first()
    )


def normalizar_rut(rut: str | None) -> str:
    """Formatea un RUT chileno a XX.XXX.XXX-Y (compatible con el formateo del frontend)."""
    limpio = "".join(c for c in (rut or "").upper() if c.isdigit() or c == "K")
    if len(limpio) < 2:
        return (rut or "").strip().upper()
    cuerpo, dv = limpio[:-1], limpio[-1]
    cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".") if cuerpo.isdigit() else cuerpo
    return f"{cuerpo_formateado}-{dv}"


def obtener_o_actualizar_vecino(
    rut: str | None,
    nombre: str | None,
    telefono: str | None,
    territorio=None,
) -> Vecino | None:
    """
    Si se entrega RUT, busca o registra el Vecino en BD para habilitar
    el autocompletado futuro sin duplicar registros.
    """
    rut_texto = (rut or "").strip()
    if not rut_texto:
        return None

    rut_norm = normalizar_rut(rut_texto)
    rut_sin_puntos = rut_norm.replace(".", "")
    nombre_limpio = (nombre or "").strip()
    telefono_limpio = (telefono or "").strip()

    vecino = Vecino.objects.filter(
        Q(rut__iexact=rut_norm) | Q(rut__iexact=rut_sin_puntos)
    ).first()

    if vecino:
        actualizados = []
        if nombre_limpio and not vecino.nombre_completo.strip():
            vecino.nombre_completo = nombre_limpio
            actualizados.append("nombre_completo")
        if telefono_limpio and not vecino.telefono.strip():
            vecino.telefono = telefono_limpio
            actualizados.append("telefono")
        if territorio and not vecino.territorio_id:
            vecino.territorio = territorio
            actualizados.append("territorio")
        if actualizados:
            vecino.save(update_fields=actualizados)
        return vecino

    return Vecino.objects.create(
        rut=rut_norm,
        nombre_completo=nombre_limpio or "Sin nombre informado",
        telefono=telefono_limpio,
        territorio=territorio,
    )


def motivos_sin_puntaje_evidencia(evidencia: Evidencia) -> list[str]:
    """Devuelve las razones de negocio por las cuales una evidencia no suma puntaje."""
    motivos = []
    if evidencia.es_usuario_delegado:
        motivos.append("Solicitante es el Delegado (no contabiliza)")
    if evidencia.subtipo_atencion and evidencia.subtipo_atencion.es_coordinacion:
        motivos.append("Coordinación preparatoria (no pondera)")

    nombre_ok = bool((evidencia.contacto_nombre or "").strip()) or bool(
        evidencia.vecino and evidencia.vecino.nombre_completo.strip()
    )
    fono_ok = bool((evidencia.contacto_telefono or "").strip()) or bool(
        evidencia.vecino and evidencia.vecino.telefono.strip()
    )
    if not (nombre_ok and fono_ok):
        motivos.append("Falta nombre o teléfono del ciudadano (0 puntos)")

    return motivos


def motivos_sin_puntaje_gestion(gestion: GestionSocial) -> list[str]:
    """Devuelve las razones de negocio por las cuales una gestión social no suma puntaje."""
    motivos = []
    if gestion.subtipo_atencion and gestion.subtipo_atencion.es_coordinacion:
        motivos.append("Coordinación preparatoria (no pondera)")
    nombre_ok = bool((gestion.caso.usuario_nombre or "").strip())
    fono_ok = bool((gestion.caso.telefono or "").strip())
    if not (nombre_ok and fono_ok):
        motivos.append("Falta nombre o teléfono del ciudadano (0 puntos)")
    return motivos