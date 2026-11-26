from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from .forms import (
    AsignacionMetaForm,
    CargoForm,
    CatalogoMetaForm,
    DelegacionForm,
    HitoForm,
    SubtipoAtencionForm,
    TerritorioForm,
    TipoAtencionForm,
    TrimestreForm,
    VecinoForm,
)
from .models import (
    AsignacionMeta,
    Cargo,
    CatalogoMeta,
    Delegacion,
    Hito,
    SubtipoAtencion,
    Territorio,
    TipoAtencion,
    Trimestre,
    Vecino,
)
from .views import renderizar, requiere_roles


def _bool_txt(val, si="Sí", no="No"):
    return si if val else no


CATALOGOS_CONFIG = {
    "delegaciones": {
        "titulo": "Delegaciones Municipales",
        "singular": "Delegación",
        "tab_volver": "catalogos",
        "model": Delegacion,
        "form": DelegacionForm,
        "select_related": (),
        "columnas": ["Nombre", "Estado"],
        "fila": lambda o: [o.nombre, _bool_txt(o.activa, "Activa", "Inactiva")],
        "toggle_field": "activa",
        "invertir_toggle": False,
    },
    "territorios": {
        "titulo": "Territorios / Sectores",
        "singular": "Territorio",
        "tab_volver": "catalogos",
        "model": Territorio,
        "form": TerritorioForm,
        "select_related": ("delegacion",),
        "columnas": ["Territorio", "Delegación", "Estado"],
        "fila": lambda o: [o.nombre, o.delegacion.nombre, _bool_txt(o.activo, "Activo", "Inactivo")],
        "toggle_field": "activo",
        "invertir_toggle": False,
    },
    "cargos": {
        "titulo": "Cargos Funcionales",
        "singular": "Cargo",
        "tab_volver": "metas",
        "model": Cargo,
        "form": CargoForm,
        "select_related": (),
        "columnas": ["Cargo", "Área Social", "Meta Mínima", "Estado"],
        "fila": lambda o: [
            o.nombre,
            _bool_txt(o.es_area_social),
            f"{o.meta_minima_porcentaje}%",
            _bool_txt(o.activo, "Activo", "Inactivo"),
        ],
        "toggle_field": "activo",
        "invertir_toggle": False,
    },
    "vecinos": {
        "titulo": "Registro de Vecinos",
        "singular": "Vecino",
        "tab_volver": "catalogos",
        "model": Vecino,
        "form": VecinoForm,
        "select_related": ("territorio",),
        "columnas": ["RUT", "Nombre Completo", "Teléfono", "Territorio", "Estado"],
        "fila": lambda o: [
            o.rut,
            o.nombre_completo,
            o.telefono or "Sin fono",
            o.territorio.nombre if o.territorio else "-",
            _bool_txt(o.activo, "Activo", "Inactivo"),
        ],
        "toggle_field": "activo",
        "invertir_toggle": False,
    },
    "hitos": {
        "titulo": "Hitos Territoriales",
        "singular": "Hito",
        "tab_volver": "catalogos",
        "model": Hito,
        "form": HitoForm,
        "select_related": ("territorio", "responsable"),
        "columnas": ["Hito", "Territorio", "Responsable", "Fecha Comprometida", "Estado"],
        "fila": lambda o: [
            o.nombre,
            o.territorio.nombre,
            o.responsable.get_full_name().strip() or o.responsable.username,
            o.fecha_comprometida.strftime("%d/%m/%Y"),
            o.estado,
        ],
        "toggle_field": None,
        "invertir_toggle": False,
    },
    "tipos-atencion": {
        "titulo": "Tipos de Atención",
        "singular": "Tipo de Atención",
        "tab_volver": "catalogos",
        "model": TipoAtencion,
        "form": TipoAtencionForm,
        "select_related": (),
        "columnas": ["Nombre", "Área", "Estado"],
        "fila": lambda o: [o.nombre, o.get_area_display(), _bool_txt(o.activo, "Activo", "Inactivo")],
        "toggle_field": "activo",
        "invertir_toggle": False,
    },
    "subtipos-atencion": {
        "titulo": "Subtipos de Atención",
        "singular": "Subtipo de Atención",
        "tab_volver": "catalogos",
        "model": SubtipoAtencion,
        "form": SubtipoAtencionForm,
        "select_related": ("tipo_atencion",),
        "columnas": ["Tipo Padre", "Subtipo", "Coordinación (0 pts)", "Estado"],
        "fila": lambda o: [
            o.tipo_atencion.nombre,
            o.nombre,
            _bool_txt(o.es_coordinacion, "Sí (Sin puntaje)", "No (Pondera)"),
            _bool_txt(o.activo, "Activo", "Inactivo"),
        ],
        "toggle_field": "activo",
        "invertir_toggle": False,
    },
    "trimestres": {
        "titulo": "Trimestres de Evaluación",
        "singular": "Trimestre",
        "tab_volver": "periodos",
        "model": Trimestre,
        "form": TrimestreForm,
        "select_related": (),
        "columnas": ["Código", "Nombre", "Rango Fechas", "Días / Tope", "Estado"],
        "fila": lambda o: [
            o.codigo,
            o.nombre,
            f"{o.fecha_inicio.strftime('%d/%m/%Y')} — {o.fecha_termino.strftime('%d/%m/%Y')}",
            f"{o.dias_computables} días · máx {o.tope_maximo_porcentaje}%",
            _bool_txt(o.cerrado, "Cerrado", "Abierto"),
        ],
        "toggle_field": "cerrado",
        "invertir_toggle": True,
    },
    "catalogo-metas": {
        "titulo": "Catálogo General de Metas",
        "singular": "Meta de Catálogo",
        "tab_volver": "metas",
        "model": CatalogoMeta,
        "form": CatalogoMetaForm,
        "select_related": ("cargo_sugerido",),
        "columnas": ["Código", "Nombre", "Cargo Sugerido", "Tipo", "Estado"],
        "fila": lambda o: [
            o.codigo,
            o.nombre,
            o.cargo_sugerido.nombre if o.cargo_sugerido else "Cualquier cargo",
            _bool_txt(o.es_porcentual, "Porcentual (%)", "Cantidad"),
            _bool_txt(o.activa, "Activa", "Inactiva"),
        ],
        "toggle_field": "activa",
        "invertir_toggle": False,
    },
    "asignaciones-meta": {
        "titulo": "Asignación de Metas por Funcionario y Trimestre",
        "singular": "Asignación de Meta",
        "tab_volver": "metas",
        "model": AsignacionMeta,
        "form": AsignacionMetaForm,
        "select_related": ("funcionario", "trimestre", "catalogo_meta"),
        "columnas": ["Trimestre", "Funcionario", "Meta del Catálogo", "Cantidad Exigida", "Ponderación / Tope"],
        "fila": lambda o: [
            o.trimestre.codigo,
            o.funcionario.get_full_name().strip() or o.funcionario.username,
            f"{o.catalogo_meta.codigo} · {o.catalogo_meta.nombre}",
            str(o.cantidad_exigida),
            f"{o.ponderacion}% (tope {o.tope_cumplimiento}%)",
        ],
        "toggle_field": None,
        "invertir_toggle": False,
    },
}


