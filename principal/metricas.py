from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q

from .models import (
    AjusteDesempeno,
    AsignacionMeta,
    Ausencia,
    CartaOficinaPartes,
    Compromiso,
    Evidencia,
    GestionSocial,
    Meta,
    Trimestre,
)
from .reglas import es_registro_aprobado

MESES_ES = (
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
)


def _meses_en_rango(inicio: date, fin: date) -> list[tuple[int, int, str]]:
    """Devuelve lista ordenada de (año, mes, etiqueta) dentro del rango."""
    meses = []
    anio, mes = inicio.year, inicio.month
    while (anio, mes) <= (fin.year, fin.month):
        meses.append((anio, mes, f"{MESES_ES[mes]} {anio}"))
        if mes == 12:
            anio += 1
            mes = 1
        else:
            mes += 1
    return meses


def resolver_trimestre_periodo(inicio: date, fin: date) -> Trimestre | None:
    """Busca el Trimestre de BD que coincide o se solapa con el rango seleccionado."""
    exacto = Trimestre.objects.filter(fecha_inicio=inicio, fecha_termino=fin).first()
    if exacto:
        return exacto
    return (
        Trimestre.objects.filter(fecha_inicio__lte=fin, fecha_termino__gte=inicio)
        .order_by("-fecha_inicio")
        .first()
    )


def clasificar_semaforo(porcentaje: float, meta_minima: int = 80) -> dict:
    """Devuelve etiqueta y clase Bootstrap del semáforo según la meta mínima del cargo."""
    umbral_riesgo = max(40, round(meta_minima * 0.65))
    if porcentaje >= meta_minima:
        return {"estado": "Óptimo", "badge": "bg-success", "bar": "bg-success", "color": "#198754"}
    if porcentaje >= umbral_riesgo:
        return {"estado": "En riesgo", "badge": "bg-warning text-dark", "bar": "bg-warning", "color": "#ffc107"}
    return {"estado": "Crítico", "badge": "bg-danger", "bar": "bg-danger", "color": "#dc3545"}


