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
)

from .periodos import contexto_periodo_actual

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from .models import AjusteDesempeno, Territorio, Vecino

from datetime import date

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

def renderizar(request, plantilla, contexto=None):
    """Renderiza una plantilla incluyendo el contexto del usuario conectado."""
    return render(
        request,
        plantilla,
        contexto_usuario(request, **(contexto or {})),
    )

def destino_por_rol(usuario):
    """Devuelve la ruta de la página principal según el rol del usuario."""
    if usuario_tiene_rol(usuario, "Administrador"):
        return "principal:administracion"
    if usuario_tiene_rol(usuario, "Supervisor"):
        return "principal:equipo"
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
            
            if usuario_tiene_rol(usuario, "Administrador"):
                return redirect("principal:administracion")
            elif usuario_tiene_rol(usuario, "Supervisor"):
                return redirect("principal:equipo")
            else:
                
                if hasattr(usuario, 'perfil') and usuario.perfil.cargo and 'social' in usuario.perfil.cargo.nombre.lower():
                    return redirect("principal:area_social")
                
                
                return redirect("principal:panel")

        return render(
            request,
            "principal/inicio.html",
            {"error_inicio": "Usuario o contraseña incorrectos."},
        )

    return render(request, "principal/inicio.html")


@requiere_roles("Funcionario")
def actividades(request):
    if request.method == "POST":
        fecha = request.POST.get("fecha")
        actividad = request.POST.get("actividad")
        accion = request.POST.get("accion")
        contacto = request.POST.get("contacto")
        telefono = request.POST.get("telefono")
        fotografia = request.FILES.get("fotografia")
        
        meta_id = request.POST.get("meta_id") 

        codigo_evi = f"EVI-{uuid.uuid4().hex[:5].upper()}"

        nueva_evidencia = Evidencia(
            codigo=codigo_evi,
            funcionario=request.user,
            fecha_registro=fecha,
            solicitud=actividad,
            accion=accion,
            contacto_nombre=contacto,
            contacto_telefono=telefono,
            fotografia=fotografia,
            meta_relacionada_id=meta_id 
        )

        if request.POST.get("crear_compromiso") == "on":
            id_territorio = request.POST.get("territorio")
            delegacion = Delegacion.objects.get(id=id_territorio)
            codigo_com = f"COM-{uuid.uuid4().hex[:5].upper()}"

            nuevo_compromiso = Compromiso.objects.create(
                codigo=codigo_com,
                titulo=actividad[:250],
                territorio=delegacion,
                responsable=request.user,
                area=request.POST.get("area"),
                solicitante=contacto or "Sin especificar",
                fecha=fecha,
                plazo=request.POST.get("fecha_comprometida")
            )
            nueva_evidencia.compromiso_vinculado = nuevo_compromiso

        nueva_evidencia.save()
        return redirect("principal:evidencias")

    return renderizar(
        request,
        "principal/actividades.html",
        {
            "pagina": "actividades",
            "delegaciones": Delegacion.objects.all(),
            
            "metas_reales": Meta.objects.filter(vigente=True), 
        },
    )


@requiere_roles("Funcionario", "Supervisor")
def agenda(request):
    if request.method == "POST":
        codigo_recibido = request.POST.get("codigo")
        nuevo_estado = request.POST.get("nuevo_estado")
        nuevo_texto = request.POST.get("observacion")

        if codigo_recibido and nuevo_estado:
            compromiso = get_object_or_404(Compromiso, codigo=codigo_recibido)
            compromiso.estado = nuevo_estado
            compromiso.save()

            if nuevo_texto:
                Observacion.objects.create(
                    compromiso=compromiso,
                    autor=request.user,
                    texto=nuevo_texto,
                )

        return redirect("principal:agenda")

    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    compromisos_reales = Compromiso.objects.filter(
        fecha__range=(inicio_periodo, fin_periodo)
    )

    return renderizar(
        request,
        "principal/agenda.html",
        {
            "pagina": "agenda",
            "compromisos_reales": compromisos_reales,
        },
    )


