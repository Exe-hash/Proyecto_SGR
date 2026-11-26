from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .forms import JuntaVecinosForm, TipoOrganizacionForm
from .models import Dirigencia, JuntaVecinos, Territorio, TipoOrganizacion, Vecino
from .reglas import normalizar_rut
from .views import renderizar, requiere_roles, usuario_tiene_rol

TIPOS_BASE = [
    ("Junta de Vecinos", "Organización comunitaria territorial del sector."),
    ("Organización Comunitaria Funcional", "Personas unidas por un objetivo, interés o función común en la comuna."),
    ("Club de Adulto Mayor", "Espacios de integración, recreación y apoyo mutuo para personas mayores."),
    ("Organización Deportiva", "Clubes o talleres enfocados en la práctica y fomento del deporte."),
    ("Centro de Madres / Cultural / Juvenil", "Desarrollo artístico, social, comunitario o de capacitación."),
    ("Comité de Vecinos / Allegados / Seguridad", "Comités vecinales específicos, vivienda, APR o seguridad."),
]

CARGOS_UNICOS = {"Presidente", "Secretario", "Tesorero"}


def asegurar_tipos_organizacion():
    """Garantiza que existan los tipos base y vincula organizaciones antiguas si alguna quedó sin FK."""
    for nombre, desc in TIPOS_BASE:
        TipoOrganizacion.objects.get_or_create(
            nombre=nombre,
            defaults={"descripcion": desc, "activo": True},
        )
    for org in JuntaVecinos.objects.filter(tipo__isnull=True):
        texto = (org.tipo_organizacion or "").strip() or "Organización Comunitaria Funcional"
        tipo_obj, _ = TipoOrganizacion.objects.get_or_create(nombre=texto, defaults={"activo": True})
        org.tipo = tipo_obj
        org.save(update_fields=["tipo", "tipo_organizacion"])


def _delegacion_scope(user):
    """Devuelve None para Administrador/superusuario, o la Delegacion asignada para Supervisor."""
    es_admin = user.is_superuser or usuario_tiene_rol(user, "Administrador")
    if es_admin:
        return None, True
    perfil = getattr(user, "perfil", None)
    return (perfil.delegacion if perfil else None), False


def _verificar_acceso_organizacion(user, org: JuntaVecinos):
    deleg_scope, es_admin = _delegacion_scope(user)
    if not es_admin and deleg_scope and org.territorio.delegacion_id != deleg_scope.id:
        raise PermissionDenied("Solo puedes gestionar organizaciones de tu propia delegación.")


def vincular_vecino_a_organizacion(vecino: Vecino | None, junta_id_raw: str | int | None):
    """
    Asocia un vecino a la organización elegida al atenderlo (como Socio si aún no pertenece).
    Si junta_id_raw está vacío o es '0', significa 'No pertenece a ninguna organización' y no crea vínculo.
    """
    if not vecino or not junta_id_raw:
        return None
    junta_str = str(junta_id_raw).strip()
    if not junta_str.isdigit() or int(junta_str) <= 0:
        return None

    junta = JuntaVecinos.objects.filter(pk=int(junta_str), activa=True).first()
    if not junta:
        return None

    ya_pertenece = Dirigencia.objects.filter(
        vecino=vecino,
        junta_vecinos=junta,
        vigente=True,
    ).exists()
    if not ya_pertenece:
        Dirigencia.objects.create(
            vecino=vecino,
            junta_vecinos=junta,
            cargo_dirigencia="Socio",
            fecha_inicio=timezone.localdate(),
            vigente=True,
        )
    return junta


@requiere_roles("Supervisor", "Administrador")
def organizaciones_lista(request):
    asegurar_tipos_organizacion()
    deleg_scope, es_admin = _delegacion_scope(request.user)

    qs = (
        JuntaVecinos.objects.select_related("tipo", "territorio__delegacion")
        .prefetch_related("dirigencias__vecino")
        .order_by("territorio__nombre", "nombre")
    )
    territorios_qs = Territorio.objects.filter(activo=True).select_related("delegacion").order_by("nombre")

    if deleg_scope:
        qs = qs.filter(territorio__delegacion=deleg_scope)
        territorios_qs = territorios_qs.filter(delegacion=deleg_scope)

    filtro_territorio = (request.GET.get("territorio_id") or "").strip()
    filtro_tipo = (request.GET.get("tipo_id") or "").strip()
    filtro_estado = (request.GET.get("estado") or "activas").strip()

    if filtro_territorio.isdigit():
        qs = qs.filter(territorio_id=int(filtro_territorio))
    if filtro_tipo.isdigit():
        qs = qs.filter(tipo_id=int(filtro_tipo))
    if filtro_estado == "activas":
        qs = qs.filter(activa=True)
    elif filtro_estado == "inactivas":
        qs = qs.filter(activa=False)

    organizaciones = []
    for org in qs:
        vigentes = [d for d in org.dirigencias.all() if d.vigente]
        presidente = next((d for d in vigentes if d.cargo_dirigencia == "Presidente"), None)
        org.presidente_vigente = presidente
        org.total_registrados_sgr = len(vigentes)
        organizaciones.append(org)

    return renderizar(
        request,
        "principal/organizaciones_lista.html",
        {
            "pagina": "organizaciones",
            "organizaciones": organizaciones,
            "tipos_organizacion": TipoOrganizacion.objects.all().order_by("-activo", "nombre"),
            "territorios_filtro": territorios_qs,
            "filtro_territorio": filtro_territorio,
            "filtro_tipo": filtro_tipo,
            "filtro_estado": filtro_estado,
            "es_admin_org": es_admin,
            "form_tipo": TipoOrganizacionForm(),
        },
    )


