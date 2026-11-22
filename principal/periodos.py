import calendar
from datetime import date
from typing import Any

from django.http import HttpRequest
from django.utils import timezone


def _crear_trimestre(anio: int, numero: int, hoy: date) -> dict[str, Any]:
    mes_inicio = (numero - 1) * 3 + 1
    mes_fin = mes_inicio + 2
    fecha_inicio = date(anio, mes_inicio, 1)
    fecha_fin = date(anio, mes_fin, calendar.monthrange(anio, mes_fin)[1])
    etiquetas = {
        1: "Ene - Mar",
        2: "Abr - Jun",
        3: "Jul - Sep",
        4: "Oct - Dic",
    }

    return {
        "codigo": f"{anio}-Q{numero}",
        "anio": anio,
        "numero": numero,
        "etiqueta": f"Trimestre {etiquetas[numero]} {anio}",
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "estado": "Abierto" if fecha_fin >= hoy else "Cerrado",
    }


def obtener_trimestre_por_fecha(fecha: date | None = None) -> dict[str, Any]:
    hoy = fecha if fecha is not None else timezone.localdate()
    numero = (hoy.month - 1) // 3 + 1
    return _crear_trimestre(hoy.year, numero, hoy)


def listar_trimestres_disponibles(
    fecha_referencia: date | None = None,
) -> list[dict[str, Any]]:
    referencia = (
        fecha_referencia if fecha_referencia is not None else timezone.localdate()
    )
    trimestre_actual = (referencia.month - 1) // 3
    indice_actual = referencia.year * 4 + trimestre_actual

    periodos = []
    for desplazamiento in range(4):
        anio, indice_trimestre = divmod(indice_actual - desplazamiento, 4)
        periodos.append(
            _crear_trimestre(anio, indice_trimestre + 1, referencia)
        )

    return periodos


def contexto_periodo_actual(request: HttpRequest) -> dict[str, Any]:
    periodos_disponibles = listar_trimestres_disponibles()
    periodos_por_codigo = {
        periodo["codigo"]: periodo for periodo in periodos_disponibles
    }

    if "periodo" in request.GET:
        codigo_seleccionado = request.GET.get("periodo")
    else:
        codigo_seleccionado = request.session.get("periodo_seleccionado")

    periodo_activo = (
        periodos_por_codigo.get(codigo_seleccionado)
        if isinstance(codigo_seleccionado, str)
        else None
    )
    if periodo_activo is not None:
        request.session["periodo_seleccionado"] = periodo_activo["codigo"]
    else:
        periodo_activo = periodos_disponibles[0]

    return {
        "periodo_activo": periodo_activo,
        "periodos_disponibles": periodos_disponibles,
    }
