from functools import wraps
import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import UsuarioCRUDForm
from .models import (
    CasoSocial,
    Compromiso,
    Delegacion,
    Evidencia,
    GestionSocial,
    Meta,
    Observacion,
    Dirigencia,
    JuntaVecinos,
)
from .models import Cargo, CatalogoMeta, TipoOrganizacion
from .periodos import contexto_periodo_actual

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from .models import AjusteDesempeno, Territorio, Vecino

from datetime import date

import os
from django.core.exceptions import PermissionDenied, ValidationError
from .models import AsignacionMeta, Hito, SubtipoAtencion, TipoAtencion
from .reglas import (
    LIMITE_DIARIO_ACTIVIDADES,
    contar_actividades_del_dia,
    es_registro_aprobado,
    inicio_semana_actual,
    motivos_sin_puntaje_evidencia,
    motivos_sin_puntaje_gestion,
    normalizar_rut,
    obtener_o_actualizar_vecino,
    obtener_trimestre_para_fecha,
    validar_estado_verificacion,
    validar_limite_diario,
    validar_registro_editable,
    validar_semana_abierta,
    fecha_minima_semana_abierta,
    vincular_vecino_a_organizacion,
)

from django.urls import reverse, reverse_lazy
from .models import CartaOficinaPartes

from decimal import Decimal, InvalidOperation
from .metricas import (
    calcular_resumen_equipo,
    calcular_resumen_funcionario,
    enviar_notificacion_ajuste,
    resolver_trimestre_periodo,
)
from .models import Ausencia, Trimestre

def usuario_tiene_rol(usuario, *roles):
    """Indica si un usuario posee al menos uno de los roles solicitados."""
    return (
        usuario.is_authenticated
        and (
            usuario.is_superuser
            or usuario.groups.filter(name__in=roles).exists()
        )
    )


def requiere_roles(*roles):
    """Protege una vista y devuelve error 403 si el rol no está autorizado."""

    def decorador(vista):
        @login_required(login_url="principal:inicio")
        @wraps(vista)
        def vista_protegida(request, *args, **kwargs):
            if not usuario_tiene_rol(request.user, *roles):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return vista_protegida

    return decorador


def contexto_usuario(request, **contexto):
    """
    Agrega al template los permisos visuales y los datos reales
    del perfil del usuario que inició sesión.
    """
    perfil = getattr(request.user, "perfil", None)

    contexto.update(
        {
            "puede_registrar_actividades": usuario_tiene_rol(request.user, "Funcionario"),
            "puede_ver_agenda": usuario_tiene_rol(request.user, "Funcionario", "Supervisor"),
            "es_area_social": True if perfil and perfil.cargo and 'social' in perfil.cargo.nombre.lower() else False,
            "puede_ver_equipo": usuario_tiene_rol(request.user, "Supervisor"),
            "puede_verificar_evidencias": usuario_tiene_rol(request.user, "Supervisor"),
            "puede_administrar": usuario_tiene_rol(request.user, "Administrador"),
            "nombre_usuario": (request.user.get_full_name().strip() or request.user.get_username()),
            "cargo_usuario": perfil.cargo.nombre if perfil else "Sin cargo asignado",
            "delegacion_usuario": perfil.delegacion.nombre if perfil else "Sin delegación asignada",
        }
    )
    contexto.update(contexto_periodo_actual(request))  # <--- AQUÍ VA

    return contexto

def _rango_periodo_activo(request):
    """Devuelve (fecha_inicio, fecha_fin) del trimestre seleccionado en la barra superior."""
    periodo = contexto_periodo_actual(request)["periodo_activo"]
    return periodo["fecha_inicio"], periodo["fecha_fin"]

def _resolver_usuario_objetivo(request):
    """
    Permite a Administrador inspeccionar cualquier funcionario y a Supervisor
    inspeccionar funcionarios de su delegación desde Mi Panel / Mis Evidencias.
    """
    es_admin = request.user.is_superuser or usuario_tiene_rol(request.user, "Administrador")
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")

    if not (es_admin or es_supervisor):
        return request.user, {
            "puede_inspeccionar_funcionarios": False,
            "funcionarios_buscador": [],
            "usuario_objetivo": request.user,
            "viendo_otro_usuario": False,
        }

    funcionarios_qs = (
        User.objects.filter(is_active=True, groups__name="Funcionario")
        .select_related("perfil__cargo", "perfil__delegacion")
        .order_by("first_name", "last_name", "username")
        .distinct()
    )
    if es_supervisor and not es_admin:
        perfil_sup = getattr(request.user, "perfil", None)
        if perfil_sup and perfil_sup.delegacion_id:
            funcionarios_qs = funcionarios_qs.filter(perfil__delegacion_id=perfil_sup.delegacion_id)

    param = request.GET.get("funcionario")
    if param == "propio":
        request.session.pop("funcionario_inspeccionado_id", None)
        objetivo_id = None
    elif param and param.isdigit():
        objetivo_id = int(param)
        request.session["funcionario_inspeccionado_id"] = objetivo_id
    else:
        objetivo_id = request.session.get("funcionario_inspeccionado_id")

    usuario_objetivo = request.user
    if objetivo_id:
        encontrado = funcionarios_qs.filter(pk=objetivo_id).first()
        if encontrado:
            usuario_objetivo = encontrado
        else:
            request.session.pop("funcionario_inspeccionado_id", None)

    return usuario_objetivo, {
        "puede_inspeccionar_funcionarios": True,
        "funcionarios_buscador": funcionarios_qs,
        "usuario_objetivo": usuario_objetivo,
        "viendo_otro_usuario": usuario_objetivo.pk != request.user.pk,
    }

def renderizar(request, plantilla, contexto=None):
    """Renderiza una plantilla incluyendo el contexto del usuario conectado."""
    return render(
        request,
        plantilla,
        contexto_usuario(request, **(contexto or {})),
    )

def destino_por_rol(usuario):
    """Devuelve la ruta de la página principal según el rol y cargo del usuario."""
    if usuario_tiene_rol(usuario, "Administrador"):
        return "principal:administracion"
    if usuario_tiene_rol(usuario, "Supervisor"):
        return "principal:equipo"
    perfil = getattr(usuario, "perfil", None)
    if perfil and perfil.cargo and "social" in perfil.cargo.nombre.lower():
        return "principal:area_social"
    return "principal:panel"


def landing(request):
    """Página pública de bienvenida del SGR."""
    return render(request, "principal/landing.html")

def inicio(request):
    if request.method == "POST":
        nombre_usuario = request.POST.get("username", "").strip()
        contrasena = request.POST.get("password", "")

        usuario = authenticate(
            request,
            username=nombre_usuario,
            password=contrasena,
        )

        if usuario is not None:
            login(request, usuario)
            perfil = getattr(usuario, "perfil", None)
            if perfil and perfil.debe_cambiar_clave:
                messages.warning(
                    request,
                    "Ingresaste con una contraseña temporal. Debes actualizarla para continuar.",
                )
                return redirect("principal:cambiar_password_inicial")
            return redirect(destino_por_rol(usuario))

        return render(
            request,
            "principal/inicio.html",
            {"error_inicio": "Usuario o contraseña incorrectos."},
        )

    return render(request, "principal/inicio.html")

MAX_ARCHIVO_BYTES = 5 * 1024 * 1024  # 5 MB


def _validar_archivo_subido(archivo, extensiones_permitidas):
    """Valida extensión y tamaño máximo de archivos en servidor."""
    if not archivo:
        return
    ext = os.path.splitext(archivo.name)[1].lower()
    if ext not in extensiones_permitidas:
        permitidas_txt = ", ".join(sorted(extensiones_permitidas))
        raise ValidationError(f"Formato de archivo no permitido ({ext}). Use: {permitidas_txt}.")
    if archivo.size > MAX_ARCHIVO_BYTES:
        raise ValidationError("El archivo supera el tamaño máximo permitido de 5 MB.")
    
