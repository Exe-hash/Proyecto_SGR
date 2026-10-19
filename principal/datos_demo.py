"""Datos ficticios utilizados únicamente para presentar las pantallas."""

METAS = [
    {"id": "01", "nombre": "Atención de usuario telefónica y presencial", "ponderacion": 10, "avance": 11, "meta": 45, "resultado": "2,4", "barra": 24},
    {"id": "02", "nombre": "Visitas, reuniones con organizaciones", "ponderacion": 15, "avance": 3, "meta": 24, "resultado": "1,9", "barra": 13},
    {"id": "03", "nombre": "Conformación de directivas definitivas", "ponderacion": 25, "avance": 0, "meta": 2, "resultado": "0,0", "barra": 0},
    {"id": "04", "nombre": "Gestión de talleres y actividades", "ponderacion": 15, "avance": 6, "meta": 24, "resultado": "3,8", "barra": 25},
    {"id": "05", "nombre": "Emergencia", "ponderacion": 5, "avance": 8, "meta": 8, "resultado": "5,0", "barra": 100},
]

COMPROMISOS = [
    {"codigo": "COM1762", "titulo": "Solicitud de iluminación en final de calle", "territorio": "Latorre", "responsable": "Andrea Muñoz", "estado": "Ingresado", "plazo": "Hoy", "area": "Alumbrado público", "solicitante": "Vecina de ejemplo", "fecha": "2026-10-19"},
    {"codigo": "COM1761", "titulo": "Visita a organización comunitaria", "territorio": "Latorre", "responsable": "María Rojas", "estado": "Pendiente", "plazo": "Mañana", "area": "Apoyo territorial", "solicitante": "Organización de ejemplo", "fecha": "2026-10-20"},
    {"codigo": "COM1758", "titulo": "Reunión por problemas de vehículos mal estacionados", "territorio": "Toqui", "responsable": "Luis Molina", "estado": "Pendiente", "plazo": "Mañana", "area": "Tránsito", "solicitante": "Vecino de ejemplo", "fecha": "2026-10-20"},
    {"codigo": "COM1757", "titulo": "Evaluación y retiro de escombros", "territorio": "Latorre", "responsable": "Andrea Muñoz", "estado": "En proceso", "plazo": "Vence 23/10", "area": "Aseo y ornato", "solicitante": "Organización de ejemplo", "fecha": "2026-10-23"},
    {"codigo": "COM1755", "titulo": "Taller de alfabetización digital", "territorio": "Latorre", "responsable": "Carla Soto", "estado": "Realizado", "plazo": "Hoy", "area": "Apoyo territorial", "solicitante": "Organización de ejemplo", "fecha": "2026-10-19"},
    {"codigo": "COM1752", "titulo": "Solicitud de apoyo para mantención de un espacio público", "territorio": "Toqui", "responsable": "Andrea Muñoz", "estado": "Realizado", "plazo": "Mañana", "area": "Aseo y ornato", "solicitante": "Vecino de ejemplo", "fecha": "2026-10-20"},
]

EVIDENCIAS = [
    {"fecha": "17/10/2026", "codigo": "COM1762", "titulo": "Poda y retiro de ramas en sector Uruguay", "estado": "Aprobada", "clase": "aprobada", "observacion": "Evidencia válida, cumple con lo requerido"},
    {"fecha": "15/10/2026", "codigo": "COM1760", "titulo": "Taller de alfabetización digital", "estado": "Aprobada", "clase": "aprobada", "observacion": "Actividad registrada con éxito"},
    {"fecha": "12/10/2026", "codigo": "COM1758", "titulo": "Reunión por problemas de vehículos", "estado": "Corregir", "clase": "corregir", "observacion": "Falta adjuntar fotografía de asistencia"},
    {"fecha": "08/10/2026", "codigo": "COM1754", "titulo": "Solicitud de iluminación", "estado": "Aprobada", "clase": "aprobada", "observacion": "Revisado por coordinación"},
    {"fecha": "05/10/2026", "codigo": "COM1750", "titulo": "Emergencia por inundación", "estado": "Rechazada", "clase": "rechazada", "observacion": "La fotografía no corresponde a la fecha señalada"},
]

EQUIPO = [
    {"iniciales": "DR", "nombre": "Daniela Rojas", "cargo": "Gestora social", "estado": "Óptimo", "clase": "aprobada", "porcentaje": "116,9", "barra": 100},
    {"iniciales": "AV", "nombre": "Andrés Vega", "cargo": "Gestor social", "estado": "Riesgo", "clase": "corregir", "porcentaje": "57,2", "barra": 57},
    {"iniciales": "LP", "nombre": "Lucía Pérez", "cargo": "Territorial", "estado": "Crítico", "clase": "rechazada", "porcentaje": "15,5", "barra": 16},
    {"iniciales": "AM", "nombre": "Andrea Muñoz", "cargo": "Territorial", "estado": "Riesgo", "clase": "corregir", "porcentaje": "49,4", "barra": 49},
    {"iniciales": "FS", "nombre": "Felipe Salas", "cargo": "Apoyo administrativo", "estado": "Crítico", "clase": "rechazada", "porcentaje": "30,3", "barra": 30},
]