def _get_cfg(slug: str) -> dict:
    cfg = CATALOGOS_CONFIG.get(slug)
    if not cfg:
        raise Http404("Catálogo no encontrado.")
    return cfg


@requiere_roles("Administrador")
def catalogo_lista(request, slug):
    cfg = _get_cfg(slug)
    qs = cfg["model"].objects.all()
    if cfg["select_related"]:
        qs = qs.select_related(*cfg["select_related"])

    filas = []
    toggle_field = cfg["toggle_field"]
    invertir = cfg["invertir_toggle"]

    for obj in qs:
        if toggle_field:
            valor_actual = getattr(obj, toggle_field)
            if invertir:  # Trimestre.cerrado
                accion_label = "Reabrir" if valor_actual else "Cerrar"
                accion_clase = "btn-outline-success" if valor_actual else "btn-outline-warning"
            else:
                accion_label = "Desactivar" if valor_actual else "Activar"
                accion_clase = "btn-outline-danger" if valor_actual else "btn-outline-success"
            es_borrado = False
        else:
            accion_label = "Eliminar"
            accion_clase = "btn-outline-danger"
            es_borrado = True

        filas.append({
            "pk": obj.pk,
            "valores": cfg["fila"](obj),
            "accion_label": accion_label,
            "accion_clase": accion_clase,
            "es_borrado": es_borrado,
        })

    return renderizar(
        request,
        "principal/catalogo_lista.html",
        {
            "pagina": "administracion",
            "slug": slug,
            "titulo": cfg["titulo"],
            "singular": cfg["singular"],
            "tab_volver": cfg["tab_volver"],
            "columnas": cfg["columnas"],
            "filas": filas,
        },
    )


@requiere_roles("Administrador")
def catalogo_crear(request, slug):
    cfg = _get_cfg(slug)
    FormClass = cfg["form"]

    if request.method == "POST":
        form = FormClass(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"{cfg['singular']} '{obj}' creado correctamente.")
            return redirect("principal:catalogo_lista", slug=slug)
    else:
        form = FormClass()

    return renderizar(
        request,
        "principal/catalogo_form.html",
        {
            "pagina": "administracion",
            "slug": slug,
            "titulo": f"Nuevo/a {cfg['singular']}",
            "subtitulo": cfg["titulo"],
            "form": form,
            "es_edicion": False,
        },
    )


@requiere_roles("Administrador")
def catalogo_editar(request, slug, pk):
    cfg = _get_cfg(slug)
    FormClass = cfg["form"]
    obj = get_object_or_404(cfg["model"], pk=pk)

    if request.method == "POST":
        form = FormClass(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"{cfg['singular']} '{obj}' actualizado correctamente.")
            return redirect("principal:catalogo_lista", slug=slug)
    else:
        form = FormClass(instance=obj)

    return renderizar(
        request,
        "principal/catalogo_form.html",
        {
            "pagina": "administracion",
            "slug": slug,
            "titulo": f"Editar {cfg['singular']}",
            "subtitulo": str(obj),
            "form": form,
            "es_edicion": True,
        },
    )


@requiere_roles("Administrador")
def catalogo_accion(request, slug, pk):
    if request.method != "POST":
        return redirect("principal:catalogo_lista", slug=slug)

    cfg = _get_cfg(slug)
    obj = get_object_or_404(cfg["model"], pk=pk)
    toggle_field = cfg["toggle_field"]

    if toggle_field:
        nuevo_valor = not getattr(obj, toggle_field)
        setattr(obj, toggle_field, nuevo_valor)
        obj.save(update_fields=[toggle_field])
        if cfg["invertir_toggle"]:
            estado = "cerrado" if nuevo_valor else "reabierto"
        else:
            estado = "activado" if nuevo_valor else "desactivado"
        messages.success(request, f"{cfg['singular']} '{obj}' {estado} correctamente.")
    else:
        nombre = str(obj)
        try:
            obj.delete()
            messages.success(request, f"{cfg['singular']} '{nombre}' eliminado correctamente.")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar '{nombre}' porque tiene registros históricos asociados.",
            )

    return redirect("principal:catalogo_lista", slug=slug)