@requiere_roles("Funcionario")
@transaction.atomic
def actividades(request):
    hoy = timezone.localdate()
    lunes_semana = fecha_minima_semana_abierta(hoy)
    perfil = getattr(request.user, "perfil", None)
    trimestre_actual = obtener_trimestre_para_fecha(hoy)

    if request.method == "POST":
        fecha_str = (request.POST.get("fecha") or "").strip()
        actividad_txt = (request.POST.get("actividad") or "").strip()
        accion_txt = (request.POST.get("accion") or "").strip()
        rut_vecino = (request.POST.get("rut_vecino") or "").strip()
        contacto = (request.POST.get("contacto") or "").strip()
        telefono = (request.POST.get("telefono") or "").strip()
        fotografia = request.FILES.get("fotografia")
        meta_id = (request.POST.get("meta_id") or "").strip() or None
        asignacion_meta_id = (request.POST.get("asignacion_meta_id") or "").strip() or None
        subtipo_id = (request.POST.get("subtipo_atencion_id") or "").strip() or None
        hito_id = (request.POST.get("hito_id") or "").strip() or None
        es_usuario_delegado = request.POST.get("es_usuario_delegado") == "on"

        try:
            fecha_reg = date.fromisoformat(fecha_str) if fecha_str else hoy
        except ValueError:
            messages.error(request, "La fecha de registro no tiene un formato válido.")
            return redirect("principal:actividades")

        if not (actividad_txt and accion_txt):
            messages.error(request, "Debes completar la actividad/solicitud y la acción realizada.")
            return redirect("principal:actividades")

        if not fotografia:
            messages.error(request, "Debes adjuntar una fotografía de evidencia.")
            return redirect("principal:actividades")

        try:
            validar_semana_abierta(fecha_reg, hoy=hoy)
            validar_limite_diario(request.user, fecha_reg)
            _validar_archivo_subido(fotografia, {".jpg", ".jpeg", ".png"})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:actividades")

        sector_id = (request.POST.get("sector_id") or "").strip() or None
        sector_obj = Territorio.objects.filter(pk=sector_id).first() if sector_id else None
        subtipo_obj = SubtipoAtencion.objects.filter(pk=subtipo_id, activo=True).first() if subtipo_id else None
        hito_obj = Hito.objects.filter(pk=hito_id).first() if hito_id else None
        trimestre_obj = obtener_trimestre_para_fecha(fecha_reg)

        asig_obj = (
            AsignacionMeta.objects.select_related("catalogo_meta")
            .filter(pk=asignacion_meta_id, funcionario=request.user)
            .first()
            if asignacion_meta_id
            else None
        )
        meta_obj = Meta.objects.filter(pk=meta_id, vigente=True).first() if meta_id else None

        vecino_obj = obtener_o_actualizar_vecino(
            rut=rut_vecino,
            nombre=contacto,
            telefono=telefono,
            territorio=sector_obj,
        )
        vincular_vecino_a_organizacion(vecino_obj, request.POST.get("junta_vecinos_id"))
        if vecino_obj:
            if not contacto:
                contacto = vecino_obj.nombre_completo
            if not telefono:
                telefono = vecino_obj.telefono

        item_medir_txt = (
            asig_obj.catalogo_meta.nombre
            if asig_obj
            else (
                meta_obj.nombre
                if meta_obj
                else (subtipo_obj.nombre if subtipo_obj else "Actividad territorial")
            )
        )[:150]

        codigo_evi = f"EVI-{uuid.uuid4().hex[:5].upper()}"
        nueva_evidencia = Evidencia(
            codigo=codigo_evi,
            funcionario=request.user,
            estado="Pendiente",
            fecha_registro=fecha_reg,
            item_medir=item_medir_txt,
            solicitud=actividad_txt,
            accion=accion_txt,
            vecino=vecino_obj,
            contacto_nombre=contacto or None,
            contacto_telefono=telefono or None,
            subtipo_atencion=subtipo_obj,
            hito=hito_obj,
            trimestre=trimestre_obj,
            es_usuario_delegado=es_usuario_delegado,
            fotografia=fotografia,
            meta_relacionada=meta_obj,
            asignacion_meta=asig_obj,
        )

        if request.POST.get("crear_compromiso") == "on":
            id_delegacion = request.POST.get("territorio")
            delegacion = (
                Delegacion.objects.filter(pk=id_delegacion).first()
                or (perfil.delegacion if perfil else None)
                or Delegacion.objects.first()
            )
            responsable_id = (request.POST.get("responsable_id") or "").strip()
            responsable = (
                User.objects.filter(pk=responsable_id, is_active=True).first()
                if responsable_id.isdigit()
                else request.user
            ) or request.user

            fecha_comp_str = (request.POST.get("fecha_comprometida") or "").strip()
            try:
                fecha_lim = date.fromisoformat(fecha_comp_str) if fecha_comp_str else fecha_reg
            except ValueError:
                fecha_lim = fecha_reg

            codigo_com = f"COM-{uuid.uuid4().hex[:5].upper()}"
            nuevo_compromiso = Compromiso.objects.create(
                codigo=codigo_com,
                titulo=actividad_txt[:250],
                descripcion=accion_txt,
                territorio=delegacion,
                sector=sector_obj,
                vecino=vecino_obj,
                responsable=responsable,
                creado_por=request.user,
                trimestre=trimestre_obj,
                area=(request.POST.get("area") or "Gestión territorial").strip(),
                solicitante=contacto or "Sin especificar",
                fecha=fecha_reg,
                plazo=fecha_lim.strftime("%Y-%m-%d"),
                fecha_limite=fecha_lim,
            )
            nueva_evidencia.compromiso_vinculado = nuevo_compromiso

        nueva_evidencia.save()

        motivos = motivos_sin_puntaje_evidencia(nueva_evidencia)
        if motivos:
            messages.warning(
                request,
                f"Evidencia {codigo_evi} registrada en estado Pendiente. Nota de puntaje: {' · '.join(motivos)}.",
            )
        else:
            messages.success(request, f"Evidencia {codigo_evi} registrada correctamente y enviada a verificación.")
        return redirect("principal:evidencias")

    if perfil and perfil.cargo:
        metas_reales = Meta.objects.filter(vigente=True, cargo=perfil.cargo)
        if not metas_reales.exists():
            metas_reales = Meta.objects.filter(vigente=True)
    else:
        metas_reales = Meta.objects.filter(vigente=True)

    asignaciones_qs = AsignacionMeta.objects.filter(funcionario=request.user).select_related(
        "catalogo_meta", "trimestre"
    )
    if trimestre_actual:
        asignaciones_trim = asignaciones_qs.filter(trimestre=trimestre_actual)
        if asignaciones_trim.exists():
            asignaciones_qs = asignaciones_trim

    funcionarios_disponibles = (
        User.objects.filter(is_active=True, groups__name="Funcionario")
        .order_by("first_name", "last_name", "username")
        .distinct()
    )

    return renderizar(
        request,
        "principal/actividades.html",
        {
            "pagina": "actividades",
            "delegaciones": Delegacion.objects.filter(activa=True),
            "territorios": Territorio.objects.filter(activo=True).select_related("delegacion"),
            "subtipos_atencion": SubtipoAtencion.objects.filter(activo=True).select_related("tipo_atencion"),
            "hitos_activos": Hito.objects.exclude(estado="Suspendido").select_related("territorio"),
            "metas_reales": metas_reales,
            "asignaciones_meta": asignaciones_qs,
            "funcionarios_disponibles": funcionarios_disponibles,
            "actividades_hoy": contar_actividades_del_dia(request.user, hoy),
            "limite_diario": LIMITE_DIARIO_ACTIVIDADES,
            "fecha_minima_semana": lunes_semana,
            "delegacion_actual_id": perfil.delegacion_id if perfil else None,
            "organizaciones_activas": JuntaVecinos.objects.filter(activa=True).select_related("territorio").order_by("nombre"),
        },
    )