@requiere_roles("Supervisor", "Administrador")
def organizacion_crear(request):
    asegurar_tipos_organizacion()
    deleg_scope, _ = _delegacion_scope(request.user)

    if request.method == "POST":
        form = JuntaVecinosForm(request.POST, delegacion_restringida=deleg_scope)
        if form.is_valid():
            org = form.save()
            messages.success(request, f"Organización '{org.nombre}' registrada correctamente.")
            return redirect("principal:organizaciones_lista")
    else:
        form = JuntaVecinosForm(delegacion_restringida=deleg_scope)

    return renderizar(
        request,
        "principal/organizacion_form.html",
        {
            "pagina": "organizaciones",
            "form": form,
            "titulo": "Nueva Organización / Junta de Vecinos",
            "es_edicion": False,
        },
    )


@requiere_roles("Supervisor", "Administrador")
def organizacion_editar(request, org_id):
    asegurar_tipos_organizacion()
    org = get_object_or_404(JuntaVecinos.objects.select_related("territorio__delegacion"), pk=org_id)
    _verificar_acceso_organizacion(request.user, org)
    deleg_scope, _ = _delegacion_scope(request.user)

    if request.method == "POST":
        form = JuntaVecinosForm(request.POST, instance=org, delegacion_restringida=deleg_scope)
        if form.is_valid():
            org = form.save()
            messages.success(request, f"Organización '{org.nombre}' actualizada.")
            return redirect("principal:organizaciones_lista")
    else:
        form = JuntaVecinosForm(instance=org, delegacion_restringida=deleg_scope)

    return renderizar(
        request,
        "principal/organizacion_form.html",
        {
            "pagina": "organizaciones",
            "form": form,
            "org": org,
            "titulo": f"Editar: {org.nombre}",
            "es_edicion": True,
        },
    )


@requiere_roles("Supervisor", "Administrador")
def organizacion_toggle_estado(request, org_id):
    if request.method != "POST":
        return redirect("principal:organizaciones_lista")
    org = get_object_or_404(JuntaVecinos.objects.select_related("territorio"), pk=org_id)
    _verificar_acceso_organizacion(request.user, org)

    org.activa = not org.activa
    org.save(update_fields=["activa"])
    estado_txt = "reactivada" if org.activa else "desactivada"
    messages.success(request, f"Organización '{org.nombre}' {estado_txt}.")
    return redirect("principal:organizaciones_lista")


@requiere_roles("Supervisor", "Administrador")
def tipo_organizacion_crear(request):
    if request.method != "POST":
        return redirect("principal:organizaciones_lista")
    form = TipoOrganizacionForm(request.POST)
    if form.is_valid():
        tipo = form.save()
        messages.success(request, f"Tipo de organización '{tipo.nombre}' creado correctamente.")
    else:
        errores = " ".join([e for errs in form.errors.values() for e in errs])
        messages.error(request, f"No se pudo crear el tipo: {errores}")
    return redirect("principal:organizaciones_lista")


@requiere_roles("Supervisor", "Administrador")
def tipo_organizacion_toggle(request, tipo_id):
    if request.method != "POST":
        return redirect("principal:organizaciones_lista")
    tipo = get_object_or_404(TipoOrganizacion, pk=tipo_id)
    tipo.activo = not tipo.activo
    tipo.save(update_fields=["activo"])
    messages.success(request, f"Tipo '{tipo.nombre}' {'activado' if tipo.activo else 'desactivado'}.")
    return redirect("principal:organizaciones_lista")


