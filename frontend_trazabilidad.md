# Frontend de demostración: relación con los requisitos

Estas pantallas presentan información ficticia y permiten revisar la estructura visual y algunas interacciones en el navegador. La relación de una pantalla con un requisito no significa que el requisito o la historia se encuentren cumplidos: todavía requieren backend, controles de acceso, datos persistentes y pruebas de aceptación.

| Vista | Referencias entregadas | Qué permite revisar | Pendiente para cumplimiento funcional |
| --- | --- | --- | --- |
| Inicio | Diseño de acceso | Formulario de inicio de sesión con usuarios de Django. | Completar cierre de sesión, permisos por rol y recuperación de contraseña. |
| Mi panel | RF-008, RF-028, RF-037, RF-026, RF-027, RF-025, RF-022, RF-023, RF-024; HU-06, HU-31, HU-16, HU-17, HU-07 | Ficha, indicadores, semáforo, evidencias, ajustes, metas y ejemplo de fórmula. | Cálculos reales, reglas versionadas, alertas, filtros y consulta de registros autorizados. |
| Registrar actividad | RF-008, RF-009, RF-010, RF-016, RF-017, RF-012; HU-01, HU-02, HU-09, HU-10 | Formulario, campos de compromiso y selección de fotografía. | Validación en servidor, persistencia, generación de código, creación de compromiso y almacenamiento seguro. |
| Agenda colectiva y detalle | RF-032, RF-019, RF-018, RF-035; HU-12, HU-13, HU-14, HU-15, HU-24 | Columnas, filtros, apertura del detalle, cambios temporales de estado y observaciones. | Persistencia y auditoría, transiciones autorizadas, fechas reales, reasignación, comunicación y permisos. |
| Resumen de equipo | RF-029, RF-026, RF-030, RF-027, RF-023, RF-031, RF-032, RF-033; HU-08, HU-17, HU-19, HU-21, HU-18, HU-20, HU-29 | Indicadores, búsqueda local y listado de ejemplo. | Cálculos reales, consolidación por delegación, detalle, filtros de servidor y exportación. |
| Revisión de evidencias | RF-032, RF-011, RF-013, RF-014, RF-036; HU-11 | Bandeja, selección de evidencia, observación y botones. | Consulta y archivo reales, permisos de verificación, decisiones persistentes y recálculo auditado. |
| Historial de evidencias | RF-013, RF-014, RF-032, RF-036; HU-11, HU-01, HU-29 | Búsqueda local y cuadro de detalle. | Consulta persistente, decisiones de verificación, historial auditado y permisos. |

## Decisiones de la vista previa

- Las cifras y las personas son ejemplos ficticios, no datos operacionales.
- El inicio de sesión utiliza usuarios de Django. Las vistas requieren una sesión iniciada, pero los permisos por rol y delegación aún están pendientes.
- Los filtros y los cambios de la agenda actúan únicamente en la página abierta; no escriben en la base de datos.
- Guardar, exportar y aprobar/rechazar muestran un aviso de función pendiente.
- La fotografía y el escudo se representan con elementos provisionales. Sustituirlos por los recursos originales autorizados si se proporcionan.
- En la maqueta de panel se observa avance 40 % frente a esperado 60 %. Según la regla académica de la guía, 40 es superior al 60 % de 60 (36), por lo que corresponde ámbar; la vista de ejemplo indica «En riesgo» en vez de «Crítico». Es una comprobación manual del ejemplo, no un cálculo real implementado.
- Los valores independientes de las maquetas son referencias visuales; no se han conectado para producir indicadores consistentes entre pantallas.