def _compromiso_esta_bloqueado(compromiso):
    """Un compromiso queda inmutable si está Completado o su evidencia origen ya fue Aprobada."""
    if compromiso.estado == "Completado":
        return True
    try:
        ev_origen = compromiso.evidencia_origen
    except Evidencia.DoesNotExist:
        ev_origen = None
    return bool(ev_origen and es_registro_aprobado(ev_origen.estado))


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def agenda(request):
    perfil = getattr(request.user, "perfil", None)
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")
    delegacion_usuario = perfil.delegacion if (perfil and not request.user.is_superuser) else None


    if request.method == "POST":
        codigo_recibido = (request.POST.get("codigo") or "").strip()
        nuevo_estado = (request.POST.get("nuevo_estado") or "").strip()
        nuevo_texto = (request.POST.get("observacion") or "").strip()

        if not (codigo_recibido and nuevo_estado):
            messages.error(request, "Datos incompletos para actualizar el compromiso.")
            return redirect("principal:agenda")

        if nuevo_estado not in {"Pendiente", "En proceso", "Completado", "Rechazado", "Vencido"}:
            messages.error(request, "Estado de compromiso inválido.")
            return redirect("principal:agenda")

        compromiso = get_object_or_404(
            Compromiso.objects.select_related("evidencia_origen"),
            codigo=codigo_recibido,
        )


        if delegacion_usuario and compromiso.territorio_id != delegacion_usuario.id:
            raise PermissionDenied("No tienes permiso para acceder a compromisos de otra delegación.")


        es_dueno = (
            compromiso.responsable_id == request.user.id
            or compromiso.creado_por_id == request.user.id
        )
        if not (es_dueno or es_supervisor):
            raise PermissionDenied("Solo puedes modificar tus propios registros en el Tubo.")


        if _compromiso_esta_bloqueado(compromiso):
            messages.error(
                request,
                f"El compromiso {compromiso.codigo} ya está aprobado/completado y no permite modificaciones.",
            )
            return redirect("principal:agenda")

        compromiso.estado = nuevo_estado
        compromiso.save(update_fields=["estado", "actualizado_en"])

        if nuevo_texto:
            Observacion.objects.create(
                compromiso=compromiso,
                autor=request.user,
                texto=nuevo_texto,
            )

        messages.success(request, f"Compromiso {compromiso.codigo} actualizado a '{nuevo_estado}'.")
        return redirect("principal:agenda")


    tab_activo = request.GET.get("tab", "seguimiento")
    if tab_activo not in ("seguimiento", "cartas"):
        tab_activo = "seguimiento"

    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    fecha_desde_str = (request.GET.get("fecha_desde") or "").strip()
    fecha_hasta_str = (request.GET.get("fecha_hasta") or "").strip()
    filtro_func = (request.GET.get("funcionario_id") or "").strip()
    filtro_estado = (request.GET.get("estado") or "").strip()
    filtro_area = (request.GET.get("area") or "").strip()
    filtro_sector = (request.GET.get("sector_id") or "").strip()
    filtro_deleg = (request.GET.get("delegacion_id") or "").strip()

    try:
        fecha_desde = date.fromisoformat(fecha_desde_str) if fecha_desde_str else inicio_periodo
    except ValueError:
        fecha_desde = inicio_periodo
    try:
        fecha_hasta = date.fromisoformat(fecha_hasta_str) if fecha_hasta_str else fin_periodo
    except ValueError:
        fecha_hasta = fin_periodo


    compromisos_qs = (
        Compromiso.objects.filter(fecha__range=(fecha_desde, fecha_hasta))
        .select_related("territorio", "sector", "vecino", "responsable", "creado_por", "evidencia_origen")
        .prefetch_related("observaciones__autor")
        .order_by("-fecha", "-id")
    )
    cartas_qs = (
        CartaOficinaPartes.objects.filter(fecha_ingreso__range=(fecha_desde, fecha_hasta))
        .select_related("delegacion", "vecino", "responsable", "creado_por")
        .order_by("-fecha_ingreso", "-id")
    )

    if delegacion_usuario:
        compromisos_qs = compromisos_qs.filter(territorio=delegacion_usuario)
        cartas_qs = cartas_qs.filter(delegacion=delegacion_usuario)
    elif filtro_deleg.isdigit():
        compromisos_qs = compromisos_qs.filter(territorio_id=int(filtro_deleg))
        cartas_qs = cartas_qs.filter(delegacion_id=int(filtro_deleg))


    total_seguimiento = compromisos_qs.count()
    total_cartas_all = cartas_qs.count()


    if filtro_func.isdigit():
        compromisos_qs = compromisos_qs.filter(responsable_id=int(filtro_func))
        cartas_qs = cartas_qs.filter(responsable_id=int(filtro_func))

    if filtro_area:
        compromisos_qs = compromisos_qs.filter(area__iexact=filtro_area)
    if filtro_sector.isdigit():
        compromisos_qs = compromisos_qs.filter(sector_id=int(filtro_sector))

    if filtro_estado:
        if tab_activo == "seguimiento":
            compromisos_qs = compromisos_qs.filter(estado=filtro_estado)
        else:
            cartas_qs = cartas_qs.filter(estado=filtro_estado)


    compromisos_reales = []
    for c in compromisos_qs:
        bloqueado = _compromiso_esta_bloqueado(c)
        es_dueno = c.responsable_id == request.user.id or c.creado_por_id == request.user.id
        c.esta_bloqueado_ui = bloqueado
        c.es_dueno_ui = es_dueno
        c.puede_editar_ui = (not bloqueado) and (es_dueno or es_supervisor)
        compromisos_reales.append(c)


    cartas_lista = list(cartas_qs)
    c_en_proceso = sum(1 for x in cartas_lista if x.estado == "En proceso")
    c_aprobada = sum(1 for x in cartas_lista if x.estado == "Aprobada")
    c_finalizada = sum(1 for x in cartas_lista if x.estado == "Finalizada")
    c_no_aplica = sum(1 for x in cartas_lista if x.estado == "No aplica")
    c_aplicables = c_en_proceso + c_aprobada + c_finalizada

    resumen_cartas = {
        "total": len(cartas_lista),
        "aplicables": c_aplicables,
        "en_proceso": c_en_proceso,
        "aprobada": c_aprobada,
        "finalizada": c_finalizada,
        "no_aplica": c_no_aplica,
        "pct_en_proceso": round((c_en_proceso / c_aplicables * 100), 2) if c_aplicables else 0,
        "pct_aprobada": round((c_aprobada / c_aplicables * 100), 2) if c_aplicables else 0,
        "pct_finalizada": round((c_finalizada / c_aplicables * 100), 2) if c_aplicables else 0,
    }

    for carta in cartas_lista:
        es_dueno_carta = carta.responsable_id == request.user.id or carta.creado_por_id == request.user.id
        carta.es_dueno_ui = es_dueno_carta
        carta.puede_editar_ui = (not carta.esta_bloqueada) and (es_dueno_carta or es_supervisor)

    funcionarios_qs = User.objects.filter(is_active=True).select_related("perfil__delegacion").order_by("first_name", "username")
    if delegacion_usuario:
        funcionarios_qs = funcionarios_qs.filter(perfil__delegacion=delegacion_usuario)

    territorios_qs = Territorio.objects.filter(activo=True).select_related("delegacion")
    if delegacion_usuario:
        territorios_qs = territorios_qs.filter(delegacion=delegacion_usuario)

    return renderizar(
        request,
        "principal/agenda.html",
        {
            "pagina": "agenda",
            "tab_activo": tab_activo,
            "compromisos_reales": compromisos_reales,
            "cartas_reales": cartas_lista,
            "resumen_cartas": resumen_cartas,
            "total_seguimiento": total_seguimiento,
            "total_cartas": total_cartas_all,
            "funcionarios_filtro": funcionarios_qs,
            "territorios_filtro": territorios_qs,
            "delegaciones_filtro": Delegacion.objects.filter(activa=True),
            "es_superusuario": request.user.is_superuser,
            "es_supervisor": es_supervisor,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "filtro_func": filtro_func,
            "filtro_estado": filtro_estado,
            "filtro_area": filtro_area,
            "filtro_sector": filtro_sector,
            "filtro_deleg": filtro_deleg,
            "organizaciones_activas": JuntaVecinos.objects.filter(activa=True).select_related("territorio").order_by("nombre"),
        },
    )


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def crear_carta(request):
    """Registra una nueva carta en el Tubo de Cartas de Oficina de Partes."""
    if request.method != "POST":
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    hoy = timezone.localdate()
    perfil = getattr(request.user, "perfil", None)
    delegacion_id = (request.POST.get("delegacion_id") or "").strip()

    if request.user.is_superuser and delegacion_id.isdigit():
        delegacion = Delegacion.objects.filter(pk=int(delegacion_id)).first()
    else:
        delegacion = perfil.delegacion if perfil else Delegacion.objects.first()

    if not delegacion:
        messages.error(request, "No se pudo determinar la delegación para registrar la carta.")
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    remitente = (request.POST.get("remitente") or "").strip()
    actividad_tema = (request.POST.get("actividad_tema") or "").strip()
    if not (remitente and actividad_tema):
        messages.error(request, "Debes completar el remitente y la actividad o tema de la carta.")
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    rut_raw = (request.POST.get("rut_remitente") or "").strip()
    rut_norm = normalizar_rut(rut_raw) if rut_raw else ""
    telefono = (request.POST.get("telefono") or "").strip()
    vecino_obj = obtener_o_actualizar_vecino(rut_norm, remitente, telefono) if rut_norm else None
    vincular_vecino_a_organizacion(vecino_obj, request.POST.get("junta_vecinos_id"))

    responsable_id = (request.POST.get("responsable_id") or "").strip()
    responsable = (
        User.objects.filter(pk=int(responsable_id), is_active=True).first()
        if responsable_id.isdigit()
        else request.user
    ) or request.user

    estado = (request.POST.get("estado") or "En proceso").strip()
    if estado not in {"En proceso", "Aprobada", "Finalizada", "No aplica"}:
        estado = "En proceso"
    if not usuario_tiene_rol(request.user, "Supervisor") and estado in ("Aprobada", "Finalizada"):
        estado = "En proceso"

    carta = CartaOficinaPartes.objects.create(
        numero_carta=(request.POST.get("numero_carta") or "").strip(),
        delegacion=delegacion,
        trimestre=obtener_trimestre_para_fecha(hoy),
        fecha_ingreso=hoy,
        para=(request.POST.get("para") or "Alcaldesa").strip(),
        vecino=vecino_obj,
        rut_remitente=rut_norm,
        remitente=remitente,
        telefono=telefono or (vecino_obj.telefono if vecino_obj else ""),
        actividad_tema=actividad_tema,
        fecha_actividad=(request.POST.get("fecha_actividad") or "").strip(),
        encargado_area=(request.POST.get("encargado_area") or "").strip(),
        responsable=responsable,
        estado=estado,
        pronuncia=(request.POST.get("pronuncia") or "No aplica").strip(),
        derivada_a=(request.POST.get("derivada_a") or "").strip(),
        observacion=(request.POST.get("observacion") or "").strip(),
        creado_por=request.user,
    )

    messages.success(request, f"Carta {carta.codigo} registrada en el Tubo de Cartas.")
    return redirect(f"{reverse('principal:agenda')}?tab=cartas")


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def editar_carta(request):
    """Edita una carta existente validando delegación, propiedad e inmutabilidad."""
    if request.method != "POST":
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    carta_id = request.POST.get("carta_id")
    carta = get_object_or_404(CartaOficinaPartes, pk=carta_id)

    perfil = getattr(request.user, "perfil", None)
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")
    if perfil and not request.user.is_superuser and carta.delegacion_id != perfil.delegacion_id:
        raise PermissionDenied("No tienes permiso para modificar cartas de otra delegación.")

    es_dueno = carta.responsable_id == request.user.id or carta.creado_por_id == request.user.id
    if not (es_dueno or es_supervisor):
        raise PermissionDenied("Solo puedes modificar tus propias cartas en el Tubo.")

    if carta.esta_bloqueada:
        messages.error(request, f"La carta {carta.codigo} ya está {carta.estado} y no permite modificaciones.")
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    nuevo_estado = (request.POST.get("estado") or carta.estado).strip()
    if nuevo_estado not in {"En proceso", "Aprobada", "Finalizada", "No aplica"}:
        nuevo_estado = carta.estado
    if not es_supervisor and nuevo_estado == "Aprobada":
        messages.error(request, "Solo un Supervisor puede marcar una carta como Aprobada.")
        return redirect(f"{reverse('principal:agenda')}?tab=cartas")

    carta.numero_carta = (request.POST.get("numero_carta") or "").strip()
    carta.para = (request.POST.get("para") or carta.para).strip()
    carta.telefono = (request.POST.get("telefono") or "").strip()
    carta.actividad_tema = (request.POST.get("actividad_tema") or carta.actividad_tema).strip()
    carta.fecha_actividad = (request.POST.get("fecha_actividad") or "").strip()
    carta.encargado_area = (request.POST.get("encargado_area") or "").strip()
    carta.estado = nuevo_estado
    carta.pronuncia = (request.POST.get("pronuncia") or carta.pronuncia).strip()
    carta.derivada_a = (request.POST.get("derivada_a") or "").strip()
    carta.observacion = (request.POST.get("observacion") or "").strip()
    carta.save()

    messages.success(request, f"Carta {carta.codigo} actualizada correctamente.")
    return redirect(f"{reverse('principal:agenda')}?tab=cartas")


