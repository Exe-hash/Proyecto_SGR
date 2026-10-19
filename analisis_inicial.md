# Sistema de Gestión de Resultados (SGR): análisis inicial

Estado: análisis preliminar a partir de la guía académica, versión 1.0 del 31 de agosto de 2026. Este documento no acredita que las funcionalidades estén implementadas, probadas ni aprobadas por el docente.

## 1. Propósito

Construir una aplicación web responsiva para centralizar el registro, seguimiento, validación y medición de la gestión de funcionarios y delegaciones. Debe conservar información en una base de datos, aplicar reglas verificables y contar con controles básicos de seguridad.

El caso es académico y solo se deben utilizar datos ficticios o anonimizados. No cargar datos reales de ciudadanos ni funcionarios.

## 2. Flujo principal

1. El administrador configura delegaciones, usuarios, cargos, catálogos, períodos, metas y ponderaciones.
2. Un funcionario autorizado registra una actividad y el sistema le asigna un código único e inmutable.
3. El funcionario vincula una evidencia permitida con la actividad.
4. Un verificador autorizado aprueba, rechaza o solicita corrección, dejando constancia de su decisión.
5. La actividad aprobada aporta una sola vez al avance correspondiente; una rechazada no aporta.
6. El funcionario y la jefatura consultan los indicadores y el detalle que los origina dentro de su ámbito autorizado.

En paralelo, la agenda colectiva registra compromisos futuros, responsables, plazos, estados e historial. Cuando un ítem lo configure, un compromiso validado puede alimentar la medición una sola vez (RF-020).

## 3. Alcance mínimo recomendado por la guía

- Autenticación y autorización por rol y delegación.
- Administración básica de usuarios, cargos, catálogos, períodos, metas y ponderaciones.
- Actividades con identificador único, evidencia y flujo de validación.
- Agenda colectiva con responsables, estados, plazos e historial.
- Avance, cumplimiento ponderado, meta esperada al día y semáforo.
- Panel personal y resumen de delegación con filtros y detalle.
- Informe o exportación básica y auditoría de operaciones críticas.

Este es el MVP recomendado en la sección 13.2, no una reducción aprobada de los requisitos formales. La guía indica que P2 y P3 dependen del tiempo, la complejidad y la definición docente. Sus inconsistencias de prioridad deben aclararse.

Fuera del alcance inicial indicado por la guía: presupuesto, contabilidad y remuneraciones; evaluación formal de desempeño laboral o decisiones de recursos humanos sin validación institucional adicional; atención ciudadana multicanal completa, firma electrónica o tramitación documental integral; e integraciones municipales no identificadas en la presentación.

## 4. Actores principales

| Actor | Responsabilidad descrita en la guía |
| --- | --- |
| Administrador | Configura organización, usuarios, catálogos, períodos, metas y permisos. |
| Coordinador | Supervisa la operación y los indicadores, y coordina criterios y mejoras. |
| Delegado o jefatura | Consulta su delegación y asigna o revisa compromisos. |
| Funcionario | Registra actividades, compromisos, avances y evidencias. |
| Verificador | Revisa evidencias y registra sus decisiones. |
| Usuario de consulta | Consulta tableros e informes autorizados sin modificar datos operativos. |

Los permisos deben comprobarse en el servidor para cada operación y ámbito. La configuración detallada de permisos por actor queda por diseñar y validar.

## 5. Reglas académicas iniciales

| Regla | Línea base de la guía |
| --- | --- |
| Período | Inicio y término configurables; se calculan los días computables. |
| Meta | Para un ítem cuantitativo, debe ser mayor que cero. |
| Cumplimiento | Avance aprobado / meta del período × 100. |
| Tope | 150 % inicial, configurable y visible en la configuración. |
| Ponderación | Ponderador × cumplimiento / 100; la suma aplicable de ponderadores es 100 %, salvo excepción formal configurada. |
| Meta esperada al día | Días computables transcurridos / días computables totales × 100. |
| Semáforo | Verde si el avance es igual o superior al esperado; ámbar si alcanza al menos 60 % del esperado y es menor que este; rojo si es inferior al 60 % del esperado. Umbrales sujetos a validación. |
| Umbral colectivo | 80 % propuesto como valor inicial configurable. |
| Evidencias | Solo una actividad con validación aprobada aporta al avance; una rechazada conserva su motivo e historial. |
| Ajustes | Bonificaciones y penalizaciones requieren reglas parametrizadas y aprobadas; no fijar valores arbitrarios. |
| Historial | La configuración vigente de períodos cerrados debe conservarse; la reapertura requiere autorización y auditoría. |

Ejemplo didáctico: una meta de 20 actividades, con 8 aprobadas, tiene 40 % de cumplimiento. Si su ponderación es 40 %, aporta 16 puntos porcentuales. Si ya transcurrió la mitad de los días computables, el avance esperado es 50 %; el umbral ámbar es 30 % y el semáforo sería ámbar. Es un ejemplo ficticio, sujeto a la definición de días computables y a las reglas aplicables.

## 6. Propuesta técnica inicial

