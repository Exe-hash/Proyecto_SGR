"""Vistas de presentación del SGR con datos ficticios de demostración."""

from functools import wraps

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from .datos_demo import COMPROMISOS, EQUIPO, EVIDENCIAS, METAS
import uuid
from .models import Evidencia, Compromiso, Delegacion, Observacion
from .models import Meta

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
            "puede_registrar_actividades": usuario_tiene_rol(
                request.user, "Funcionario"
            ),
            "puede_ver_agenda": usuario_tiene_rol(
                request.user, "Funcionario", "Jefatura"
            ),
            "puede_ver_equipo": usuario_tiene_rol(
                request.user, "Jefatura"
            ),
            "puede_verificar_evidencias": usuario_tiene_rol(
                request.user, "Verificador"
            ),
            "puede_administrar": usuario_tiene_rol(
                request.user, "Administrador"
            ),
            "nombre_usuario": (
                request.user.get_full_name().strip()
                or request.user.get_username()
            ),
            "cargo_usuario": (
                perfil.cargo.nombre if perfil else "Sin cargo asignado"
            ),
            "delegacion_usuario": (
                perfil.delegacion.nombre
                if perfil
                else "Sin delegación asignada"
            ),
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
            
            # --- NUEVA LÓGICA DE REDIRECCIÓN DINÁMICA ---
            if usuario_tiene_rol(usuario, "Jefatura"):
                # Si es jefe, aterriza en el resumen de su equipo
                return redirect("principal:equipo")
            else:
                # Si es funcionario, aterriza en sus propias metas
                return redirect("principal:panel")
            # --------------------------------------------

        return render(
            request,
            "principal/inicio.html",
            {"error_inicio": "Usuario o contraseña incorrectos."},
        )

    return render(request, "principal/inicio.html")


# Asegúrate de que esta importación siga arriba en tu archivo:
# from .datos_demo import METAS, COMPROMISOS, EQUIPO, EVIDENCIAS

@requiere_roles("Funcionario", "Jefatura", "Verificador")
def panel(request):
    mis_evidencias = Evidencia.objects.filter(funcionario=request.user)
    ev_aprobadas = mis_evidencias.filter(estado="Aprobada").count()
    ev_revision = mis_evidencias.filter(estado="En revisión").count()
    ev_rechazadas = mis_evidencias.filter(estado="Rechazada").count()
    
    total_ev = mis_evidencias.count()
    porcentaje_avance = int((ev_aprobadas / total_ev * 100)) if total_ev > 0 else 0
    compromisos_vencer = Compromiso.objects.filter(responsable=request.user).order_by('plazo')[:4]

    # --- LÓGICA MATEMÁTICA DE LAS METAS ---
    metas_db = Meta.objects.filter(vigente=True)
    metas_calculadas = []

    for m in metas_db:
        # Cuenta cuántas evidencias aprobadas tiene el funcionario PARA ESTA META específica
        avance_real = mis_evidencias.filter(meta_relacionada=m, estado="Aprobada").count()
        
        # Calcula el porcentaje (avance / meta * 100)
        cumplimiento = (avance_real / m.valor_objetivo * 100) if m.valor_objetivo > 0 else 0
        if cumplimiento > 100: cumplimiento = 100 # Tope visual al 100%
        
        # Calcula cuánto suma al porcentaje final
        resultado = (m.ponderacion * cumplimiento) / 100

        metas_calculadas.append({
            "id": m.id,
            "nombre": m.nombre,
            "ponderacion": m.ponderacion,
            "avance": avance_real,
            "meta": m.valor_objetivo,
            "barra": int(cumplimiento),
            "resultado": round(resultado, 1)
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
            "metas": metas_calculadas, # REEMPLAZAMOS DATOS FALSOS POR LA MATEMÁTICA REAL
        },
    )