@requiere_roles("Funcionario", "Administrador")
@transaction.atomic
def evidencias(request):
    if request.method == "POST" and request.POST.get("accion") == "editar_evidencia":
        evidencia_id = request.POST.get("evidencia_id")
        evidencia = get_object_or_404(Evidencia, pk=evidencia_id)

        if evidencia.funcionario_id != request.user.id:
            raise PermissionDenied("Solo puedes modificar tus propias evidencias.")

        try:
            validar_registro_editable(evidencia.estado, f"La evidencia {evidencia.codigo}")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:evidencias")

        solicitud = (request.POST.get("solicitud") or "").strip()
        accion_txt = (request.POST.get("accion_realizada") or "").strip()
        rut_vecino = (request.POST.get("rut_vecino") or "").strip()
        contacto = (request.POST.get("contacto_nombre") or "").strip()
        telefono = (request.POST.get("contacto_telefono") or "").strip()
        subtipo_id = (request.POST.get("subtipo_atencion_id") or "").strip() or None
        es_delegado = request.POST.get("es_usuario_delegado") == "on"
        nueva_foto = request.FILES.get("fotografia")

        if not (solicitud and accion_txt):
            messages.error(request, "La actividad y la acción realizada son obligatorias.")
            return redirect("principal:evidencias")

        if nueva_foto:
            try:
                _validar_archivo_subido(nueva_foto, {".jpg", ".jpeg", ".png"})
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("principal:evidencias")
            evidencia.fotografia = nueva_foto

        if rut_vecino:
            vecino_obj = obtener_o_actualizar_vecino(rut_vecino, contacto, telefono)
            evidencia.vecino = vecino_obj

        evidencia.solicitud = solicitud
        evidencia.accion = accion_txt
        evidencia.contacto_nombre = contacto or None
        evidencia.contacto_telefono = telefono or None
        evidencia.subtipo_atencion = (
            SubtipoAtencion.objects.filter(pk=subtipo_id, activo=True).first()
            if subtipo_id
            else None
        )
        evidencia.es_usuario_delegado = es_delegado
        evidencia.estado = "Pendiente"
        evidencia.save()

        messages.success(request, f"Evidencia {evidencia.codigo} corregida y reenviada a verificación.")
        return redirect("principal:evidencias")

    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    usuario_objetivo, ctx_buscador = _resolver_usuario_objetivo(request)

    mis_evidencias_qs = (
        Evidencia.objects.filter(
            funcionario=usuario_objetivo,
            fecha_registro__range=(inicio_periodo, fin_periodo),
        )
        .select_related("revisor", "subtipo_atencion__tipo_atencion", "vecino")
        .order_by("-fecha_registro", "-id")
    )

    evidencias_list = []
    for e in mis_evidencias_qs:
        aprobada = es_registro_aprobado(e.estado)
        evidencias_list.append(
            {
                "obj": e,
                "aprobada": aprobada,
                "puede_editar": (not aprobada) and (e.funcionario_id == request.user.id),
                "puntaje": e.puntaje_valido,
                "motivos_sin_puntaje": motivos_sin_puntaje_evidencia(e),
                "observacion_final": e.observacion_revision or e.observacion or "",
            }
        )

    totales = len(evidencias_list)
    aprobadas = sum(1 for item in evidencias_list if item["aprobada"])
    pendientes = totales - aprobadas

    return renderizar(
        request,
        "principal/evidencias.html",
        {
            "pagina": "evidencias",
            "evidencias_reales": evidencias_list,
            "totales": totales,
            "aprobadas": aprobadas,
            "pendientes": pendientes,
            "subtipos_atencion": SubtipoAtencion.objects.filter(activo=True).select_related("tipo_atencion"),
            **ctx_buscador,
        },
    )

@requiere_roles("Supervisor", "Administrador")
def equipo(request):
    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    es_admin = request.user.is_superuser or usuario_tiene_rol(request.user, "Administrador")
    perfil_actual = getattr(request.user, "perfil", None)

    delegacion_obj = None
    filtro_deleg = (request.GET.get("delegacion_id") or "").strip()
    if es_admin:
        if filtro_deleg.isdigit():
            delegacion_obj = Delegacion.objects.filter(pk=int(filtro_deleg), activa=True).first()
    elif perfil_actual and perfil_actual.delegacion:
        delegacion_obj = perfil_actual.delegacion

    funcionarios_qs = (
        User.objects.filter(is_active=True, groups__name="Funcionario")
        .select_related("perfil__cargo", "perfil__delegacion")
        .order_by("first_name", "last_name", "username")
        .distinct()
    )
    if delegacion_obj:
        funcionarios_qs = funcionarios_qs.filter(perfil__delegacion=delegacion_obj)

    resumen = calcular_resumen_equipo(
        funcionarios_qs=funcionarios_qs,
        inicio_periodo=inicio_periodo,
        fin_periodo=fin_periodo,
        delegacion=delegacion_obj,
    )

    trimestre_activo = resolver_trimestre_periodo(inicio_periodo, fin_periodo)
    trimestres_disponibles = Trimestre.objects.all().order_by("-fecha_inicio")

    ajustes_recientes_qs = AjusteDesempeno.objects.select_related(
        "funcionario", "trimestre", "registrado_por"
    ).order_by("-fecha_registro")
    ausencias_recientes_qs = Ausencia.objects.select_related(
        "funcionario", "trimestre", "registrado_por"
    ).order_by("-fecha_inicio")

    if delegacion_obj:
        ajustes_recientes_qs = ajustes_recientes_qs.filter(funcionario__perfil__delegacion=delegacion_obj)
        ausencias_recientes_qs = ausencias_recientes_qs.filter(funcionario__perfil__delegacion=delegacion_obj)

    return renderizar(
        request,
        "principal/equipo.html",
        {
            "pagina": "equipo",
            **resumen,
            "es_admin_equipo": es_admin,
            "delegaciones": Delegacion.objects.filter(activa=True),
            "delegacion_seleccionada": delegacion_obj,
            "filtro_deleg": str(delegacion_obj.id) if delegacion_obj else "",
            "funcionarios_delegacion": funcionarios_qs,
            "trimestre_activo": trimestre_activo,
            "trimestres_disponibles": trimestres_disponibles,
            "ajustes_recientes": ajustes_recientes_qs[:8],
            "ausencias_recientes": ausencias_recientes_qs[:8],
        },
    )


@requiere_roles("Supervisor")
@transaction.atomic
def verificacion(request):
    perfil_sup = getattr(request.user, "perfil", None)
    delegacion_sup_id = perfil_sup.delegacion_id if (perfil_sup and not request.user.is_superuser) else None

    if request.method == "POST":
        tipo_registro = (request.POST.get("tipo_registro") or "evidencia").strip()
        registro_id = (request.POST.get("registro_id") or "").strip()
        codigo_evi = (request.POST.get("codigo") or "").strip()
        nuevo_estado_raw = request.POST.get("nuevo_estado")
        observacion_txt = (request.POST.get("observacion") or "").strip()

        try:
            nuevo_estado = validar_estado_verificacion(nuevo_estado_raw)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:verificacion")

        if nuevo_estado in ("Rechazada", "Solicitud de más antecedentes") and not observacion_txt:
            messages.error(request, "Debes indicar una observación para rechazar o solicitar más antecedentes.")
            return redirect("principal:verificacion")

        if tipo_registro == "social":
            gestion = get_object_or_404(
                GestionSocial.objects.select_related("caso__funcionario__perfil"),
                pk=registro_id,
            )
            try:
                validar_registro_editable(gestion.validacion, f"La gestión social #{gestion.id}")
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("principal:verificacion")

            gestion.validacion = nuevo_estado
            gestion.revisor = request.user
            gestion.fecha_revision = timezone.now()
            gestion.observacion_revision = observacion_txt
            gestion.save(update_fields=["validacion", "revisor", "fecha_revision", "observacion_revision"])
            messages.success(
                request,
                f"Gestión social de {gestion.caso.rut} actualizada a '{nuevo_estado}'.",
            )
            return redirect("principal:verificacion")

        if registro_id.isdigit():
            evidencia = get_object_or_404(Evidencia, pk=int(registro_id))
        else:
            evidencia = get_object_or_404(Evidencia, codigo=codigo_evi)

        try:
            validar_registro_editable(evidencia.estado, f"La evidencia {evidencia.codigo}")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:verificacion")

        evidencia.estado = nuevo_estado
        evidencia.revisor = request.user
        evidencia.fecha_revision = timezone.now()
        evidencia.observacion_revision = observacion_txt
        evidencia.observacion = observacion_txt
        evidencia.save(
            update_fields=["estado", "revisor", "fecha_revision", "observacion_revision", "observacion"]
        )
        messages.success(request, f"Evidencia {evidencia.codigo} dictaminada como '{nuevo_estado}'.")
        return redirect("principal:verificacion")

    evidencias_qs = (
        Evidencia.objects.filter(
            estado__in=["Pendiente", "En revisión", "Solicitud de más antecedentes"]
        )
        .select_related("funcionario__perfil", "subtipo_atencion__tipo_atencion", "vecino")
        .order_by("-fecha_registro", "-id")
    )
    gestiones_qs = (
        GestionSocial.objects.filter(
            validacion__in=["Pendiente", "Solicitud de más antecedentes"]
        )
        .select_related("caso__funcionario__perfil", "subtipo_atencion__tipo_atencion")
        .order_by("-fecha_registro")
    )

    if delegacion_sup_id:
        evidencias_qs = evidencias_qs.filter(funcionario__perfil__delegacion_id=delegacion_sup_id)
        gestiones_qs = gestiones_qs.filter(
            Q(caso__delegacion_id=delegacion_sup_id)
            | Q(caso__funcionario__perfil__delegacion_id=delegacion_sup_id)
        )

    registros = []
    for e in evidencias_qs:
        contacto_nom = e.contacto_nombre or (e.vecino.nombre_completo if e.vecino else "")
        contacto_tel = e.contacto_telefono or (e.vecino.telefono if e.vecino else "")
        registros.append(
            {
                "tipo": "evidencia",
                "tipo_etiqueta": "Actividad",
                "id": e.id,
                "codigo": e.codigo,
                "titulo": e.solicitud,
                "accion": e.accion,
                "fecha": e.fecha_registro,
                "autor": e.funcionario.get_full_name().strip() or e.funcionario.username,
                "estado": e.estado,
                "grupo_tab": "antecedentes" if e.estado == "Solicitud de más antecedentes" else "nuevas",
                "subtipo": str(e.subtipo_atencion) if e.subtipo_atencion else e.item_medir,
                "contacto": f"{contacto_nom or 'Sin nombre'} / {contacto_tel or 'Sin teléfono'}",
                "observacion_previa": e.observacion_revision or e.observacion or "",
                "tiene_archivo": bool(e.fotografia),
                "archivo_url": reverse_lazy("principal:descargar_evidencia", args=[e.id]) if e.fotografia else "",
                "es_imagen": True,
                "motivos_sin_puntaje": motivos_sin_puntaje_evidencia(e),
            }
        )

    for g in gestiones_qs:
        archivo_nombre = g.imagen_verificacion.name.lower() if g.imagen_verificacion else ""
        registros.append(
            {
                "tipo": "social",
                "tipo_etiqueta": "Área Social",
                "id": g.id,
                "codigo": g.evidencia_codigo or f"{g.caso.codigo}-G{g.id}",
                "titulo": f"{g.sub_atencion} — {g.caso.usuario_nombre} ({g.caso.rut})",
                "accion": f"{g.accion_realizada}: {g.detalle_accion}",
                "fecha": g.fecha_ejecucion or g.fecha_registro.date(),
                "autor": g.caso.funcionario.get_full_name().strip() or g.caso.funcionario.username,
                "estado": g.validacion,
                "grupo_tab": "antecedentes" if g.validacion == "Solicitud de más antecedentes" else "nuevas",
                "subtipo": str(g.subtipo_atencion) if g.subtipo_atencion else g.sub_atencion,
                "contacto": f"{g.caso.usuario_nombre or 'Sin nombre'} / {g.caso.telefono or 'Sin teléfono'}",
                "observacion_previa": g.observacion_revision or "",
                "tiene_archivo": bool(g.imagen_verificacion),
                "archivo_url": reverse_lazy("principal:descargar_evidencia_social", args=[g.id])
                if g.imagen_verificacion
                else "",
                "es_imagen": archivo_nombre.endswith((".jpg", ".jpeg", ".png", ".webp")),
                "motivos_sin_puntaje": motivos_sin_puntaje_gestion(g),
            }
        )

    total_nuevas = sum(1 for r in registros if r["grupo_tab"] == "nuevas")
    total_antecedentes = sum(1 for r in registros if r["grupo_tab"] == "antecedentes")

    return renderizar(
        request,
        "principal/verificacion.html",
        {
            "pagina": "verificacion",
            "registros": registros,
            "total_pendientes": len(registros),
            "total_nuevas": total_nuevas,
            "total_antecedentes": total_antecedentes,
        },
    )