@requiere_roles("Supervisor", "Administrador")
@transaction.atomic
def organizacion_directiva(request, org_id):
    org = get_object_or_404(
        JuntaVecinos.objects.select_related("tipo", "territorio__delegacion"),
        pk=org_id,
    )
    _verificar_acceso_organizacion(request.user, org)

    if request.method == "POST":
        vecino_id = (request.POST.get("vecino_id") or "").strip()
        rut_raw = (request.POST.get("rut") or "").strip()
        nombre_vecino = (request.POST.get("nombre_completo") or "").strip()
        telefono = (request.POST.get("telefono") or "").strip()
        cargo = (request.POST.get("cargo_dirigencia") or "Socio").strip()
        f_ini_str = (request.POST.get("fecha_inicio") or "").strip()
        f_fin_str = (request.POST.get("fecha_termino") or "").strip()

        if cargo not in dict(Dirigencia.CARGO_DIRIGENCIA_CHOICES):
            messages.error(request, "Cargo de dirigencia inválido.")
            return redirect("principal:organizacion_directiva", org_id=org.id)

        try:
            f_ini = date.fromisoformat(f_ini_str) if f_ini_str else timezone.localdate()
            f_fin = date.fromisoformat(f_fin_str) if f_fin_str else None
        except ValueError:
            messages.error(request, "Formato de fecha inválido.")
            return redirect("principal:organizacion_directiva", org_id=org.id)

        if f_fin and f_fin < f_ini:
            messages.error(request, "La fecha de término no puede ser anterior a la fecha de inicio.")
            return redirect("principal:organizacion_directiva", org_id=org.id)


        vecino = None
        if vecino_id.isdigit():
            vecino = Vecino.objects.filter(pk=int(vecino_id)).first()
        elif rut_raw:
            rut_norm = normalizar_rut(rut_raw)
            vecino = Vecino.objects.filter(rut=rut_norm).first()
            if vecino:
                actualizado = False
                if nombre_vecino and not vecino.nombre_completo:
                    vecino.nombre_completo = nombre_vecino
                    actualizado = True
                if telefono and not vecino.telefono:
                    vecino.telefono = telefono
                    actualizado = True
                if actualizado:
                    vecino.save()
            else:
                if not nombre_vecino:
                    messages.error(request, "Para registrar un vecino nuevo debes indicar su nombre completo.")
                    return redirect("principal:organizacion_directiva", org_id=org.id)
                vecino = Vecino.objects.create(
                    rut=rut_norm,
                    nombre_completo=nombre_vecino,
                    telefono=telefono,
                    territorio=org.territorio,
                )

        if not vecino:
            messages.error(request, "Selecciona un vecino existente o ingresa un RUT válido.")
            return redirect("principal:organizacion_directiva", org_id=org.id)


        if Dirigencia.objects.filter(
            vecino=vecino,
            junta_vecinos=org,
            cargo_dirigencia=cargo,
            vigente=True,
        ).exists():
            messages.error(request, f"{vecino.nombre_completo} ya figura vigente como {cargo} en esta organización.")
            return redirect("principal:organizacion_directiva", org_id=org.id)


        if cargo in CARGOS_UNICOS:
            titular = Dirigencia.objects.filter(
                junta_vecinos=org,
                cargo_dirigencia=cargo,
                vigente=True,
            ).select_related("vecino").first()
            if titular:
                messages.error(
                    request,
                    f"Ya existe un {cargo} vigente ({titular.vecino.nombre_completo}). Finaliza primero su período.",
                )
                return redirect("principal:organizacion_directiva", org_id=org.id)

        Dirigencia.objects.create(
            vecino=vecino,
            junta_vecinos=org,
            cargo_dirigencia=cargo,
            fecha_inicio=f_ini,
            fecha_termino=f_fin,
            vigente=True,
        )
        messages.success(request, f"{vecino.nombre_completo} agregado como {cargo} en '{org.nombre}'.")
        return redirect("principal:organizacion_directiva", org_id=org.id)

    orden_cargo = {"Presidente": 1, "Secretario": 2, "Tesorero": 3, "Director": 4, "Socio": 5}
    todas = list(org.dirigencias.select_related("vecino").all())
    vigentes = sorted([d for d in todas if d.vigente], key=lambda x: (orden_cargo.get(x.cargo_dirigencia, 9), x.vecino.nombre_completo))
    historial = sorted([d for d in todas if not d.vigente], key=lambda x: x.fecha_termino or x.fecha_inicio, reverse=True)

    return renderizar(
        request,
        "principal/organizacion_directiva.html",
        {
            "pagina": "organizaciones",
            "org": org,
            "vigentes": vigentes,
            "historial": historial,
            "cargos_dirigencia": Dirigencia.CARGO_DIRIGENCIA_CHOICES,
            "vecinos_disponibles": Vecino.objects.filter(activo=True).order_by("nombre_completo")[:300],
            "hoy": timezone.localdate(),
        },
    )


@requiere_roles("Supervisor", "Administrador")
def dirigencia_finalizar(request, dir_id):
    dirigencia = get_object_or_404(Dirigencia.objects.select_related("junta_vecinos__territorio", "vecino"), pk=dir_id)
    org = dirigencia.junta_vecinos
    _verificar_acceso_organizacion(request.user, org)

    if request.method == "POST" and dirigencia.vigente:
        dirigencia.vigente = False
        if not dirigencia.fecha_termino:
            dirigencia.fecha_termino = timezone.localdate()
        dirigencia.save(update_fields=["vigente", "fecha_termino"])
        messages.success(
            request,
            f"Se finalizó el cargo de {dirigencia.cargo_dirigencia} para {dirigencia.vecino.nombre_completo} (pasó a historial).",
        )
    return redirect("principal:organizacion_directiva", org_id=org.id)