def calcular_resumen_funcionario(usuario, inicio_periodo: date, fin_periodo: date) -> dict:
    """
    Calcula el desempeño completo de un funcionario en el período:
    - Solo contabiliza registros aprobados con puntaje_valido == 1.
    - Ajusta las metas exigidas según días de ausencia informados por el Delegado.
    - Aplica tope máximo de 120% por meta y global.
    - Suma felicitaciones únicamente si tienen archivo_respaldo y resta reclamos.
    - Entrega datasets listos para los gráficos del Dashboard.
    """
    perfil = getattr(usuario, "perfil", None)
    meta_minima = perfil.cargo.meta_minima_porcentaje if (perfil and perfil.cargo) else 80
    trimestre_obj = resolver_trimestre_periodo(inicio_periodo, fin_periodo)
    dias_computables = trimestre_obj.dias_computables if trimestre_obj else 63
    tope_global = trimestre_obj.tope_maximo_porcentaje if trimestre_obj else 120


    evidencias_qs = (
        Evidencia.objects.filter(
            funcionario=usuario,
            fecha_registro__range=(inicio_periodo, fin_periodo),
        )
        .select_related("subtipo_atencion", "vecino", "meta_relacionada", "asignacion_meta")
    )
    evidencias_lista = list(evidencias_qs)

    ev_aprobadas = sum(1 for e in evidencias_lista if es_registro_aprobado(e.estado))
    ev_puntaje_valido = sum(e.puntaje_valido for e in evidencias_lista)
    ev_revision = sum(
        1 for e in evidencias_lista
        if e.estado in ("Pendiente", "En revisión", "Solicitud de más antecedentes")
    )
    ev_rechazadas = sum(1 for e in evidencias_lista if e.estado == "Rechazada")

    gestiones_qs = (
        GestionSocial.objects.filter(
            caso__funcionario=usuario,
        )
        .filter(
            Q(fecha_ejecucion__range=(inicio_periodo, fin_periodo))
            | Q(fecha_ejecucion__isnull=True, fecha_registro__date__range=(inicio_periodo, fin_periodo))
        )
        .select_related("caso", "subtipo_atencion", "asignacion_meta")
    )
    gestiones_lista = list(gestiones_qs)


    if trimestre_obj:
        ausencias_qs = Ausencia.objects.filter(
            funcionario=usuario
        ).filter(
            Q(trimestre=trimestre_obj)
            | Q(fecha_inicio__lte=fin_periodo, fecha_termino__gte=inicio_periodo)
        ).distinct()
    else:
        ausencias_qs = Ausencia.objects.filter(
            funcionario=usuario,
            fecha_inicio__lte=fin_periodo,
            fecha_termino__gte=inicio_periodo,
        )
    ausencias_lista = list(ausencias_qs.order_by("-fecha_inicio"))
    dias_ausencia = sum(a.dias_descontados for a in ausencias_lista)
    dias_efectivos = max(1, dias_computables - dias_ausencia)
    factor_asistencia = min(1.0, dias_efectivos / dias_computables) if dias_computables > 0 else 1.0


    asignaciones_qs = AsignacionMeta.objects.filter(funcionario=usuario).select_related(
        "catalogo_meta", "trimestre"
    )
    if trimestre_obj:
        asig_trim = asignaciones_qs.filter(trimestre=trimestre_obj)
        if asig_trim.exists():
            asignaciones_qs = asig_trim

    asignaciones_lista = list(asignaciones_qs)
    metas_calculadas = []
    usa_asignaciones = len(asignaciones_lista) > 0

    if usa_asignaciones:
        for am in asignaciones_lista:
            avance_ev = sum(
                e.puntaje_valido for e in evidencias_lista if e.asignacion_meta_id == am.id
            )
            avance_soc = sum(
                g.puntaje_valido for g in gestiones_lista if g.asignacion_meta_id == am.id
            )
            avance_real = avance_ev + avance_soc

            if am.catalogo_meta.es_porcentual or dias_ausencia == 0:
                meta_ajustada = am.cantidad_exigida
            else:
                meta_ajustada = max(1, round(am.cantidad_exigida * factor_asistencia))

            tope = am.tope_cumplimiento or 120
            cumplimiento = (avance_real / meta_ajustada * 100) if meta_ajustada > 0 else 0
            cumplimiento = min(cumplimiento, tope)
            resultado = (am.ponderacion * cumplimiento) / 100

            metas_calculadas.append({
                "id": am.catalogo_meta.codigo,
                "nombre": am.catalogo_meta.nombre,
                "ponderacion": am.ponderacion,
                "avance": avance_real,
                "meta_original": am.cantidad_exigida,
                "meta": meta_ajustada,
                "ajustada_por_ausencia": meta_ajustada != am.cantidad_exigida,
                "cumplimiento": round(cumplimiento, 1),
                "barra": min(int(cumplimiento), 100),
                "resultado": round(resultado, 1),
                "tope": tope,
            })
    else:
        metas_db = (
            Meta.objects.filter(vigente=True, cargo=perfil.cargo)
            if (perfil and perfil.cargo)
            else Meta.objects.none()
        )
        for m in metas_db:
            avance_real = sum(
                e.puntaje_valido for e in evidencias_lista if e.meta_relacionada_id == m.id
            )
            meta_ajustada = (
                max(1, round(m.valor_objetivo * factor_asistencia))
                if dias_ausencia > 0 and m.valor_objetivo > 0
                else m.valor_objetivo
            )
            cumplimiento = (avance_real / meta_ajustada * 100) if meta_ajustada > 0 else 0
            cumplimiento = min(cumplimiento, 120)
            resultado = (m.ponderacion * cumplimiento) / 100

            metas_calculadas.append({
                "id": m.id,
                "nombre": m.nombre,
                "ponderacion": m.ponderacion,
                "avance": avance_real,
                "meta_original": m.valor_objetivo,
                "meta": meta_ajustada,
                "ajustada_por_ausencia": meta_ajustada != m.valor_objetivo,
                "cumplimiento": round(cumplimiento, 1),
                "barra": min(int(cumplimiento), 100),
                "resultado": round(resultado, 1),
                "tope": 120,
            })

    puntaje_metas = round(sum(item["resultado"] for item in metas_calculadas), 1)

    if not metas_calculadas and len(evidencias_lista) > 0:
        puntaje_metas = round(min(120.0, (ev_puntaje_valido / len(evidencias_lista)) * 100), 1)


    if trimestre_obj:
        ajustes_qs = AjusteDesempeno.objects.filter(funcionario=usuario).filter(
            Q(trimestre=trimestre_obj)
            | Q(fecha_registro__date__range=(inicio_periodo, fin_periodo))
        ).distinct()
    else:
        ajustes_qs = AjusteDesempeno.objects.filter(
            funcionario=usuario,
            fecha_registro__date__range=(inicio_periodo, fin_periodo),
        )
    ajustes_lista = list(ajustes_qs.select_related("registrado_por").order_by("-fecha_registro"))

    felicitaciones_validas = [
        a for a in ajustes_lista if a.tipo == "Felicitación" and bool(a.archivo_respaldo)
    ]
    felicitaciones_sin_respaldo = [
        a for a in ajustes_lista if a.tipo == "Felicitación" and not a.archivo_respaldo
    ]
    reclamos = [a for a in ajustes_lista if a.tipo == "Penalización"]

    bono_felicitaciones = round(sum(abs(float(a.porcentaje_ajuste)) for a in felicitaciones_validas), 2)
    penalizacion_reclamos = round(sum(-abs(float(a.porcentaje_ajuste)) for a in reclamos), 2)

    porcentaje_final = round(
        max(0.0, min(float(tope_global), puntaje_metas + bono_felicitaciones + penalizacion_reclamos)),
        1,
    )
    semaforo = clasificar_semaforo(porcentaje_final, meta_minima=meta_minima)


    compromisos_qs = Compromiso.objects.filter(
        responsable=usuario,
        fecha__range=(inicio_periodo, fin_periodo),
    )
    comp_estados = {
        "Pendiente": compromisos_qs.filter(estado="Pendiente").count(),
        "En proceso": compromisos_qs.filter(estado="En proceso").count(),
        "Completado": compromisos_qs.filter(estado="Completado").count(),
        "Rechazado": compromisos_qs.filter(estado="Rechazado").count(),
    }
    compromisos_vencer = (
        compromisos_qs.exclude(estado__in=["Completado", "Rechazado"])
        .select_related("territorio")
        .order_by("fecha_limite", "fecha")[:6]
    )


    meses = _meses_en_rango(inicio_periodo, fin_periodo)
    tendencia_labels = []
    tendencia_registradas = []
    tendencia_aprobadas = []
    for anio, mes, etiqueta in meses:
        evs_mes = [
            e for e in evidencias_lista
            if e.fecha_registro.year == anio and e.fecha_registro.month == mes
        ]
        tendencia_labels.append(etiqueta)
        tendencia_registradas.append(len(evs_mes))
        tendencia_aprobadas.append(sum(e.puntaje_valido for e in evs_mes))

    charts = {
        "metas": {
            "labels": [m["nombre"][:28] for m in metas_calculadas],
            "values": [m["cumplimiento"] for m in metas_calculadas],
        },
        "compromisos": {
            "labels": list(comp_estados.keys()),
            "values": list(comp_estados.values()),
        },
        "tendencia": {
            "labels": tendencia_labels,
            "registradas": tendencia_registradas,
            "aprobadas": tendencia_aprobadas,
        },
    }

    return {
        "trimestre_obj": trimestre_obj,
        "meta_minima": meta_minima,
        "tope_global": tope_global,
        "dias_computables": dias_computables,
        "dias_ausencia": dias_ausencia,
        "dias_efectivos": dias_efectivos,
        "ausencias": ausencias_lista,
        "ev_totales": len(evidencias_lista),
        "ev_aprobadas": ev_aprobadas,
        "ev_puntaje_valido": ev_puntaje_valido,
        "ev_revision": ev_revision,
        "ev_rechazadas": ev_rechazadas,
        "gestiones_totales": len(gestiones_lista),
        "gestiones_validas": sum(g.puntaje_valido for g in gestiones_lista),
        "metas": metas_calculadas,
        "usa_asignaciones": usa_asignaciones,
        "puntaje_metas": puntaje_metas,
        "ajustes": ajustes_lista,
        "cant_felicitaciones": len(felicitaciones_validas),
        "cant_felicitaciones_sin_respaldo": len(felicitaciones_sin_respaldo),
        "bono_felicitaciones": bono_felicitaciones,
        "cant_reclamos": len(reclamos),
        "penalizacion_reclamos": penalizacion_reclamos,
        "porcentaje_avance": porcentaje_final,
        "barra_avance": min(int(porcentaje_final), 100),
        "semaforo": semaforo,
        "compromisos_vencer": compromisos_vencer,
        "comp_estados": comp_estados,
        "charts": charts,
    }