@requiere_roles("Funcionario")
def evidencias(request):
    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    mis_evidencias = Evidencia.objects.filter(
        funcionario=request.user,
        fecha_registro__range=(inicio_periodo, fin_periodo),
    )

    totales = mis_evidencias.count()
    aprobadas = mis_evidencias.filter(estado="Aprobada").count()
    pendientes = totales - aprobadas

    return renderizar(
        request,
        "principal/evidencias.html",
        {
            "pagina": "evidencias",
            "evidencias_reales": mis_evidencias,
            "totales": totales,
            "aprobadas": aprobadas,
            "pendientes": pendientes,
        },
    )



@requiere_roles("Supervisor", "Administrador")
def equipo(request):
    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    todas_evidencias = Evidencia.objects.filter(
        fecha_registro__range=(inicio_periodo, fin_periodo)
    )
    total_aprobadas = todas_evidencias.filter(estado="Aprobada").count()
    total_revision = todas_evidencias.filter(estado="En revisión").count()
    total_general = todas_evidencias.count()

    avance_global = int((total_aprobadas / total_general * 100)) if total_general > 0 else 0

    funcionarios_db = User.objects.filter(groups__name="Funcionario").select_related("perfil__cargo")
    equipo_calculado = []

    for f in funcionarios_db:
        evs = todas_evidencias.filter(funcionario=f)
        aprob = evs.filter(estado="Aprobada").count()
        tot = evs.count()
        porcentaje = int((aprob / tot * 100)) if tot > 0 else 0

        clase = "aprobada" if porcentaje >= 60 else ("corregir" if porcentaje >= 40 else "rechazada")
        estado = "Óptimo" if porcentaje >= 60 else ("En riesgo" if porcentaje >= 40 else "Crítico")

        iniciales = f"{f.first_name[:1]}{f.last_name[:1]}" if f.first_name else (f.username[:2] or "F")
        cargo_real = (
            f.perfil.cargo.nombre
            if hasattr(f, "perfil") and f.perfil.cargo
            else "Sin cargo"
        )

        equipo_calculado.append({
            "nombre": f.get_full_name() or f.username,
            "iniciales": iniciales.upper(),
            "cargo": cargo_real,
            "porcentaje": porcentaje,
            "barra": porcentaje,
            "clase": clase,
            "estado": estado,
        })

    return renderizar(
        request,
        "principal/equipo.html",
        {
            "pagina": "equipo",
            "avance_global": avance_global,
            "total_aprobadas": total_aprobadas,
            "total_revision": total_revision,
            "total_general": total_general,
            "equipo": equipo_calculado,
        },
    )


@requiere_roles("Supervisor")
def verificacion(request):
    if request.method == "POST":
        codigo_evi = request.POST.get("codigo") 
        nuevo_estado = request.POST.get("nuevo_estado")
        
        evidencia = Evidencia.objects.get(codigo=codigo_evi)
        
        evidencia.estado = nuevo_estado
        evidencia.save()
        
        return redirect("principal:verificacion")
        
    pendientes = Evidencia.objects.filter(estado="En revisión")
    
    return renderizar(
        request, 
        "principal/verificacion.html", 
        {
            "pagina": "verificacion",
            "evidencias": pendientes,
            "total_pendientes": pendientes.count()
        }
    )

from .models import Meta 