@requiere_roles("Funcionario")
def actividades(request):
    if request.method == "POST":
        fecha = request.POST.get("fecha")
        actividad = request.POST.get("actividad")
        accion = request.POST.get("accion")
        contacto = request.POST.get("contacto")
        telefono = request.POST.get("telefono")
        fotografia = request.FILES.get("fotografia")
        
        # CAPTURAMOS LA META ELEGIDA
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
            meta_relacionada_id=meta_id # LO GUARDAMOS EN LA BBDD
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
            # ENVIAMOS LAS METAS VIGENTES AL FORMULARIO
            "metas_reales": Meta.objects.filter(vigente=True), 
        },
    )


@requiere_roles("Funcionario", "Jefatura")
def agenda(request):
    # 1. Si enviamos el formulario desde el cajón lateral (UPDATE)
    if request.method == "POST":
        codigo_recibido = request.POST.get("codigo")
        nuevo_estado = request.POST.get("nuevo_estado")
        nuevo_texto = request.POST.get("observacion")
        
        if codigo_recibido and nuevo_estado:
            # Actualizamos el estado del compromiso
            compromiso = Compromiso.objects.get(codigo=codigo_recibido)
            compromiso.estado = nuevo_estado
            compromiso.save()
            
            # Si el usuario escribió una observación, la guardamos
            if nuevo_texto:
                Observacion.objects.create(
                    compromiso=compromiso,
                    autor=request.user,
                    texto=nuevo_texto
                )
            
        # Recargamos la página para limpiar el formulario y ver los cambios
        return redirect("principal:agenda")

    # 2. Si entramos a la página normalmente a mirar el tablero (GET)
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
    # 1. Traer SOLO las evidencias de este usuario desde MySQL
    mis_evidencias = Evidencia.objects.filter(funcionario=request.user)
    
    # 2. Calcular los números para las cajas de resumen
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

@requiere_roles("Jefatura", "Administrador")
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


@requiere_roles("Jefatura", "Verificador", "Administrador")
def verificacion(request):
    if request.method == "POST":
        # 1. Leemos los datos exactos que envía tu JavaScript
        codigo_evi = request.POST.get("codigo") 
        nuevo_estado = request.POST.get("nuevo_estado")
        
        # 2. Buscamos la evidencia por su código (ej: EVI-123)
        evidencia = Evidencia.objects.get(codigo=codigo_evi)
        
        # 3. Guardamos el estado (Aprobada, Rechazada o Corregir)
        evidencia.estado = nuevo_estado
        evidencia.save()
        
        return redirect("principal:verificacion")
        
    # GET: Mostrar solo las que faltan por revisar
    pendientes = Evidencia.objects.filter(estado="En revisión")
    
    return renderizar(
        request, 
        "principal/verificacion.html", 
        {
            "pagina": "verificacion",
            "evidencias": pendientes,
            "total_pendientes": pendientes.count() # Enviamos el total para tu HTML
        }
    )

from .models import Meta # Asegúrate de tener esto arriba, o déjalo aquí adentro si quieres hacerlo rápido

@requiere_roles("Administrador")
def administracion(request):
    if request.method == "POST":
        # 1. Crear nueva meta
        if "crear_meta" in request.POST:
            Meta.objects.create(
                nombre=request.POST.get("nombre"),
                valor_objetivo=request.POST.get("valor_objetivo"),
                ponderacion=request.POST.get("ponderacion")
            )
        
        # 2. Editar meta existente
        elif "editar_meta" in request.POST:
            meta_id = request.POST.get("meta_id")
            meta = Meta.objects.get(id=meta_id)
            meta.nombre = request.POST.get("nombre")
            meta.valor_objetivo = request.POST.get("valor_objetivo")
            meta.ponderacion = request.POST.get("ponderacion")
            meta.save()
            
        # 3. Eliminar meta
        elif "eliminar_meta" in request.POST:
            meta_id = request.POST.get("meta_id")
            Meta.objects.filter(id=meta_id).delete()

        return redirect("principal:administracion")
            
    # GET: Traer las metas reales de MySQL
    metas_reales = Meta.objects.all().order_by('-id')
    
    return renderizar(
        request,
        "principal/administracion.html",
        {
            "pagina": "administracion",
            "metas_reales": metas_reales,
        },
    )