def calcular_resumen_equipo(funcionarios_qs, inicio_periodo: date, fin_periodo: date, delegacion=None) -> dict:
    """Consolida semáforo por funcionario, carga de trabajo, compromisos y tendencias de la delegación."""
    equipo_calculado = []
    total_aprobadas = 0
    total_revision = 0
    total_general = 0
    total_puntaje_valido = 0

    for f in funcionarios_qs:
        res = calcular_resumen_funcionario(f, inicio_periodo, fin_periodo)
        total_aprobadas += res["ev_aprobadas"]
        total_revision += res["ev_revision"]
        total_general += res["ev_totales"]
        total_puntaje_valido += res["ev_puntaje_valido"]

        iniciales = f"{f.first_name[:1]}{f.last_name[:1]}" if f.first_name else (f.username[:2] or "F")
        perfil = getattr(f, "perfil", None)
        equipo_calculado.append({
            "id": f.id,
            "nombre": f.get_full_name().strip() or f.username,
            "iniciales": iniciales.upper(),
            "cargo": perfil.cargo.nombre if (perfil and perfil.cargo) else "Sin cargo",
            "delegacion": perfil.delegacion.nombre if (perfil and perfil.delegacion) else "Sin delegación",
            "porcentaje": res["porcentaje_avance"],
            "barra": res["barra_avance"],
            "meta_minima": res["meta_minima"],
            "estado": res["semaforo"]["estado"],
            "badge": res["semaforo"]["badge"],
            "bar": res["semaforo"]["bar"],
            "color": res["semaforo"]["color"],
            "ev_totales": res["ev_totales"],
            "ev_aprobadas": res["ev_aprobadas"],
            "ev_puntaje_valido": res["ev_puntaje_valido"],
            "dias_ausencia": res["dias_ausencia"],
            "bono_felicitaciones": res["bono_felicitaciones"],
            "penalizacion_reclamos": res["penalizacion_reclamos"],
            "carga_total": res["ev_totales"] + res["gestiones_totales"],
        })

    avance_global = (
        round(sum(p["porcentaje"] for p in equipo_calculado) / len(equipo_calculado), 1)
        if equipo_calculado
        else 0.0
    )
    semaforo_global = clasificar_semaforo(avance_global, meta_minima=80)


    comp_qs = Compromiso.objects.filter(fecha__range=(inicio_periodo, fin_periodo))
    cartas_qs = CartaOficinaPartes.objects.filter(fecha_ingreso__range=(inicio_periodo, fin_periodo))
    ev_deleg_qs = Evidencia.objects.filter(fecha_registro__range=(inicio_periodo, fin_periodo))

    if delegacion:
        comp_qs = comp_qs.filter(territorio=delegacion)
        cartas_qs = cartas_qs.filter(delegacion=delegacion)
        ev_deleg_qs = ev_deleg_qs.filter(funcionario__perfil__delegacion=delegacion)

    comp_estados = {
        "Pendiente": comp_qs.filter(estado="Pendiente").count(),
        "En proceso": comp_qs.filter(estado="En proceso").count(),
        "Completado": comp_qs.filter(estado="Completado").count(),
        "Rechazado": comp_qs.filter(estado="Rechazado").count(),
    }


    ev_deleg_lista = list(ev_deleg_qs.select_related("subtipo_atencion", "vecino"))
    meses = _meses_en_rango(inicio_periodo, fin_periodo)
    tend_labels, tend_reg, tend_aprob = [], [], []
    for anio, mes, etiqueta in meses:
        evs_m = [e for e in ev_deleg_lista if e.fecha_registro.year == anio and e.fecha_registro.month == mes]
        tend_labels.append(etiqueta)
        tend_reg.append(len(evs_m))
        tend_aprob.append(sum(e.puntaje_valido for e in evs_m))

    charts = {
        "semaforo_equipo": {
            "labels": [p["nombre"][:22] for p in equipo_calculado],
            "values": [p["porcentaje"] for p in equipo_calculado],
            "colors": [p["color"] for p in equipo_calculado],
        },
        "carga_trabajo": {
            "labels": [p["nombre"][:22] for p in equipo_calculado],
            "registradas": [p["carga_total"] for p in equipo_calculado],
            "validas": [p["ev_puntaje_valido"] for p in equipo_calculado],
        },
        "compromisos": {
            "labels": list(comp_estados.keys()),
            "values": list(comp_estados.values()),
        },
        "tendencia": {
            "labels": tend_labels,
            "registradas": tend_reg,
            "aprobadas": tend_aprob,
        },
    }

    return {
        "equipo": equipo_calculado,
        "avance_global": avance_global,
        "barra_global": min(int(avance_global), 100),
        "semaforo_global": semaforo_global,
        "total_aprobadas": total_aprobadas,
        "total_puntaje_valido": total_puntaje_valido,
        "total_revision": total_revision,
        "total_general": total_general,
        "total_compromisos": sum(comp_estados.values()),
        "total_cartas": cartas_qs.count(),
        "comp_estados": comp_estados,
        "charts": charts,
    }