@requiere_roles("Administrador")
def administracion(request):
    if request.method == "POST":
        
        if "crear_meta" in request.POST:
            Meta.objects.create(
                nombre=request.POST.get("nombre"),
                valor_objetivo=request.POST.get("valor_objetivo"),
                ponderacion=request.POST.get("ponderacion")
            )
        

        elif "editar_meta" in request.POST:
            meta_id = request.POST.get("meta_id")
            meta = Meta.objects.get(id=meta_id)
            meta.nombre = request.POST.get("nombre")
            meta.valor_objetivo = request.POST.get("valor_objetivo")
            meta.ponderacion = request.POST.get("ponderacion")
            meta.save()
            
        
        elif "eliminar_meta" in request.POST:
            meta_id = request.POST.get("meta_id")
            Meta.objects.filter(id=meta_id).delete()

        return redirect("principal:administracion")
            
    
    metas_reales = Meta.objects.all().order_by('-id')
    
    
    usuarios = User.objects.all().select_related('perfil')
    
    return renderizar(
        request,
        "principal/administracion.html",
        {
            "pagina": "administracion",
            "metas_reales": metas_reales,
            "usuarios": usuarios,
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



@requiere_roles("Funcionario", "Supervisor")
def panel(request):
    inicio_periodo, fin_periodo = _rango_periodo_activo(request)
    mis_evidencias = Evidencia.objects.filter(
        funcionario=request.user,
        fecha_registro__range=(inicio_periodo, fin_periodo),
    )
    ev_aprobadas = mis_evidencias.filter(estado="Aprobada").count()
    ev_revision = mis_evidencias.filter(estado="En revisión").count()
    ev_rechazadas = mis_evidencias.filter(estado="Rechazada").count()

    total_ev = mis_evidencias.count()
    porcentaje_avance = int((ev_aprobadas / total_ev * 100)) if total_ev > 0 else 0
    compromisos_vencer = Compromiso.objects.filter(
        responsable=request.user,
        fecha__range=(inicio_periodo, fin_periodo),
    ).order_by("fecha_limite", "plazo")[:4]

    # --- FILTRO ESTRICTO POR CARGO DEL USUARIO ---
    perfil = getattr(request.user, "perfil", None)
    if perfil and perfil.cargo:
        metas_db = Meta.objects.filter(vigente=True, cargo=perfil.cargo)
    else:
        metas_db = Meta.objects.none()

    metas_calculadas = []
    for m in metas_db:
        avance_real = mis_evidencias.filter(meta_relacionada=m, estado="Aprobada").count()

        cumplimiento = (avance_real / m.valor_objetivo * 100) if m.valor_objetivo > 0 else 0
        if cumplimiento > 120:
            cumplimiento = 120  # Tope máximo de cumplimiento exigido por rúbrica

        resultado = (m.ponderacion * cumplimiento) / 100

        metas_calculadas.append({
            "id": m.id,
            "nombre": m.nombre,
            "ponderacion": m.ponderacion,
            "avance": avance_real,
            "meta": m.valor_objetivo,
            "barra": min(int(cumplimiento), 100),
            "resultado": round(resultado, 1),
        })

    return renderizar(
        request,
        "principal/panel.html",
        {
            "pagina": "panel",
            "ev_aprobadas": ev_aprobadas,
            "ev_revision": ev_revision,
            "ev_rechazadas": ev_rechazadas,
            "porcentaje_avance": porcentaje_avance,
            "compromisos_vencer": compromisos_vencer,
            "metas": metas_calculadas,
        },
    )


def _derivar_caso_a_agenda(request, caso, fecha_prog):
    """Helper interno para derivar una gestión social a la Agenda Colectiva (Tubo)."""
    perfil = getattr(request.user, "perfil", None)
    if not perfil or not perfil.delegacion:
        return
    codigo_com = f"COM-SOC-{uuid.uuid4().hex[:4].upper()}"
    Compromiso.objects.create(
        codigo=codigo_com,
        titulo=f"Derivación Social: {caso.usuario_nombre}",
        territorio=perfil.delegacion,
        responsable=request.user,
        area="Área Social",
        solicitante=caso.usuario_nombre,
        fecha=timezone.now().date(),
        plazo="Por definir" if not fecha_prog else str(fecha_prog),
    )


@requiere_roles("Funcionario", "Supervisor")
def area_social(request):
    """Renderiza la lista de casos sociales con su historial independiente de gestiones."""
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")
    casos_qs = CasoSocial.objects.prefetch_related("gestiones").all()

    # Filtros reales (mes/año, tipo de atención y búsqueda por RUT o nombre)
    filtro_fecha = (request.GET.get("filtro_fecha") or "").strip()  # formato YYYY-MM
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
        casos_qs = casos_qs.filter(Q(rut__icontains=busqueda) | Q(usuario_nombre__icontains=busqueda))

    casos_calculados = []
    for caso in casos_qs:
        gestiones = list(caso.gestiones.all())
        ultima_gestion = gestiones[-1] if gestiones else None
        tipo_atencion = ultima_gestion.sub_atencion if ultima_gestion else "Sin gestión"
        es_dueno = (caso.funcionario_id == request.user.id)

        gestiones_detalle = []
        for idx, g in enumerate(gestiones, start=1):
            esta_aprobada = g.validacion in ("Aprobado", "Aprobada")
            gestiones_detalle.append({
                "numero": idx,
                "id": g.id,
                "sub_atencion": g.sub_atencion,
                "accion_realizada": g.accion_realizada,
                "fecha_programada": g.fecha_programada,
                "detalle_accion": g.detalle_accion,
                "evidencia_codigo": g.evidencia_codigo or "",
                "validacion": g.validacion,
                "requiere_terreno": g.requiere_terreno,
                "derivar_agenda": g.derivar_agenda,
                "fecha_registro": g.fecha_registro,
                "esta_aprobada": esta_aprobada,
                "puede_editar": es_supervisor or (es_dueno and not esta_aprobada),
            })

        casos_calculados.append({
            "id": caso.id,
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
        })

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
        },
    )


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def crear_caso_social(request):
    """Crea un Caso Nuevo y su primera Gestión en una transacción (HU-03)."""
    if request.method == "POST":
        rut = (request.POST.get("rut") or "").strip()
        es_supervisor = usuario_tiene_rol(request.user, "Supervisor")

        caso, _ = CasoSocial.objects.get_or_create(
            rut=rut,
            defaults={
                "usuario_nombre": (request.POST.get("usuario_nombre") or "").strip(),
                "telefono": (request.POST.get("telefono") or "").strip(),
                "funcionario": request.user,
            },
        )

        if caso.gestiones.count() >= 3:
            messages.error(request, "Este RUT ya alcanzó el máximo de 3 gestiones sociales.")
            return redirect("principal:area_social")

        fecha_prog = request.POST.get("fecha_programada") or None
        derivar_agenda = request.POST.get("derivar_agenda") == "True"
        validacion = request.POST.get("validacion", "Pendiente") if es_supervisor else "Pendiente"

        GestionSocial.objects.create(
            caso=caso,
            sub_atencion=request.POST.get("sub_atencion") or "Orientación Social",
            accion_realizada=request.POST.get("accion_realizada") or "Emergencia",
            fecha_programada=fecha_prog,
            detalle_accion=request.POST.get("detalle_accion", ""),
            evidencia_codigo=request.POST.get("evidencia", ""),
            validacion=validacion,
            requiere_terreno=(request.POST.get("requiere_terreno") == "True"),
            derivar_agenda=derivar_agenda,
        )

        if derivar_agenda:
            _derivar_caso_a_agenda(request, caso, fecha_prog)

        messages.success(request, "Caso social y gestión registrados correctamente.")
        return redirect("principal:area_social")

    return redirect("principal:area_social")