@requiere_roles("Administrador")
def administracion(request):
    if request.method == "POST":
        if "crear_meta" in request.POST:
            Meta.objects.create(
                nombre=(request.POST.get("nombre") or "").strip(),
                valor_objetivo=request.POST.get("valor_objetivo"),
                ponderacion=request.POST.get("ponderacion"),
            )
            messages.success(request, "Meta creada correctamente.")
        elif "editar_meta" in request.POST:
            meta = get_object_or_404(Meta, id=request.POST.get("meta_id"))
            meta.nombre = (request.POST.get("nombre") or "").strip()
            meta.valor_objetivo = request.POST.get("valor_objetivo")
            meta.ponderacion = request.POST.get("ponderacion")
            meta.save()
            messages.success(request, "Meta actualizada correctamente.")
        elif "eliminar_meta" in request.POST:
            Meta.objects.filter(id=request.POST.get("meta_id")).delete()
            messages.success(request, "Meta eliminada correctamente.")
        return redirect("principal:administracion")

    tab_activo = request.GET.get("tab", "usuarios")
    if tab_activo not in ("usuarios", "metas", "catalogos", "periodos"):
        tab_activo = "usuarios"

    usuarios = (
        User.objects.select_related("perfil__delegacion", "perfil__cargo")
        .prefetch_related("groups")
        .all()
        .order_by("-is_active", "first_name", "username")
    )
    cargos = Cargo.objects.all().order_by("nombre")
    catalogo_metas = CatalogoMeta.objects.select_related("cargo_sugerido").all().order_by("codigo")
    asignaciones_meta = (
        AsignacionMeta.objects.select_related("funcionario", "trimestre", "catalogo_meta")
        .all()
        .order_by("-trimestre__fecha_inicio", "funcionario__first_name", "catalogo_meta__codigo")
    )
    trimestres = Trimestre.objects.all().order_by("-fecha_inicio")
    metas_reales = Meta.objects.all().order_by("-id")

    tarjetas_catalogos = [
        {"slug": "delegaciones", "nombre": "Delegaciones Municipales", "desc": "Unidades territoriales de la comuna", "total": Delegacion.objects.count()},
        {"slug": "territorios", "nombre": "Territorios / Sectores", "desc": "Sectores asociados a cada delegación", "total": Territorio.objects.count()},
        {"slug": "vecinos", "nombre": "Vecinos", "desc": "Ciudadanos, RUT y datos de contacto", "total": Vecino.objects.count()},
        {"slug": "hitos", "nombre": "Hitos Territoriales", "desc": "Hitos comprometidos y sus responsables", "total": Hito.objects.count()},
        {"slug": "tipos-atencion", "nombre": "Tipos de Atención", "desc": "Categorías principales (Territorial / Social)", "total": TipoAtencion.objects.count()},
        {"slug": "subtipos-atencion", "nombre": "Subtipos de Atención", "desc": "Incluye marca de coordinación sin puntaje", "total": SubtipoAtencion.objects.count()},
        {"slug": "roles", "nombre": "Roles del Sistema", "desc": "Perfiles de autorización y control de acceso", "total": Group.objects.count()},
    ]

    return renderizar(
        request,
        "principal/administracion.html",
        {
            "pagina": "administracion",
            "tab_activo": tab_activo,
            "usuarios": usuarios,
            "cargos": cargos,
            "catalogo_metas": catalogo_metas,
            "asignaciones_meta": asignaciones_meta,
            "trimestres": trimestres,
            "metas_reales": metas_reales,
            "tarjetas_catalogos": tarjetas_catalogos,
            "total_organizaciones": JuntaVecinos.objects.count(),
            "total_tipos_org": TipoOrganizacion.objects.count(),
        },
    )


@requiere_roles("Administrador")
def listar_usuarios(request):
    """Muestra el catálogo de usuarios sin usar Django Admin."""
    usuarios = User.objects.select_related('perfil__delegacion', 'perfil__cargo').prefetch_related('groups').all().order_by('-is_active', 'first_name')
    return renderizar(request, "principal/crud_usuarios_lista.html", {"usuarios": usuarios, "pagina": "administracion"})

@requiere_roles("Administrador")
@transaction.atomic
def crear_usuario(request):
    """Crea un usuario, asigna rol y perfil en una sola transacción atómica."""
    if request.method == "POST":
        form = UsuarioCRUDForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("principal:listar_usuarios")
    else:
        form = UsuarioCRUDForm()
    
    return renderizar(request, "principal/crud_usuarios_form.html", {"form": form, "accion": "Crear", "pagina": "administracion"})

@requiere_roles("Administrador")
@transaction.atomic
def editar_usuario(request, usuario_id):
    """Modifica datos, grupo o delegación de un usuario existente."""
    usuario = User.objects.get(id=usuario_id)
    
    
    datos_iniciales = {}
    if hasattr(usuario, 'perfil'):
        datos_iniciales['delegacion'] = usuario.perfil.delegacion
        datos_iniciales['cargo'] = usuario.perfil.cargo
    if usuario.groups.exists():
        datos_iniciales['grupo'] = usuario.groups.first()

    if request.method == "POST":
        form = UsuarioCRUDForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            return redirect("principal:listar_usuarios")
    else:
        form = UsuarioCRUDForm(instance=usuario, initial=datos_iniciales)

    return renderizar(request, "principal/crud_usuarios_form.html", {"form": form, "accion": "Editar", "pagina": "administracion"})

@requiere_roles("Administrador")
def desactivar_usuario(request, usuario_id):
    """Soft Delete: Desactiva al usuario para no perder registros históricos (HU-26)."""
    usuario = User.objects.get(id=usuario_id)
    
    if usuario != request.user:
        usuario.is_active = False
        usuario.save()
    return redirect("principal:listar_usuarios")



@requiere_roles("Funcionario", "Supervisor", "Administrador")
def panel(request):
    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    usuario_objetivo, ctx_buscador = _resolver_usuario_objetivo(request)
    resumen = calcular_resumen_funcionario(usuario_objetivo, inicio_periodo, fin_periodo)

    return renderizar(
        request,
        "principal/panel.html",
        {
            "pagina": "panel",
            **resumen,
            **ctx_buscador,
        },
    )


def _derivar_caso_a_agenda(request, caso, fecha_prog):
    """Helper interno para derivar una gestión social a la Agenda Colectiva (Tubo)."""
    perfil = getattr(request.user, "perfil", None)
    delegacion = (
        caso.delegacion
        or (perfil.delegacion if perfil and perfil.delegacion else None)
        or Delegacion.objects.first()
    )
    if not delegacion:
        return None

    hoy = timezone.localdate()
    fecha_lim = None
    if fecha_prog:
        try:
            fecha_lim = date.fromisoformat(str(fecha_prog))
        except ValueError:
            fecha_lim = None

    codigo_com = f"COM-SOC-{uuid.uuid4().hex[:4].upper()}"
    return Compromiso.objects.create(
        codigo=codigo_com,
        titulo=f"Derivación Social: {caso.usuario_nombre}",
        territorio=delegacion,
        vecino=caso.vecino,
        responsable=request.user,
        creado_por=request.user,
        trimestre=obtener_trimestre_para_fecha(hoy),
        area="Área Social",
        solicitante=caso.usuario_nombre,
        fecha=hoy,
        plazo="Por definir" if not fecha_prog else str(fecha_prog),
        fecha_limite=fecha_lim,
    )