def enviar_notificacion_ajuste(ajuste: AjusteDesempeno) -> tuple[bool, str]:
    """
    Envía un correo formal al funcionario cuando el Supervisor le hace llegar
    una Felicitación o un Reclamo/Penalización recibido desde fuera del sistema.
    """
    destinatario = (ajuste.funcionario.email or "").strip()
    if not destinatario:
        return False, "El funcionario no tiene correo registrado; el ajuste quedó visible en su Panel."

    supervisor_nombre = ajuste.registrado_por.get_full_name().strip() or ajuste.registrado_por.username
    funcionario_nombre = ajuste.funcionario.get_full_name().strip() or ajuste.funcionario.username
    signo = "+" if float(ajuste.porcentaje_ajuste) >= 0 else ""

    asunto = f"[SGR] {ajuste.tipo} registrada en tu desempeño ({ajuste.trimestre.codigo})"
    cuerpo = (
        f"Hola {funcionario_nombre},\n\n"
        f"Tu jefatura ({supervisor_nombre}) ha registrado una {ajuste.tipo.lower()} recibida para tu gestión "
        f"en el período {ajuste.trimestre.nombre}.\n\n"
        f"- Tipo: {ajuste.tipo}\n"
        f"- Impacto en semáforo: {signo}{ajuste.porcentaje_ajuste}%\n"
        f"- Motivo / detalle: {ajuste.motivo}\n\n"
        f"Puedes revisar el detalle y su respaldo en tu Panel Operativo del SGR.\n\n"
        f"Sistema de Gestión de Resultados (SGR) · Ilustre Municipalidad de La Serena"
    )

    try:
        correo = EmailMessage(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )
        if ajuste.archivo_respaldo:
            with ajuste.archivo_respaldo.open("rb") as fh:
                correo.attach(ajuste.archivo_respaldo.name.split("/")[-1], fh.read())
        correo.send(fail_silently=False)
        return True, f"Se notificó por correo a {destinatario}."
    except Exception:
        return False, "El ajuste fue guardado, pero no se pudo enviar el correo (revisa configuración SMTP)."