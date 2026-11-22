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

from .datos_demo import COMPROMISOS, EQUIPO, EVIDENCIAS, METAS
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

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from .models import AjusteDesempeno, Vecino

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

    return contexto


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
    contexto = {}
    if request.user.is_authenticated:
        contexto["destino_usuario"] = destino_por_rol(request.user)
    return render(request, "principal/landing.html", contexto)

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
                # NUEVO: Si el cargo contiene la palabra "social", va a su panel especial
                if hasattr(usuario, 'perfil') and usuario.perfil.cargo and 'social' in usuario.perfil.cargo.nombre.lower():
                    return redirect("principal:area_social")
                
                # Si es territorial, va al panel normal
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
            compromiso = Compromiso.objects.get(codigo=codigo_recibido)
            compromiso.estado = nuevo_estado
            compromiso.save()
            
            if nuevo_texto:
                Observacion.objects.create(
                    compromiso=compromiso,
                    autor=request.user,
                    texto=nuevo_texto
                )
            
        return redirect("principal:agenda")

    compromisos_reales = Compromiso.objects.all()
    
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
    mis_evidencias = Evidencia.objects.filter(funcionario=request.user)
    
    totales = mis_evidencias.count()
    aprobadas = mis_evidencias.filter(estado="Aprobada").count()
    pendientes = totales - aprobadas

    return renderizar(
        request,
        "principal/evidencias.html",
        {
            "pagina": "evidencias",
            "evidencias_reales": mis_evidencias, # Enviamos los datos verdaderos
            "totales": totales,
            "aprobadas": aprobadas,
            "pendientes": pendientes,
        },
    )


from django.contrib.auth.models import User

@requiere_roles("Supervisor", "Administrador")
def equipo(request):
    todas_evidencias = Evidencia.objects.all()
    total_aprobadas = todas_evidencias.filter(estado="Aprobada").count()
    total_revision = todas_evidencias.filter(estado="En revisión").count()
    total_general = todas_evidencias.count()
    
    # Calculamos el avance global de todo el equipo
    avance_global = int((total_aprobadas / total_general * 100)) if total_general > 0 else 0

    funcionarios_db = User.objects.filter(groups__name="Funcionario")
    equipo_calculado = []
    
    # Calculamos el desempeño individual de cada funcionario
    for f in funcionarios_db:
        evs = Evidencia.objects.filter(funcionario=f)
        aprob = evs.filter(estado="Aprobada").count()
        tot = evs.count()
        porcentaje = int((aprob / tot * 100)) if tot > 0 else 0
        
        clase = "aprobada" if porcentaje >= 60 else ("corregir" if porcentaje >= 40 else "rechazada")
        estado = "Óptimo" if porcentaje >= 60 else ("En riesgo" if porcentaje >= 40 else "Crítico")
        
        # Obtenemos iniciales para el avatar (Ej: CC para Catherine Contreras)
        iniciales = f"{f.first_name[:1]}{f.last_name[:1]}" if f.first_name else "F"
        
        equipo_calculado.append({
            "nombre": f.get_full_name() or f.username,
            "iniciales": iniciales.upper(),
            "cargo": "Territorial", 
            "porcentaje": porcentaje,
            "barra": porcentaje,
            "clase": clase,
            "estado": estado
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
            "equipo": equipo_calculado, # Enviamos la lista procesada
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
    mis_evidencias = Evidencia.objects.filter(funcionario=request.user)
    ev_aprobadas = mis_evidencias.filter(estado="Aprobada").count()
    ev_revision = mis_evidencias.filter(estado="En revisión").count()
    ev_rechazadas = mis_evidencias.filter(estado="Rechazada").count()

    total_ev = mis_evidencias.count()
    porcentaje_avance = int((ev_aprobadas / total_ev * 100)) if total_ev > 0 else 0
    compromisos_vencer = Compromiso.objects.filter(responsable=request.user).order_by("plazo")[:4]

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
            "barra": min(int(cumplimiento), 100),  # Ancho visual máximo 100%
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

    # Modo por defecto: agregar_gestion (2ª o 3ª atención nueva)
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