- Python y Django para el backend, modelos, formularios, autenticación y validación.
- Plantillas HTML, CSS y JavaScript para una interfaz web adaptable.
- Base de datos relacional mediante el ORM y migraciones de Django. El motor definitivo está pendiente de definición.
- Archivos de evidencia almacenados de forma controlada, con revisión de permisos del lado del servidor.
- Pruebas de reglas, integración, autorización y flujos principales.

La guía permite proponer el stack, sujeto a aprobación docente. Esta propuesta debe validarse; no presupone que exista una API separada, un servidor de despliegue ni una integración institucional.

## 7. Entidades preliminares

Delegación, funcionario/usuario, cargo y función, período, meta e ítem, actividad, compromiso, evidencia, validación, indicador y auditoría. Estas son entidades conceptuales de la guía; sus relaciones, campos definitivos y restricciones se diseñarán antes de crear las tablas.

## 8. Ruta de trabajo

1. **Sprint 0: descubrimiento y diseño.** Refinar el alcance y backlog; documentar dudas; diseñar prototipo, arquitectura, modelo de datos, repositorio y plan de pruebas.
2. **Sprint 1: acceso y configuración.** Autenticación, roles, delegaciones, usuarios, cargos, catálogos, períodos y metas.
3. **Sprint 2: operación.** Actividades, códigos, evidencias, validaciones y agenda colectiva.
4. **Sprint 3: medición y consulta.** Cálculos, semáforo, paneles, filtros e informes.
5. **Sprint 4: calidad y entrega.** Pruebas, seguridad, correcciones, despliegue, manuales y demostración.

La planificación y los plazos se deben adaptar a las fechas y criterios docentes.

## 9. Trazabilidad inicial por completar

La matriz final debe contener historia de usuario, requisito, tarea o commit, caso de prueba, resultado, responsable y enlace a la evidencia. Una historia no se considera terminada sin trazabilidad demostrable. Los ejemplos siguientes son un punto de partida; no son evidencia de implementación.

| Historia | Requisito relacionado | Resultado que debe poder demostrarse | Estado |
| --- | --- | --- | --- |
| HU-01 Registro de actividades | RF-009, RF-010, RF-014, RF-022 | Se guarda una actividad válida y aporta una sola vez tras su aprobación. | Pendiente |
| HU-09 Evidencia fotográfica | RF-012, RNF-017 | Se vincula un archivo permitido y se rechaza una carga inválida. | Pendiente |
| HU-11 Validación | RF-013, RF-014, RF-036 | Se registra la decisión; un rechazo no aporta al avance. | Pendiente |
| HU-13 Estados de compromisos | RF-018, RF-036 | Cada cambio conserva estado anterior y nuevo, autor, fecha y observación. | Pendiente |
| HU-16 Semáforo | RF-026, RF-027 | Se presenta el color conforme a la regla vigente. | Pendiente |
| HU-23 Trabajo colaborativo | RF-034, RNF-003 | Dos usuarios pueden trabajar sin pérdida ni sobrescritura silenciosa. | Pendiente |
| HU-26 Usuarios y roles | RF-001, RF-002, RNF-004, RNF-005 | Cada usuario accede únicamente a su ámbito autorizado. | Pendiente |
| HU-30 Auditoría | RF-036, RNF-008 | Un usuario autorizado consulta eventos críticos protegidos. | Pendiente |

## 10. Preguntas y decisiones pendientes

- ¿Existe otra rúbrica, instrucción docente, fecha de entrega o condición de evaluación que complemente esta guía?
- ¿El docente aprueba Python, Django y la arquitectura web propuesta? ¿Existe un motor de base de datos o entorno de despliegue exigido?
- ¿Cómo se definen los días computables, incluidos fecha inicial, fecha final, fines de semana y feriados?
- ¿Qué formatos y tamaños de evidencia se admitirán, y cómo se aplicarán antivirus, retención y eliminación segura según RNF-017?
- ¿Qué operaciones concretas corresponden a cada rol y cómo se asigna el alcance por delegación?
- ¿Qué reglas, plazos, autorizaciones y versión de parámetros rigen al cerrar o reabrir un período?
- RF-015 clasifica como alta la atención social con hasta tres gestiones, mientras HU-03 aparece como P2 y no figura expresamente en el MVP. La guía establece que, ante contradicción, prevalece el requisito formal y se registra la decisión: consultar la priorización de implementación con el docente sin darla por resuelta.
- RF-029 clasifica como alta la vista de delegación, mientras HU-08 es P2. El MVP también incluye resumen de delegación: conservar esa necesidad y consultar el detalle del alcance.
- Definir cómo se medirá la disponibilidad, el rendimiento, el respaldo y la recuperación; los valores propuestos en la guía están sujetos a validación.

## 11. Entregables señalados en la guía

Repositorio; análisis y backlog; diseño; aplicación ejecutable y datos ficticios; plan y resultados de pruebas; manuales y decisiones técnicas; demostración; y matriz de trazabilidad. Cada integrante debe poder demostrar su aporte.