@requiere_roles("Funcionario", "Supervisor")
def area_social(request):
    """Renderiza la lista de casos sociales con su historial independiente de gestiones."""
    hoy = timezone.localdate()
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")
    casos_qs = CasoSocial.objects.prefetch_related("gestiones__subtipo_atencion").all()

    filtro_fecha = (request.GET.get("filtro_fecha") or "").strip()
    filtro_tipo = (request.GET.get("filtro_tipo") or "").strip()
    busqueda = (request.GET.get("q") or "").strip()

    if filtro_fecha and "-" in filtro_fecha:
        try:
            anio_str, mes_str = filtro_fecha.split("-")
            casos_qs = casos_qs.filter(fecha_ingreso__year=int(anio_str), fecha_ingreso__month=int(mes_str))
        except ValueError:
            pass

    if filtro_tipo:
        casos_qs = casos_qs.filter(gestiones__sub_atencion__icontains=filtro_tipo).distinct()

    if busqueda:
        casos_qs = casos_qs.filter(
            Q(rut__icontains=busqueda) | Q(usuario_nombre__icontains=busqueda) | Q(codigo__icontains=busqueda)
        )

    casos_calculados = []
    for caso in casos_qs:
        gestiones = list(caso.gestiones.all())
        ultima_gestion = gestiones[-1] if gestiones else None
        tipo_atencion = ultima_gestion.sub_atencion if ultima_gestion else "Sin gestión"
        es_dueno = caso.funcionario_id == request.user.id

        gestiones_detalle = []
        for idx, g in enumerate(gestiones, start=1):
            esta_aprobada = es_registro_aprobado(g.validacion)
            gestiones_detalle.append(
                {
                    "numero": idx,
                    "id": g.id,
                    "sub_atencion": g.sub_atencion,
                    "subtipo_atencion_id": g.subtipo_atencion_id,
                    "subtipo_etiqueta": str(g.subtipo_atencion) if g.subtipo_atencion else "",
                    "accion_realizada": g.accion_realizada,
                    "fecha_programada": g.fecha_programada,
                    "fecha_ejecucion": g.fecha_ejecucion,
                    "detalle_accion": g.detalle_accion,
                    "evidencia_codigo": g.evidencia_codigo or "",
                    "tiene_archivo": bool(g.imagen_verificacion),
                    "validacion": g.validacion,
                    "observacion_revision": g.observacion_revision,
                    "requiere_terreno": g.requiere_terreno,
                    "derivar_agenda": g.derivar_agenda,
                    "fecha_registro": g.fecha_registro,
                    "esta_aprobada": esta_aprobada,
                    # Regla estricta: un registro aprobado NO permite modificaciones ni siquiera por Supervisor
                    "puede_editar": (not esta_aprobada) and (es_dueno or es_supervisor),
                    "motivos_sin_puntaje": motivos_sin_puntaje_gestion(g),
                }
            )

        casos_calculados.append(
            {
                "id": caso.id,
                "codigo": caso.codigo or "",
                "rut": caso.rut,
                "usuario_nombre": caso.usuario_nombre,
                "telefono": caso.telefono or "",
                "fecha_ingreso": caso.fecha_ingreso,
                "tipo_atencion": tipo_atencion,
                "gestiones_realizadas": len(gestiones),
                "gestiones_maximas": 3,
                "puede_agregar_gestion": len(gestiones) < 3 and (es_dueno or es_supervisor),
                "siguiente_numero": len(gestiones) + 1,
                "gestiones": gestiones_detalle,
                "es_dueno_o_supervisor": es_dueno or es_supervisor,
            }
        )

    subtipos_sociales = SubtipoAtencion.objects.filter(activo=True).select_related("tipo_atencion")

    return renderizar(
        request,
        "principal/area_social.html",
        {
            "pagina": "area_social",
            "casos": casos_calculados,
            "es_supervisor": es_supervisor,
            "filtro_fecha": filtro_fecha,
            "filtro_tipo": filtro_tipo,
            "busqueda": busqueda,
            "subtipos_sociales": subtipos_sociales,
            "actividades_hoy": contar_actividades_del_dia(request.user, hoy),
            "limite_diario": LIMITE_DIARIO_ACTIVIDADES,
            "fecha_minima_semana": fecha_minima_semana_abierta(hoy),
            "organizaciones_activas": JuntaVecinos.objects.filter(activa=True).select_related("territorio").order_by("nombre"),
        },
    )


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def crear_caso_social(request):
    """Crea un Caso Nuevo y su primera Gestión aplicando las reglas del cliente."""
    if request.method == "POST":
        hoy = timezone.localdate()
        rut_raw = (request.POST.get("rut") or "").strip()
        rut_norm = normalizar_rut(rut_raw)
        nombre = (request.POST.get("usuario_nombre") or "").strip()
        telefono = (request.POST.get("telefono") or "").strip()
        fecha_ejec_str = (request.POST.get("fecha_ejecucion") or "").strip()
        archivo = request.FILES.get("imagen_verificacion")
        es_supervisor = usuario_tiene_rol(request.user, "Supervisor")

        try:
            fecha_ejec = date.fromisoformat(fecha_ejec_str) if fecha_ejec_str else hoy
        except ValueError:
            messages.error(request, "La fecha de ejecución no tiene un formato válido.")
            return redirect("principal:area_social")

        try:
            validar_semana_abierta(fecha_ejec, hoy=hoy)
            validar_limite_diario(request.user, fecha_ejec)
            _validar_archivo_subido(archivo, {".jpg", ".jpeg", ".png", ".pdf"})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:area_social")

        perfil = getattr(request.user, "perfil", None)
        vecino_obj = obtener_o_actualizar_vecino(rut_norm, nombre, telefono)
        vincular_vecino_a_organizacion(vecino_obj, request.POST.get("junta_vecinos_id"))

        caso, creado = CasoSocial.objects.get_or_create(
            rut=rut_norm,
            defaults={
                "vecino": vecino_obj,
                "delegacion": perfil.delegacion if perfil else None,
                "usuario_nombre": nombre or (vecino_obj.nombre_completo if vecino_obj else ""),
                "telefono": telefono or (vecino_obj.telefono if vecino_obj else ""),
                "funcionario": request.user,
            },
        )
        if not creado and vecino_obj and not caso.vecino_id:
            caso.vecino = vecino_obj
            caso.save(update_fields=["vecino"])

        if caso.gestiones.count() >= 3:
            messages.error(request, "Este RUT ya alcanzó el máximo de 3 gestiones sociales.")
            return redirect("principal:area_social")

        subtipo_id = (request.POST.get("subtipo_atencion_id") or "").strip() or None
        subtipo_obj = SubtipoAtencion.objects.filter(pk=subtipo_id, activo=True).first() if subtipo_id else None
        fecha_prog = request.POST.get("fecha_programada") or None
        derivar_agenda = request.POST.get("derivar_agenda") == "True"

        validacion = "Pendiente"
        if es_supervisor and request.POST.get("validacion"):
            try:
                validacion = validar_estado_verificacion(request.POST.get("validacion"))
            except ValidationError:
                validacion = "Pendiente"

        compromiso_obj = _derivar_caso_a_agenda(request, caso, fecha_prog) if derivar_agenda else None

        gestion = GestionSocial.objects.create(
            caso=caso,
            tipo_atencion=subtipo_obj.tipo_atencion if subtipo_obj else None,
            subtipo_atencion=subtipo_obj,
            sub_atencion=request.POST.get("sub_atencion") or "Orientación Social",
            accion_realizada=request.POST.get("accion_realizada") or "Emergencia",
            fecha_programada=fecha_prog,
            fecha_ejecucion=fecha_ejec,
            detalle_accion=(request.POST.get("detalle_accion") or "").strip(),
            evidencia_codigo=(request.POST.get("evidencia") or "").strip() or f"{caso.codigo}-G{caso.gestiones.count() + 1}",
            imagen_verificacion=archivo,
            validacion=validacion,
            requiere_terreno=(request.POST.get("requiere_terreno") == "True"),
            derivar_agenda=derivar_agenda,
            compromiso_derivado=compromiso_obj,
        )

        motivos = motivos_sin_puntaje_gestion(gestion)
        if motivos:
            messages.warning(
                request,
                f"Caso social {caso.codigo} registrado. Nota de puntaje: {' · '.join(motivos)}.",
            )
        else:
            messages.success(request, f"Caso social {caso.codigo} y primera gestión registrados correctamente.")
        return redirect("principal:area_social")

    return redirect("principal:area_social")


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def editar_caso_social(request):
    """
    Maneja 3 operaciones explícitas desde el modal del expediente:
    - actualizar_ciudadano: modifica teléfono del caso.
    - actualizar_gestion: corrige una gestión existente (siempre bloqueada si está Aprobada).
    - agregar_gestion: registra la 2ª o 3ª gestión validando límite diario y semana abierta.
    """
    if request.method != "POST":
        return redirect("principal:area_social")

    hoy = timezone.localdate()
    caso_id = request.POST.get("caso_id")
    modo = request.POST.get("modo", "agregar_gestion")
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")

    caso = CasoSocial.objects.filter(id=caso_id).first()
    if not caso:
        messages.error(request, "El caso especificado no existe.")
        return redirect("principal:area_social")

    if not es_supervisor and caso.funcionario_id != request.user.id:
        messages.error(request, "Solo puedes modificar expedientes creados por ti.")
        return redirect("principal:area_social")

    if modo == "actualizar_ciudadano":
        caso.telefono = (request.POST.get("telefono") or "").strip()
        caso.save(update_fields=["telefono"])
        if caso.vecino:
            caso.vecino.telefono = caso.telefono
            caso.vecino.save(update_fields=["telefono"])
        messages.success(request, f"Teléfono actualizado para {caso.rut}.")
        return redirect("principal:area_social")

    if modo == "actualizar_gestion":
        gestion_id = request.POST.get("gestion_id")
        gestion = GestionSocial.objects.filter(id=gestion_id, caso=caso).first()
        if not gestion:
            messages.error(request, "La gestión indicada no existe.")
            return redirect("principal:area_social")

        try:
            validar_registro_editable(gestion.validacion, "La gestión social")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:area_social")

        archivo = request.FILES.get("imagen_verificacion")
        if archivo:
            try:
                _validar_archivo_subido(archivo, {".jpg", ".jpeg", ".png", ".pdf"})
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("principal:area_social")
            gestion.imagen_verificacion = archivo

        subtipo_id = (request.POST.get("subtipo_atencion_id") or "").strip() or None
        subtipo_obj = SubtipoAtencion.objects.filter(pk=subtipo_id, activo=True).first() if subtipo_id else None
        fecha_prog = request.POST.get("fecha_programada") or None
        estaba_derivada = gestion.derivar_agenda
        derivar_ahora = request.POST.get("derivar_agenda") == "True"

        gestion.subtipo_atencion = subtipo_obj
        gestion.tipo_atencion = subtipo_obj.tipo_atencion if subtipo_obj else None
        gestion.sub_atencion = request.POST.get("sub_atencion") or gestion.sub_atencion
        gestion.accion_realizada = request.POST.get("accion_realizada") or gestion.accion_realizada
        gestion.fecha_programada = fecha_prog
        gestion.detalle_accion = (request.POST.get("detalle_accion") or "").strip()
        gestion.evidencia_codigo = (request.POST.get("evidencia") or "").strip()
        gestion.requiere_terreno = request.POST.get("requiere_terreno") == "True"
        gestion.derivar_agenda = derivar_ahora

        if es_supervisor and request.POST.get("validacion"):
            try:
                gestion.validacion = validar_estado_verificacion(request.POST.get("validacion"))
                gestion.revisor = request.user
                gestion.fecha_revision = timezone.now()
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("principal:area_social")
        elif not es_supervisor:
            gestion.validacion = "Pendiente"

        if derivar_ahora and not estaba_derivada and not gestion.compromiso_derivado_id:
            gestion.compromiso_derivado = _derivar_caso_a_agenda(request, caso, fecha_prog)

        gestion.save()
        messages.success(request, "Gestión actualizada correctamente.")
        return redirect("principal:area_social")


    if caso.gestiones.count() >= 3:
        messages.error(request, "Límite máximo alcanzado (3 de 3). No se pueden agregar más gestiones.")
        return redirect("principal:area_social")

    fecha_ejec_str = (request.POST.get("fecha_ejecucion") or "").strip()
    archivo = request.FILES.get("imagen_verificacion")
    try:
        fecha_ejec = date.fromisoformat(fecha_ejec_str) if fecha_ejec_str else hoy
    except ValueError:
        messages.error(request, "La fecha de ejecución no tiene un formato válido.")
        return redirect("principal:area_social")

    try:
        validar_semana_abierta(fecha_ejec, hoy=hoy)
        validar_limite_diario(request.user, fecha_ejec)
        _validar_archivo_subido(archivo, {".jpg", ".jpeg", ".png", ".pdf"})
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("principal:area_social")

    subtipo_id = (request.POST.get("subtipo_atencion_id") or "").strip() or None
    subtipo_obj = SubtipoAtencion.objects.filter(pk=subtipo_id, activo=True).first() if subtipo_id else None
    fecha_prog = request.POST.get("fecha_programada") or None
    derivar_agenda = request.POST.get("derivar_agenda") == "True"
    compromiso_obj = _derivar_caso_a_agenda(request, caso, fecha_prog) if derivar_agenda else None

    GestionSocial.objects.create(
        caso=caso,
        tipo_atencion=subtipo_obj.tipo_atencion if subtipo_obj else None,
        subtipo_atencion=subtipo_obj,
        sub_atencion=request.POST.get("sub_atencion") or "Orientación Social",
        accion_realizada=request.POST.get("accion_realizada") or "Emergencia",
        fecha_programada=fecha_prog,
        fecha_ejecucion=fecha_ejec,
        detalle_accion=(request.POST.get("detalle_accion") or "").strip(),
        evidencia_codigo=(request.POST.get("evidencia") or "").strip()
        or f"{caso.codigo}-G{caso.gestiones.count() + 1}",
        imagen_verificacion=archivo,
        validacion="Pendiente",
        requiere_terreno=(request.POST.get("requiere_terreno") == "True"),
        derivar_agenda=derivar_agenda,
        compromiso_derivado=compromiso_obj,
    )

    messages.success(request, f"Gestión {caso.gestiones.count()} de 3 registrada para {caso.rut}.")
    return redirect("principal:area_social")

