from datetime import date

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from principal.models import (
    AsignacionMeta,
    Cargo,
    CartaOficinaPartes,
    CasoSocial,
    CatalogoMeta,
    Compromiso,
    Delegacion,
    Dirigencia,
    GestionSocial,
    Hito,
    JuntaVecinos,
    PerfilUsuario,
    SubtipoAtencion,
    Territorio,
    TipoAtencion,
    TipoOrganizacion,
    Trimestre,
    Vecino,
)
from principal.views_organizaciones import asegurar_tipos_organizacion


def _primera_opcion(modelo, campo, respaldo):
    choices = modelo._meta.get_field(campo).choices
    return choices[0][0] if choices else respaldo


class Command(BaseCommand):
    help = "Carga datos mínimos realistas e idempotentes para pruebas y demostración del SGR."

    def handle(self, *args, **options):
        hoy = timezone.localdate()

        # 1. Roles base
        g_func, _ = Group.objects.get_or_create(name="Funcionario")
        g_sup, _ = Group.objects.get_or_create(name="Supervisor")
        g_admin, _ = Group.objects.get_or_create(name="Administrador")

        # 2. Delegaciones y territorios
        del_antena, _ = Delegacion.objects.get_or_create(nombre="Delegación Antena - La Florida", defaults={"activa": True})
        del_comp, _ = Delegacion.objects.get_or_create(nombre="Delegación Las Compañías", defaults={"activa": True})

        t_antena, _ = Territorio.objects.get_or_create(delegacion=del_antena, nombre="Antena", defaults={"activo": True})
        t_alfalfares, _ = Territorio.objects.get_or_create(delegacion=del_antena, nombre="Alfalfares", defaults={"activo": True})
        t_florida, _ = Territorio.objects.get_or_create(delegacion=del_antena, nombre="La Florida", defaults={"activo": True})
        t_comp, _ = Territorio.objects.get_or_create(delegacion=del_comp, nombre="Las Compañías", defaults={"activo": True})

        # 3. Cargos
        c_gestor, _ = Cargo.objects.get_or_create(
            nombre="Gestor Territorial",
            defaults={"es_area_social": False, "meta_minima_porcentaje": 80, "activo": True},
        )
        c_social, _ = Cargo.objects.get_or_create(
            nombre="Trabajador Social",
            defaults={"es_area_social": True, "meta_minima_porcentaje": 80, "activo": True},
        )
        c_sup, _ = Cargo.objects.get_or_create(
            nombre="Supervisor Territorial",
            defaults={"es_area_social": False, "meta_minima_porcentaje": 80, "activo": True},
        )

        # 4. Usuarios demo (clave de prueba local)
        def crear_usr(username, first, last, email, grupo, deleg, cargo, clave_temp=False):
            u, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": email, "is_active": True},
            )
            if created:
                u.set_password("DemoSGR2026!")
                u.save()
            u.groups.set([grupo])
            PerfilUsuario.objects.update_or_create(
                usuario=u,
                defaults={"delegacion": deleg, "cargo": cargo, "debe_cambiar_clave": clave_temp},
            )
            return u

        crear_usr("admin_demo", "Administrador", "SGR", "admin.demo@laserena.cl", g_admin, del_antena, c_sup)
        sup_antena = crear_usr("sup_antena", "Camila", "Contreras", "sup.antena@laserena.cl", g_sup, del_antena, c_sup)
        gestor = crear_usr("gestor_demo", "Matías", "Rojas", "gestor.demo@laserena.cl", g_func, del_antena, c_gestor)
        social = crear_usr("social_demo", "Valentina", "Pizarro", "social.demo@laserena.cl", g_func, del_antena, c_social)
        crear_usr("nuevo_temporal", "Diego", "Araya", "temporal.demo@laserena.cl", g_func, del_comp, c_gestor, clave_temp=True)

        # 5. Trimestres (abierto y cerrado)
        trim_q4, _ = Trimestre.objects.get_or_create(
            codigo="2026-Q4",
            defaults={
                "nombre": "Trimestre Oct - Dic 2026",
                "fecha_inicio": date(2026, 10, 1),
                "fecha_termino": date(2026, 12, 31),
                "dias_computables": 65,
                "tope_maximo_porcentaje": 120,
                "cerrado": False,
            },
        )
        Trimestre.objects.get_or_create(
            codigo="2026-Q3",
            defaults={
                "nombre": "Trimestre Jul - Sep 2026",
                "fecha_inicio": date(2026, 7, 1),
                "fecha_termino": date(2026, 9, 30),
                "dias_computables": 64,
                "tope_maximo_porcentaje": 120,
                "cerrado": True,
            },
        )

        # 6. Tipos y subtipos de atención (incluye coordinación sin puntaje)
        area_def = _primera_opcion(TipoAtencion, "area", "Territorial")
        ta_terr, _ = TipoAtencion.objects.get_or_create(nombre="Gestión Territorial", defaults={"area": area_def, "activo": True})
        ta_soc, _ = TipoAtencion.objects.get_or_create(nombre="Atención Social", defaults={"area": area_def, "activo": True})

        SubtipoAtencion.objects.get_or_create(
            tipo_atencion=ta_terr, nombre="Atención de público en sede", defaults={"es_coordinacion": False, "activo": True}
        )
        SubtipoAtencion.objects.get_or_create(
            tipo_atencion=ta_terr, nombre="Terreno / Operativo comunitario", defaults={"es_coordinacion": False, "activo": True}
        )
        SubtipoAtencion.objects.get_or_create(
            tipo_atencion=ta_terr, nombre="Coordinación interna / Envío de correos", defaults={"es_coordinacion": True, "activo": True}
        )
        sub_soc, _ = SubtipoAtencion.objects.get_or_create(
            tipo_atencion=ta_soc, nombre="Orientación y derivación social", defaults={"es_coordinacion": False, "activo": True}
        )

        # 7. Organizaciones y Juntas de Vecinos (datos reales de planilla)
        asegurar_tipos_organizacion()
        tipo_jjvv = TipoOrganizacion.objects.get(nombre="Junta de Vecinos")
        tipo_func = TipoOrganizacion.objects.get(nombre="Organización Comunitaria Funcional")
        tipo_cam = TipoOrganizacion.objects.get(nombre="Club de Adulto Mayor")

        org1, _ = JuntaVecinos.objects.get_or_create(
            territorio=t_alfalfares,
            nombre="AGRUPACION SERENA-MENTE MUJERES",
            defaults={
                "tipo": tipo_func,
                "direccion": "PARCELA 36, SITIO 88, ALFALFARES",
                "socios_activos": 15,
                "fecha_constitucion": date(2026, 5, 30),
                "personalidad_juridica": "4006",
                "fecha_inscripcion_registro": date(2026, 6, 8),
                "activa": True,
            },
        )
        org2, _ = JuntaVecinos.objects.get_or_create(
            territorio=t_antena,
            nombre="AGRUPACION DE VECINOS DE BENJAMIN VICUÑA MACKENNA",
            defaults={
                "tipo": tipo_jjvv,
                "direccion": "BENJAMIN VICUÑA MACKENNA",
                "socios_activos": 63,
                "fecha_constitucion": date(2004, 2, 11),
                "personalidad_juridica": "1110",
                "fecha_inscripcion_registro": date(2004, 2, 12),
                "registro_directorio_numero": "7150",
                "activa": True,
            },
        )
        JuntaVecinos.objects.get_or_create(
            territorio=t_florida,
            nombre="ADULTO MAYOR REALIZANDO SUEÑOS LA SERENA",
            defaults={
                "tipo": tipo_cam,
                "direccion": "ALFALFARES N°1293, LA SERENA",
                "socios_activos": 26,
                "fecha_constitucion": date(2018, 11, 30),
                "personalidad_juridica": "3118",
                "fecha_inscripcion_registro": date(2018, 12, 4),
                "registro_directorio_numero": "9547",
                "activa": True,
            },
        )

        # 8. Vecinos y dirigencias
        v1, _ = Vecino.objects.get_or_create(
            rut="12.458.963-1",
            defaults={"nombre_completo": "Rosa Morales Vega", "telefono": "+56981234567", "territorio": t_antena},
        )
        v2, _ = Vecino.objects.get_or_create(
            rut="16.321.654-K",
            defaults={"nombre_completo": "Jorge Castillo Tapia", "telefono": "+56976543210", "territorio": t_alfalfares},
        )
        Dirigencia.objects.get_or_create(
            vecino=v1,
            junta_vecinos=org2,
            cargo_dirigencia="Presidente",
            defaults={"fecha_inicio": date(2025, 3, 1), "vigente": True},
        )
        Dirigencia.objects.get_or_create(
            vecino=v2,
            junta_vecinos=org1,
            cargo_dirigencia="Socio",
            defaults={"fecha_inicio": date(2026, 6, 10), "vigente": True},
        )

        # 9. Hitos y Metas (Catálogo + Asignación por funcionario/trimestre)
        hito_estado = _primera_opcion(Hito, "estado", "En curso")
        Hito.objects.get_or_create(
            nombre="Operativo de Seguridad Vecinal Antena",
            territorio=t_antena,
            defaults={
                "descripcion": "Jornada de coordinación con JJVV y luminarias del sector.",
                "responsable": gestor,
                "fecha_comprometida": hoy,
                "estado": hito_estado,
            },
        )

        cm1, _ = CatalogoMeta.objects.get_or_create(
            codigo="META-TER-01",
            defaults={"nombre": "Atenciones territoriales resueltas", "cargo_sugerido": c_gestor, "activa": True},
        )
        cm2, _ = CatalogoMeta.objects.get_or_create(
            codigo="META-TER-02",
            defaults={"nombre": "Terrenos y reuniones con JJVV", "cargo_sugerido": c_gestor, "activa": True},
        )
        AsignacionMeta.objects.get_or_create(
            funcionario=gestor,
            trimestre=trim_q4,
            catalogo_meta=cm1,
            defaults={"cantidad_exigida": 20, "ponderacion": 60, "tope_cumplimiento": 120},
        )
        AsignacionMeta.objects.get_or_create(
            funcionario=gestor,
            trimestre=trim_q4,
            catalogo_meta=cm2,
            defaults={"cantidad_exigida": 10, "ponderacion": 40, "tope_cumplimiento": 120},
        )

        # 10. Ejemplos en Tubo de Seguimiento, Tubo de Cartas y Área Social
        Compromiso.objects.get_or_create(
            codigo="COM-DEMO-01",
            defaults={
                "titulo": "Reposición de luminaria pasaje Los Aromos",
                "descripcion": "Vecina reporta poste apagado frente a sede comunitaria.",
                "territorio": del_antena,
                "sector": t_antena,
                "vecino": v1,
                "responsable": gestor,
                "creado_por": gestor,
                "trimestre": trim_q4,
                "estado": "En proceso",
                "prioridad": "Alta",
                "area": "Gestión territorial",
                "solicitante": v1.nombre_completo,
                "fecha": hoy,
                "plazo": "5 días",
                "fecha_limite": hoy,
            },
        )
        CartaOficinaPartes.objects.get_or_create(
            numero_carta="OP-2026-045",
            defaults={
                "delegacion": del_antena,
                "trimestre": trim_q4,
                "fecha_ingreso": hoy,
                "para": "Alcaldesa",
                "vecino": v2,
                "rut_remitente": v2.rut,
                "remitente": v2.nombre_completo,
                "telefono": v2.telefono,
                "actividad_tema": "Solicitud de subvención para equipamiento sede comunitaria",
                "responsable": gestor,
                "creado_por": sup_antena,
                "estado": "En proceso",
            },
        )
        caso, _ = CasoSocial.objects.get_or_create(
            rut=v1.rut,
            defaults={
                "vecino": v1,
                "delegacion": del_antena,
                "usuario_nombre": v1.nombre_completo,
                "telefono": v1.telefono,
                "funcionario": social,
            },
        )
        if not caso.gestiones.exists():
            GestionSocial.objects.create(
                caso=caso,
                tipo_atencion=ta_soc,
                subtipo_atencion=sub_soc,
                sub_atencion="Orientación Social",
                accion_realizada="Visita domiciliaria",
                fecha_ejecucion=hoy,
                detalle_accion="Evaluación socioeconómica inicial y orientación de subsidio.",
                evidencia_codigo=f"{caso.codigo}-G1",
                validacion="Pendiente",
            )

        self.stdout.write(self.style.SUCCESS("Datos demo cargados correctamente (clave común: DemoSGR2026!)."))
        self.stdout.write("  - Administrador : admin_demo")
        self.stdout.write("  - Supervisor    : sup_antena")
        self.stdout.write("  - Funcionario   : gestor_demo")
        self.stdout.write("  - Área Social   : social_demo")
        self.stdout.write("  - Clave temporal: nuevo_temporal (forzará cambio de clave al entrar)")