@requiere_roles("Funcionario", "Supervisor")
@transaction.atomic
def editar_caso_social(request):
    """
    Maneja 3 operaciones explícitas desde el modal del expediente:
    - actualizar_ciudadano: modifica teléfono del caso.
    - actualizar_gestion: corrige una gestión existente (bloqueada si ya está Aprobada).
    - agregar_gestion: registra la 2ª o 3ª gestión sin sobrescribir las anteriores.
    """
    if request.method != "POST":
        return redirect("principal:area_social")

    caso_id = request.POST.get("caso_id")
    modo = request.POST.get("modo", "agregar_gestion")
    es_supervisor = usuario_tiene_rol(request.user, "Supervisor")

    try:
        caso = CasoSocial.objects.get(id=caso_id)
    except CasoSocial.DoesNotExist:
        messages.error(request, "El caso especificado no existe.")
        return redirect("principal:area_social")

    if not es_supervisor and caso.funcionario_id != request.user.id:
        messages.error(request, "Solo puedes modificar expedientes creados por ti.")
        return redirect("principal:area_social")

    if modo == "actualizar_ciudadano":
        caso.telefono = (request.POST.get("telefono") or "").strip()
        caso.save(update_fields=["telefono"])
        messages.success(request, f"Teléfono actualizado para {caso.rut}.")
        return redirect("principal:area_social")

    if modo == "actualizar_gestion":
        gestion_id = request.POST.get("gestion_id")
        try:
            gestion = GestionSocial.objects.get(id=gestion_id, caso=caso)
        except GestionSocial.DoesNotExist:
            messages.error(request, "La gestión indicada no existe.")
            return redirect("principal:area_social")

        if gestion.validacion in ("Aprobado", "Aprobada") and not es_supervisor:
            messages.error(request, "Una gestión aprobada no permite modificaciones.")
            return redirect("principal:area_social")

        fecha_prog = request.POST.get("fecha_programada") or None
        estaba_derivada = gestion.derivar_agenda
        derivar_ahora = request.POST.get("derivar_agenda") == "True"

        gestion.sub_atencion = request.POST.get("sub_atencion") or gestion.sub_atencion
        gestion.accion_realizada = request.POST.get("accion_realizada") or gestion.accion_realizada
        gestion.fecha_programada = fecha_prog
        gestion.detalle_accion = request.POST.get("detalle_accion", "")
        gestion.evidencia_codigo = request.POST.get("evidencia", "")
        gestion.requiere_terreno = (request.POST.get("requiere_terreno") == "True")
        gestion.derivar_agenda = derivar_ahora
        if es_supervisor and request.POST.get("validacion"):
            gestion.validacion = request.POST.get("validacion")
        gestion.save()

        if derivar_ahora and not estaba_derivada:
            _derivar_caso_a_agenda(request, caso, fecha_prog)

        messages.success(request, "Gestión actualizada correctamente.")
        return redirect("principal:area_social")

    
    if caso.gestiones.count() >= 3:
        messages.error(request, "Límite máximo alcanzado (3 de 3). No se pueden agregar más gestiones.")
        return redirect("principal:area_social")

    fecha_prog = request.POST.get("fecha_programada") or None
    derivar_agenda = request.POST.get("derivar_agenda") == "True"
    validacion = request.POST.get("validacion", "Pendiente") if es_supervisor else "Pendiente"

    GestionSocial.objects.create(
        caso=caso,
        sub_atencion=request.POST.get("sub_atencion") or "Orientación Social",
        accion_realizada=request.POST.get("accion_realizada") or "Emergencia",
        fecha_programada=fecha_prog,
        detalle_accion=request.POST.get("detalle_accion", ""),
        evidencia_codigo=request.POST.get("evidencia", ""),
        validacion=validacion,
        requiere_terreno=(request.POST.get("requiere_terreno") == "True"),
        derivar_agenda=derivar_agenda,
    )

    if derivar_agenda:
        _derivar_caso_a_agenda(request, caso, fecha_prog)

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
            return redirect("principal:panel")
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
    """Endpoint para autocompletar nombre y teléfono cuando el RUT ya existe en BD."""
    rut = (request.GET.get("rut") or "").strip()
    if not rut:
        return JsonResponse({"encontrado": False})

    rut_limpio = rut.replace(".", "").upper()
    vecino = Vecino.objects.filter(Q(rut__iexact=rut) | Q(rut__iexact=rut_limpio)).first()
    if vecino:
        return JsonResponse({
            "encontrado": True,
            "rut": vecino.rut,
            "nombre": vecino.nombre_completo,
            "telefono": vecino.telefono,
            "direccion": vecino.direccion,
        })

    caso = CasoSocial.objects.filter(Q(rut__iexact=rut) | Q(rut__iexact=rut_limpio)).first()
    if caso:
        return JsonResponse({
            "encontrado": True,
            "rut": caso.rut,
            "nombre": caso.usuario_nombre,
            "telefono": caso.telefono or "",
            "direccion": "",
        })

    return JsonResponse({"encontrado": False})

@requiere_roles("Supervisor", "Administrador")
def asignar_tareas(request):
    hoy = timezone.localdate()

    # --- CREAR O EDITAR TAREA (POST) ---
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

    # --- LISTADO, RESUMEN Y FILTROS (GET) ---
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