@login_required
def cambiar_password_inicial(request):
    """Obliga a reemplazar la contraseña temporal antes de operar en el sistema."""
    perfil = getattr(request.user, "perfil", None)
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            usuario = form.save()
            update_session_auth_hash(request, usuario)
            if perfil:
                perfil.debe_cambiar_clave = False
                perfil.save(update_fields=["debe_cambiar_clave"])
            messages.success(request, "Contraseña actualizada correctamente.")
            return redirect(destino_por_rol(usuario))
    else:
        form = PasswordChangeForm(request.user)

    return renderizar(
        request,
        "principal/cambiar_password_inicial.html",
        {"pagina": "cambiar_password", "form": form},
    )


def _puede_ver_archivo_usuario(solicitante, dueno_usuario):
    """Solo el propio funcionario, un Administrador o un Supervisor de su misma delegación."""
    if solicitante.id == dueno_usuario.id:
        return True
    if usuario_tiene_rol(solicitante, "Administrador"):
        return True
    if usuario_tiene_rol(solicitante, "Supervisor"):
        p_sol = getattr(solicitante, "perfil", None)
        p_due = getattr(dueno_usuario, "perfil", None)
        if p_sol and p_due and p_sol.delegacion_id == p_due.delegacion_id:
            return True
    return False


@login_required
def descargar_evidencia(request, evidencia_id):
    evidencia = get_object_or_404(Evidencia, id=evidencia_id)
    if not _puede_ver_archivo_usuario(request.user, evidencia.funcionario):
        raise PermissionDenied("No tienes permiso para acceder a esta evidencia.")
    if not evidencia.fotografia:
        raise Http404("Archivo no disponible.")
    return FileResponse(evidencia.fotografia.open("rb"))


@login_required
def descargar_evidencia_social(request, gestion_id):
    gestion = get_object_or_404(GestionSocial.objects.select_related("caso"), id=gestion_id)
    if not _puede_ver_archivo_usuario(request.user, gestion.caso.funcionario):
        raise PermissionDenied("No tienes permiso para acceder a este documento social.")
    if not gestion.imagen_verificacion:
        raise Http404("Archivo no disponible.")
    return FileResponse(gestion.imagen_verificacion.open("rb"))


@login_required
def descargar_respaldo_ajuste(request, ajuste_id):
    ajuste = get_object_or_404(AjusteDesempeno, id=ajuste_id)
    if not _puede_ver_archivo_usuario(request.user, ajuste.funcionario):
        raise PermissionDenied("No tienes permiso para acceder a este respaldo.")
    if not ajuste.archivo_respaldo:
        raise Http404("Respaldo no disponible.")
    return FileResponse(ajuste.archivo_respaldo.open("rb"))


@login_required
def api_buscar_vecino(request):
    """Autocompleta nombre, teléfono y organización vigente cuando el RUT ya existe en BD."""
    rut = (request.GET.get("rut") or "").strip()
    if not rut:
        return JsonResponse({"encontrado": False})

    rut_norm = normalizar_rut(rut)
    rut_limpio = rut_norm.replace(".", "").upper()
    vecino = Vecino.objects.filter(
        Q(rut__iexact=rut) | Q(rut__iexact=rut_norm) | Q(rut__iexact=rut_limpio)
    ).first()
    if vecino:
        dir_vigente = (
            Dirigencia.objects.filter(vecino=vecino, vigente=True, junta_vecinos__activa=True)
            .select_related("junta_vecinos")
            .order_by("-fecha_inicio")
            .first()
        )
        return JsonResponse({
            "encontrado": True,
            "rut": vecino.rut,
            "nombre": vecino.nombre_completo,
            "telefono": vecino.telefono,
            "direccion": vecino.direccion,
            "junta_vecinos_id": dir_vigente.junta_vecinos_id if dir_vigente else "",
            "junta_vecinos_nombre": dir_vigente.junta_vecinos.nombre if dir_vigente else "",
        })

    caso = CasoSocial.objects.filter(
        Q(rut__iexact=rut) | Q(rut__iexact=rut_norm) | Q(rut__iexact=rut_limpio)
    ).first()
    if caso:
        return JsonResponse({
            "encontrado": True,
            "rut": caso.rut,
            "nombre": caso.usuario_nombre,
            "telefono": caso.telefono or "",
            "direccion": "",
            "junta_vecinos_id": "",
            "junta_vecinos_nombre": "",
        })

    return JsonResponse({"encontrado": False})

@requiere_roles("Supervisor", "Administrador")
def asignar_tareas(request):
    hoy = timezone.localdate()


    if request.method == "POST":
        accion = request.POST.get("accion", "crear")
        funcionario_id = request.POST.get("funcionario_id")
        territorio_id = request.POST.get("territorio_id") or None
        titulo = request.POST.get("titulo", "").strip()
        descripcion = request.POST.get("descripcion", "").strip()
        prioridad = request.POST.get("prioridad", "Media")
        fecha_limite_str = request.POST.get("fecha_limite", "").strip()
        ingresa_al_tubo = request.POST.get("ingresa_al_tubo") == "1"

        if prioridad not in {"Baja", "Media", "Alta", "Urgente"}:
            prioridad = "Media"

        if not (funcionario_id and titulo and fecha_limite_str):
            messages.error(request, "Completa el funcionario, el título y la fecha límite.")
            return redirect("principal:asignar_tareas")

        try:
            fecha_limite = date.fromisoformat(fecha_limite_str)
        except ValueError:
            messages.error(request, "La fecha límite no tiene un formato válido.")
            return redirect("principal:asignar_tareas")

        responsable = get_object_or_404(User, pk=funcionario_id, is_active=True)
        sector = Territorio.objects.filter(pk=territorio_id).first() if territorio_id else None

        perfil_resp = getattr(responsable, "perfil", None)
        perfil_actual = getattr(request.user, "perfil", None)
        delegacion = (
            (perfil_resp.delegacion if perfil_resp and perfil_resp.delegacion else None)
            or (perfil_actual.delegacion if perfil_actual and perfil_actual.delegacion else None)
            or Delegacion.objects.first()
        )
        if delegacion is None:
            delegacion = Delegacion.objects.create(nombre="Casa Central")

        dias = (fecha_limite - hoy).days
        if dias > 0:
            plazo_txt = f"{dias} días"
        elif dias == 0:
            plazo_txt = "Hoy"
        else:
            plazo_txt = f"Vencido ({abs(dias)} días)"

        if accion == "editar":
            tarea_id = request.POST.get("tarea_id")
            compromiso = get_object_or_404(Compromiso, pk=tarea_id)
            compromiso.responsable = responsable
            compromiso.territorio = delegacion
            compromiso.sector = sector
            compromiso.titulo = titulo[:255]
            compromiso.descripcion = descripcion
            compromiso.prioridad = prioridad
            compromiso.fecha_limite = fecha_limite
            compromiso.plazo = plazo_txt
            compromiso.save()
            messages.success(request, f"Tarea {compromiso.codigo} actualizada correctamente.")
        else:
            codigo = f"TAR-{hoy.strftime('%Y%m')}-{uuid.uuid4().hex[:5].upper()}"
            solicitante = (request.user.get_full_name().strip() or request.user.get_username())[:150]
            Compromiso.objects.create(
                codigo=codigo,
                titulo=titulo[:255],
                descripcion=descripcion,
                territorio=delegacion,
                sector=sector,
                responsable=responsable,
                creado_por=request.user,
                estado="Pendiente",
                prioridad=prioridad,
                area="Tubo de trabajo" if ingresa_al_tubo else "Asignación directa",
                solicitante=solicitante,
                fecha=hoy,
                plazo=plazo_txt,
                fecha_limite=fecha_limite,
            )
            messages.success(request, f"Tarea {codigo} asignada a {responsable.get_full_name() or responsable.username}.")

        return redirect("principal:asignar_tareas")


    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    base_qs = (
        Compromiso.objects.filter(fecha__range=(inicio_periodo, fin_periodo))
        .select_related("responsable", "sector", "territorio")
        .order_by("-fecha", "-id")
    )

    resumen = {"pendientes": 0, "en_proceso": 0, "completadas": 0, "vencidas": 0}
    for c in base_qs:
        esta_vencida = bool(c.fecha_limite and c.fecha_limite < hoy and c.estado not in ("Completado", "Rechazado"))
        if c.estado == "Completado":
            resumen["completadas"] += 1
        elif c.estado == "Vencido" or esta_vencida:
            resumen["vencidas"] += 1
        elif c.estado == "En proceso":
            resumen["en_proceso"] += 1
        else:
            resumen["pendientes"] += 1

    qs = base_qs
    filtro_func = request.GET.get("funcionario_id", "").strip()
    filtro_estado = request.GET.get("estado", "").strip()
    filtro_prioridad = request.GET.get("prioridad", "").strip()

    if filtro_func.isdigit():
        qs = qs.filter(responsable_id=int(filtro_func))
    if filtro_prioridad:
        qs = qs.filter(prioridad=filtro_prioridad)
    if filtro_estado == "Completada":
        qs = qs.filter(estado="Completado")
    elif filtro_estado == "Vencida":
        qs = qs.filter(
            Q(estado="Vencido") | (Q(fecha_limite__lt=hoy) & ~Q(estado__in=["Completado", "Rechazado"]))
        )
    elif filtro_estado in ("Pendiente", "En proceso"):
        qs = qs.filter(estado=filtro_estado)

    tareas = []
    for c in qs:
        esta_vencida = bool(c.fecha_limite and c.fecha_limite < hoy and c.estado not in ("Completado", "Rechazado"))
        if c.estado == "Completado":
            estado_ui = "Completada"
        elif c.estado == "Vencido" or esta_vencida:
            estado_ui = "Vencida"
        else:
            estado_ui = c.estado

        tareas.append(
            {
                "id": c.id,
                "codigo": c.codigo,
                "titulo": c.titulo,
                "descripcion": c.descripcion,
                "funcionario": c.responsable.get_full_name().strip() or c.responsable.get_username(),
                "funcionario_id": c.responsable_id,
                "territorio": c.sector.nombre if c.sector else None,
                "territorio_id": c.sector_id,
                "prioridad": c.prioridad,
                "fecha_limite": c.fecha_limite or c.fecha,
                "esta_vencida": esta_vencida,
                "estado": estado_ui,
            }
        )

    usuarios_qs = User.objects.filter(is_active=True, groups__name="Funcionario").select_related("perfil__cargo").distinct()
    if not usuarios_qs.exists():
        usuarios_qs = User.objects.filter(is_active=True).select_related("perfil__cargo")

    funcionarios = [
        {
            "id": u.id,
            "nombre": u.get_full_name().strip() or u.get_username(),
            "cargo": u.perfil.cargo.nombre if hasattr(u, "perfil") and u.perfil.cargo else "Sin cargo",
        }
        for u in usuarios_qs.order_by("first_name", "username")
    ]

    return renderizar(
        request,
        "principal/asignar_tareas.html",
        {
            "pagina": "asignar_tareas",
            "resumen": resumen,
            "tareas": tareas,
            "funcionarios": funcionarios,
            "territorios": Territorio.objects.all().order_by("nombre"),
        },
    )

@requiere_roles("Supervisor", "Administrador")
@transaction.atomic
def registrar_ajuste_desempeno(request):
    """Registra una Felicitación (con respaldo obligatorio) o Reclamo y notifica por correo al funcionario."""
    if request.method != "POST":
        return redirect("principal:equipo")

    funcionario_id = (request.POST.get("funcionario_id") or "").strip()
    trimestre_id = (request.POST.get("trimestre_id") or "").strip()
    tipo = (request.POST.get("tipo") or "").strip()
    porcentaje_str = (request.POST.get("porcentaje_ajuste") or "").strip().replace(",", ".")
    motivo = (request.POST.get("motivo") or "").strip()
    archivo = request.FILES.get("archivo_respaldo")

    if tipo not in ("Felicitación", "Penalización"):
        messages.error(request, "Tipo de ajuste inválido.")
        return redirect("principal:equipo")

    if not (funcionario_id.isdigit() and motivo and porcentaje_str):
        messages.error(request, "Completa funcionario, porcentaje y motivo.")
        return redirect("principal:equipo")

    funcionario = get_object_or_404(User, pk=int(funcionario_id), is_active=True)


    es_admin = request.user.is_superuser or usuario_tiene_rol(request.user, "Administrador")
    if not es_admin:
        p_sup = getattr(request.user, "perfil", None)
        p_fun = getattr(funcionario, "perfil", None)
        if p_sup and p_fun and p_sup.delegacion_id != p_fun.delegacion_id:
            raise PermissionDenied("Solo puedes registrar ajustes a funcionarios de tu delegación.")


    if tipo == "Felicitación" and not archivo:
        messages.error(
            request,
            "Las felicitaciones requieren adjuntar el respaldo formal (correo/oficio del Delegado) para ser válidas.",
        )
        return redirect("principal:equipo")

    if archivo:
        try:
            _validar_archivo_subido(archivo, {".jpg", ".jpeg", ".png", ".pdf"})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("principal:equipo")

    try:
        valor = abs(Decimal(porcentaje_str))
    except InvalidOperation:
        messages.error(request, "El porcentaje de ajuste debe ser un número válido.")
        return redirect("principal:equipo")

    if valor <= 0 or valor > Decimal("50"):
        messages.error(request, "El porcentaje debe estar entre 0.5% y 50%.")
        return redirect("principal:equipo")

    porcentaje_final = valor if tipo == "Felicitación" else -valor

    trimestre = Trimestre.objects.filter(pk=trimestre_id).first() if trimestre_id.isdigit() else None
    if not trimestre:
        inicio_p, fin_p = _rango_periodo_activo(request)
        trimestre = resolver_trimestre_periodo(inicio_p, fin_p) or Trimestre.objects.order_by("-fecha_inicio").first()
    if not trimestre:
        messages.error(request, "No existe un trimestre configurado en el sistema.")
        return redirect("principal:equipo")

    ajuste = AjusteDesempeno.objects.create(
        funcionario=funcionario,
        trimestre=trimestre,
        tipo=tipo,
        porcentaje_ajuste=porcentaje_final,
        motivo=motivo,
        archivo_respaldo=archivo,
        registrado_por=request.user,
    )

    _, msg_correo = enviar_notificacion_ajuste(ajuste)
    messages.success(
        request,
        f"{tipo} ({porcentaje_final:+}%) registrada para {funcionario.get_full_name() or funcionario.username}. {msg_correo}",
    )
    return redirect("principal:equipo")


@requiere_roles("Supervisor", "Administrador")
@transaction.atomic
def registrar_ausencia(request):
    """Registra una ausencia informada por el Delegado/Supervisor para ajustar las metas del semáforo."""
    if request.method != "POST":
        return redirect("principal:equipo")

    funcionario_id = (request.POST.get("funcionario_id") or "").strip()
    trimestre_id = (request.POST.get("trimestre_id") or "").strip()
    tipo_ausencia = (request.POST.get("tipo_ausencia") or "").strip()
    f_ini_str = (request.POST.get("fecha_inicio") or "").strip()
    f_fin_str = (request.POST.get("fecha_termino") or "").strip()
    dias_str = (request.POST.get("dias_descontados") or "").strip()
    observacion = (request.POST.get("observacion") or "").strip()

    if not (funcionario_id.isdigit() and tipo_ausencia and f_ini_str and f_fin_str):
        messages.error(request, "Completa todos los campos obligatorios de la ausencia.")
        return redirect("principal:equipo")

    try:
        f_ini = date.fromisoformat(f_ini_str)
        f_fin = date.fromisoformat(f_fin_str)
    except ValueError:
        messages.error(request, "Las fechas de la ausencia no tienen un formato válido.")
        return redirect("principal:equipo")

    if f_fin < f_ini:
        messages.error(request, "La fecha de término no puede ser anterior a la fecha de inicio.")
        return redirect("principal:equipo")

    dias = int(dias_str) if dias_str.isdigit() and int(dias_str) > 0 else ((f_fin - f_ini).days + 1)

    funcionario = get_object_or_404(User, pk=int(funcionario_id), is_active=True)
    es_admin = request.user.is_superuser or usuario_tiene_rol(request.user, "Administrador")
    if not es_admin:
        p_sup = getattr(request.user, "perfil", None)
        p_fun = getattr(funcionario, "perfil", None)
        if p_sup and p_fun and p_sup.delegacion_id != p_fun.delegacion_id:
            raise PermissionDenied("Solo puedes registrar ausencias a funcionarios de tu delegación.")

    trimestre = Trimestre.objects.filter(pk=trimestre_id).first() if trimestre_id.isdigit() else None
    if not trimestre:
        trimestre = resolver_trimestre_periodo(f_ini, f_fin) or Trimestre.objects.order_by("-fecha_inicio").first()
    if not trimestre:
        messages.error(request, "No existe un trimestre configurado en el sistema.")
        return redirect("principal:equipo")

    Ausencia.objects.create(
        funcionario=funcionario,
        trimestre=trimestre,
        tipo_ausencia=tipo_ausencia,
        fecha_inicio=f_ini,
        fecha_termino=f_fin,
        dias_descontados=dias,
        observacion=observacion,
        registrado_por=request.user,
    )
    messages.success(
        request,
        f"Ausencia ({dias} día/s) registrada para {funcionario.get_full_name() or funcionario.username}. Metas del semáforo ajustadas.",
    )
    return redirect("principal:equipo")