import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from principal import urls as principal_urls
from principal import views
from principal.forms import AsignacionMetaForm
from principal.models import (
    AjusteDesempeno,
    AsignacionMeta,
    Ausencia,
    Cargo,
    CartaOficinaPartes,
    CatalogoMeta,
    Compromiso,
    Delegacion,
    Dirigencia,
    Evidencia,
    JuntaVecinos,
    PerfilUsuario,
    SubtipoAtencion,
    Territorio,
    TipoAtencion,
    TipoOrganizacion,
    Trimestre,
    Vecino,
)
from principal.reglas import (
    contar_actividades_del_dia,
    motivos_sin_puntaje_evidencia,
    validar_limite_diario,
    validar_registro_editable,
    validar_semana_abierta,
    vincular_vecino_a_organizacion,
)

# PNG válido de 1x1 píxel para pruebas de subida sin ensuciar media/
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _primera_opcion(modelo, campo, respaldo):
    choices = modelo._meta.get_field(campo).choices
    return choices[0][0] if choices else respaldo


def _url_de_vista(vista_func, *args):
    for pattern in principal_urls.urlpatterns:
        if getattr(pattern, "callback", None) == vista_func:
            return reverse(f"principal:{pattern.name}", args=args)
    raise AssertionError(f"No se encontró ruta registrada para {vista_func.__name__}")


def _archivo_png(nombre="evidencia.png"):
    return SimpleUploadedFile(nombre, PNG_1X1, content_type="image/png")


class BaseSGRTestCase(TestCase):
    """Prepara delegaciones, territorios, roles, usuarios y trimestre abierto para las suites."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_tmp = tempfile.mkdtemp(prefix="sgr_test_media_")
        cls._override_media = override_settings(MEDIA_ROOT=cls._media_tmp)
        cls._override_media.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override_media.disable()
        shutil.rmtree(cls._media_tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.hoy = timezone.localdate()

        self.g_func, _ = Group.objects.get_or_create(name="Funcionario")
        self.g_sup, _ = Group.objects.get_or_create(name="Supervisor")
        self.g_admin, _ = Group.objects.get_or_create(name="Administrador")

        self.deleg_a = Delegacion.objects.create(nombre="Delegación Antena", activa=True)
        self.deleg_b = Delegacion.objects.create(nombre="Delegación Las Compañías", activa=True)

        self.terr_a = Territorio.objects.create(delegacion=self.deleg_a, nombre="Antena", activo=True)
        self.terr_b = Territorio.objects.create(delegacion=self.deleg_b, nombre="Las Compañías", activo=True)

        self.cargo_gestor = Cargo.objects.create(
            nombre="Gestor Territorial",
            es_area_social=False,
            meta_minima_porcentaje=80,
            activo=True,
        )

        self.func1 = self._crear_usuario("11.111.111-1", "func1@laserena.cl", self.g_func, self.deleg_a)
        self.func2 = self._crear_usuario("22.222.222-2", "func2@laserena.cl", self.g_func, self.deleg_a)
        self.sup_a = self._crear_usuario("33.333.333-3", "sup_a@laserena.cl", self.g_sup, self.deleg_a)
        self.sup_b = self._crear_usuario("44.444.444-4", "sup_b@laserena.cl", self.g_sup, self.deleg_b)
        self.admin = self._crear_usuario("55.555.555-5", "admin@laserena.cl", self.g_admin, self.deleg_a)

        self.trimestre_abierto = Trimestre.objects.create(
            codigo="2026-Q4",
            nombre="Trimestre 4 2026",
            fecha_inicio=date(2026, 10, 1),
            fecha_termino=date(2026, 12, 31),
            dias_computables=60,
            tope_maximo_porcentaje=120,
            cerrado=False,
        )

    def _crear_usuario(self, username, email, grupo, delegacion, debe_cambiar_clave=False):
        user = User.objects.create_user(
            username=username,
            email=email,
            password="ClaveSegura123!",
            first_name="Usuario",
            last_name=username[:6],
        )
        user.groups.add(grupo)
        PerfilUsuario.objects.create(
            usuario=user,
            delegacion=delegacion,
            cargo=self.cargo_gestor,
            debe_cambiar_clave=debe_cambiar_clave,
        )
        return user


class ControlAccesoPorRolTests(TestCase):
    def setUp(self):
        self.funcionario = User.objects.create_user(
            username="funcionario_test",
            password="ClaveDePrueba123",
        )
        self.supervisor = User.objects.create_user(
            username="supervisor_test",
            password="ClaveDePrueba123",
        )
        self.administrador = User.objects.create_user(
            username="admin_test",
            password="ClaveDePrueba123",
        )

        grupo_funcionario, _ = Group.objects.get_or_create(name="Funcionario")
        grupo_supervisor, _ = Group.objects.get_or_create(name="Supervisor")
        grupo_administrador, _ = Group.objects.get_or_create(name="Administrador")

        self.funcionario.groups.add(grupo_funcionario)
        self.supervisor.groups.add(grupo_supervisor)
        self.administrador.groups.add(grupo_administrador)

    def test_landing_es_publico(self):
        respuesta = self.client.get(reverse("principal:landing"))
        self.assertEqual(respuesta.status_code, 200)

    def test_funcionario_accede_a_registro_de_actividades(self):
        self.client.force_login(self.funcionario)
        respuesta = self.client.get(reverse("principal:actividades"))
        self.assertEqual(respuesta.status_code, 200)

    def test_funcionario_no_accede_a_resumen_de_equipo_ni_asignar_tareas(self):
        self.client.force_login(self.funcionario)
        self.assertEqual(self.client.get(reverse("principal:equipo")).status_code, 403)
        self.assertEqual(self.client.get(reverse("principal:asignar_tareas")).status_code, 403)

    def test_supervisor_accede_a_equipo_verificacion_y_asignar_tareas(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("principal:equipo")).status_code, 200)
        self.assertEqual(self.client.get(reverse("principal:verificacion")).status_code, 200)
        self.assertEqual(self.client.get(reverse("principal:asignar_tareas")).status_code, 200)

    def test_usuario_sin_sesion_es_redirigido_al_inicio(self):
        respuesta = self.client.get(reverse("principal:panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("principal:inicio"), respuesta.url)


class SeguridadYPermisosTests(BaseSGRTestCase):
    def test_middleware_exige_cambio_de_contrasena_temporal(self):
        nuevo = self._crear_usuario(
            "66.666.666-6",
            "temp@laserena.cl",
            self.g_func,
            self.deleg_a,
            debe_cambiar_clave=True,
        )
        self.client.force_login(nuevo)
        resp = self.client.get(reverse("principal:panel"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("principal:cambiar_password_inicial"), resp.url)

    def test_funcionario_no_accede_a_administracion_ni_organizaciones(self):
        self.client.force_login(self.func1)
        self.assertEqual(self.client.get(reverse("principal:administracion")).status_code, 403)
        self.assertEqual(self.client.get(reverse("principal:organizaciones_lista")).status_code, 403)

    def test_proteccion_descarga_evidencia_por_delegacion(self):
        ev = Evidencia.objects.create(
            codigo="EVI-SEC-01",
            funcionario=self.func1,
            estado="Pendiente",
            fecha_registro=self.hoy,
            item_medir="Atención territorial",
            solicitud="Revisión luminaria",
            accion="Visita en terreno",
            contacto_nombre="María Pérez",
            contacto_telefono="+56912345678",
            fotografia=_archivo_png(),
        )
        url = reverse("principal:descargar_evidencia", args=[ev.id])

        # Supervisor de otra delegación debe recibir 403
        self.client.force_login(self.sup_b)
        self.assertEqual(self.client.get(url).status_code, 403)

        # Supervisor de la misma delegación sí accede
        self.client.force_login(self.sup_a)
        resp_ok = self.client.get(url)
        self.assertEqual(resp_ok.status_code, 200)
        resp_ok.close()


class ReglasNegocioYVerificacionTests(BaseSGRTestCase):
    def setUp(self):
        super().setUp()
        area_val = _primera_opcion(TipoAtencion, "area", "Territorial")
        self.tipo_at = TipoAtencion.objects.create(nombre="Gestión Comunitaria", area=area_val, activo=True)
        self.subtipo_normal = SubtipoAtencion.objects.create(
            tipo_atencion=self.tipo_at,
            nombre="Operativo en terreno",
            es_coordinacion=False,
            activo=True,
        )
        self.subtipo_coord = SubtipoAtencion.objects.create(
            tipo_atencion=self.tipo_at,
            nombre="Envío de correos / coordinación previa",
            es_coordinacion=True,
            activo=True,
        )

    def test_regla_1_usuario_delegado_no_contabiliza(self):
        ev = Evidencia.objects.create(
            codigo="EVI-R1",
            funcionario=self.func1,
            estado="Aprobada",
            fecha_registro=self.hoy,
            item_medir="Atención",
            solicitud="Solicitud interna del delegado",
            accion="Gestión interna",
            contacto_nombre="Delegado Municipal",
            contacto_telefono="+56911111111",
            subtipo_atencion=self.subtipo_normal,
            es_usuario_delegado=True,
        )
        self.assertEqual(ev.puntaje_valido, 0)
        self.assertTrue(motivos_sin_puntaje_evidencia(ev))

    def test_regla_2_sin_nombre_o_telefono_no_obtiene_puntaje(self):
        ev = Evidencia.objects.create(
            codigo="EVI-R2",
            funcionario=self.func1,
            estado="Aprobada",
            fecha_registro=self.hoy,
            item_medir="Atención",
            solicitud="Consulta sin fono",
            accion="Orientación entregada",
            contacto_nombre="Pedro Soto",
            contacto_telefono="",
            subtipo_atencion=self.subtipo_normal,
        )
        self.assertEqual(ev.puntaje_valido, 0)
        self.assertTrue(motivos_sin_puntaje_evidencia(ev))

    def test_regla_3_bloquea_octava_actividad_en_el_mismo_dia(self):
        for idx in range(7):
            Evidencia.objects.create(
                codigo=f"EVI-DIA-{idx}",
                funcionario=self.func1,
                estado="Pendiente",
                fecha_registro=self.hoy,
                item_medir="Atención",
                solicitud=f"Actividad {idx}",
                accion="Ejecutada",
                contacto_nombre="Vecino Prueba",
                contacto_telefono="+56922222222",
            )
        self.assertEqual(contar_actividades_del_dia(self.func1, self.hoy), 7)
        with self.assertRaises(ValidationError):
            validar_limite_diario(self.func1, self.hoy)

        self.client.force_login(self.func1)
        self.client.post(
            reverse("principal:actividades"),
            {
                "fecha": self.hoy.isoformat(),
                "actividad": "Octava actividad",
                "accion": "No debe guardarse",
                "contacto": "Vecino 8",
                "telefono": "+56988888888",
                "fotografia": _archivo_png("octava.png"),
            },
        )
        self.assertEqual(Evidencia.objects.filter(funcionario=self.func1, fecha_registro=self.hoy).count(), 7)

    def test_regla_4_cierre_semanal_abierto_lunes_y_bloqueado_martes(self):
        viernes_pasado = date(2026, 11, 20)
        lunes_siguiente = date(2026, 11, 23)
        martes_siguiente = date(2026, 11, 24)

        # El lunes aún se permite ingresar la semana anterior
        validar_semana_abierta(viernes_pasado, hoy=lunes_siguiente)

        # Desde el martes queda bloqueada la semana anterior
        with self.assertRaises(ValidationError):
            validar_semana_abierta(viernes_pasado, hoy=martes_siguiente)

    def test_regla_5_coordinacion_preparatoria_no_da_puntaje(self):
        ev = Evidencia.objects.create(
            codigo="EVI-R5",
            funcionario=self.func1,
            estado="Aprobada",
            fecha_registro=self.hoy,
            item_medir="Coordinación",
            solicitud="Coordinación de taller",
            accion="Envío de invitaciones por correo",
            contacto_nombre="Ana Rojas",
            contacto_telefono="+56933333333",
            subtipo_atencion=self.subtipo_coord,
        )
        self.assertEqual(ev.puntaje_valido, 0)
        self.assertTrue(motivos_sin_puntaje_evidencia(ev))

    def test_verificacion_cuatro_estados_e_inmutabilidad_tras_aprobacion(self):
        ev = Evidencia.objects.create(
            codigo="EVI-VER-01",
            funcionario=self.func1,
            estado="Pendiente",
            fecha_registro=self.hoy,
            item_medir="Atención",
            solicitud="Reparación sede",
            accion="Inspección inicial",
            contacto_nombre="Luis Vega",
            contacto_telefono="+56944444444",
            subtipo_atencion=self.subtipo_normal,
        )

        # Supervisor pide más antecedentes
        self.client.force_login(self.sup_a)
        self.client.post(
            reverse("principal:verificacion"),
            {
                "tipo_registro": "evidencia",
                "registro_id": ev.id,
                "nuevo_estado": "Solicitud de más antecedentes",
                "observacion": "Falta foto panorámica",
            },
        )
        ev.refresh_from_db()
        self.assertEqual(ev.estado, "Solicitud de más antecedentes")

        # Supervisor aprueba
        self.client.post(
            reverse("principal:verificacion"),
            {
                "tipo_registro": "evidencia",
                "registro_id": ev.id,
                "nuevo_estado": "Aprobada",
                "observacion": "Conforme",
            },
        )
        ev.refresh_from_db()
        self.assertEqual(ev.estado, "Aprobada")
        self.assertEqual(ev.puntaje_valido, 1)

        # Ni el funcionario ni el supervisor pueden alterar un registro ya aprobado
        with self.assertRaises(ValidationError):
            validar_registro_editable(ev.estado)

        self.client.force_login(self.func1)
        self.client.post(
            reverse("principal:evidencias"),
            {
                "accion": "editar_evidencia",
                "evidencia_id": ev.id,
                "solicitud": "Intento alterar aprobado",
                "accion_realizada": "No debe cambiar",
            },
        )
        ev.refresh_from_db()
        self.assertEqual(ev.solicitud, "Reparación sede")
        self.assertEqual(ev.estado, "Aprobada")


class TuboYPropiedadTests(BaseSGRTestCase):
    def test_funcionario_solo_edita_sus_propios_compromisos_y_no_puede_cerrarlos(self):
        comp = Compromiso.objects.create(
            codigo="COM-PROP-01",
            titulo="Limpieza microbasural",
            territorio=self.deleg_a,
            sector=self.terr_a,
            responsable=self.func1,
            creado_por=self.func1,
            estado="Pendiente",
            area="Gestión territorial",
            solicitante="Carmen Díaz",
            fecha=self.hoy,
            plazo="3 días",
        )

        # Otro funcionario consulta el Tubo (200), pero no puede editar (403)
        self.client.force_login(self.func2)
        self.assertEqual(self.client.get(reverse("principal:agenda")).status_code, 200)
        resp_forbidden = self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "En proceso", "observacion": "Intento ajeno"},
        )
        self.assertEqual(resp_forbidden.status_code, 403)

        # El dueño puede avanzar a "En proceso"
        self.client.force_login(self.func1)
        self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "En proceso", "observacion": "Trabajando"},
        )
        comp.refresh_from_db()
        self.assertEqual(comp.estado, "En proceso")

        # El funcionario NO puede marcar Completado ni Rechazado (403)
        resp_comp = self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "Completado", "observacion": "Intento autocierre"},
        )
        self.assertEqual(resp_comp.status_code, 403)
        resp_rech = self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "Rechazado", "observacion": "Intento autorechazo"},
        )
        self.assertEqual(resp_rech.status_code, 403)
        comp.refresh_from_db()
        self.assertEqual(comp.estado, "En proceso")

        # El Supervisor sí puede marcar Completado; luego queda inmutable
        self.client.force_login(self.sup_a)
        self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "Completado", "observacion": "Aprobado por supervisor"},
        )
        comp.refresh_from_db()
        self.assertEqual(comp.estado, "Completado")

        # Ya completado no vuelve atrás
        self.client.post(
            reverse("principal:agenda"),
            {"codigo": comp.codigo, "nuevo_estado": "Pendiente", "observacion": "Reabrir"},
        )
        comp.refresh_from_db()
        self.assertEqual(comp.estado, "Completado")

    def test_fecha_limite_tarea_no_se_puede_modificar_ni_por_administrador(self):
        fecha_original = date(2026, 12, 1)
        comp = Compromiso.objects.create(
            codigo="TAR-FIJA-01",
            titulo="Inspección inicial",
            territorio=self.deleg_a,
            sector=self.terr_a,
            responsable=self.func1,
            creado_por=self.sup_a,
            estado="Pendiente",
            prioridad="Media",
            area="Tubo de trabajo",
            solicitante="Supervisor",
            fecha=self.hoy,
            plazo="5 días",
            fecha_limite=fecha_original,
        )

        self.client.force_login(self.admin)
        self.client.post(
            reverse("principal:asignar_tareas"),
            {
                "accion": "editar",
                "tarea_id": comp.id,
                "funcionario_id": self.func2.id,
                "territorio_id": self.terr_a.id,
                "titulo": "Inspección reasignada",
                "descripcion": "Detalle actualizado",
                "prioridad": "Alta",
                "fecha_limite": "2026-12-30",
            },
        )
        comp.refresh_from_db()
        self.assertEqual(comp.titulo, "Inspección reasignada")
        self.assertEqual(comp.responsable, self.func2)
        self.assertEqual(comp.fecha_limite, fecha_original)
        self.assertEqual(comp.plazo, "5 días")

    def test_tubo_cartas_creacion_y_propiedad(self):
        url_crear = _url_de_vista(views.crear_carta)
        url_editar = _url_de_vista(views.editar_carta)

        self.client.force_login(self.func1)
        self.client.post(
            url_crear,
            {
                "numero_carta": "C-101",
                "remitente": "Carlos Muñoz",
                "rut_remitente": "15.432.198-7",
                "telefono": "+56955555555",
                "actividad_tema": "Solicitud de poda de árboles",
                "para": "Alcaldesa",
            },
        )
        carta = CartaOficinaPartes.objects.get(numero_carta="C-101")
        self.assertEqual(carta.responsable, self.func1)

        # Otro funcionario no puede modificar una carta ajena
        self.client.force_login(self.func2)
        resp = self.client.post(
            url_editar,
            {"carta_id": carta.id, "actividad_tema": "Editado sin permiso", "estado": "En proceso"},
        )
        self.assertEqual(resp.status_code, 403)


class OrganizacionesYCatalogosTests(BaseSGRTestCase):
    def test_supervisor_gestiona_tipos_organizacion_y_bloquea_doble_presidente(self):
        self.client.force_login(self.sup_a)

        # Crear tipo dinámico de organización
        self.client.post(
            reverse("principal:tipo_organizacion_crear"),
            {"nombre": "Agrupación Ambientalista", "descripcion": "Cuidado de áreas verdes", "activo": "on"},
        )
        tipo = TipoOrganizacion.objects.get(nombre="Agrupación Ambientalista")

        # Crear organización en su delegación
        self.client.post(
            reverse("principal:organizacion_crear"),
            {
                "nombre": "Agrupación Verde Antena",
                "tipo": tipo.id,
                "territorio": self.terr_a.id,
                "direccion": "Av. 18 de Septiembre 123",
                "socios_activos": 25,
                "personalidad_juridica": "4010",
                "activa": "on",
            },
        )
        org = JuntaVecinos.objects.get(nombre="Agrupación Verde Antena")

        # Asignar primer Presidente
        url_dir = reverse("principal:organizacion_directiva", args=[org.id])
        self.client.post(
            url_dir,
            {
                "rut": "12.345.678-5",
                "nombre_completo": "Juana Morales",
                "telefono": "+56966666666",
                "cargo_dirigencia": "Presidente",
                "fecha_inicio": self.hoy.isoformat(),
            },
        )
        # Intentar asignar un segundo Presidente vigente -> debe rechazarse
        self.client.post(
            url_dir,
            {
                "rut": "13.456.789-2",
                "nombre_completo": "Roberto Araya",
                "telefono": "+56977777777",
                "cargo_dirigencia": "Presidente",
                "fecha_inicio": self.hoy.isoformat(),
            },
        )
        self.assertEqual(Dirigencia.objects.filter(junta_vecinos=org, cargo_dirigencia="Presidente", vigente=True).count(), 1)

        # Supervisor de otra delegación recibe 403
        self.client.force_login(self.sup_b)
        self.assertEqual(self.client.get(reverse("principal:organizacion_editar", args=[org.id])).status_code, 403)

    def test_vinculacion_rapida_vecino_y_api_autocompletado(self):
        tipo = TipoOrganizacion.objects.create(nombre="Junta de Vecinos", activo=True)
        org = JuntaVecinos.objects.create(nombre="JJVV El Faro", tipo=tipo, territorio=self.terr_a, activa=True)
        vecino = Vecino.objects.create(rut="14.111.222-3", nombre_completo="Elena Flores", telefono="+56910101010")

        # Sin organización ("No pertenece a ninguna") no crea membresía
        vincular_vecino_a_organizacion(vecino, "")
        self.assertEqual(Dirigencia.objects.filter(vecino=vecino).count(), 0)

        # Con organización vincula una sola vez como Socio
        vincular_vecino_a_organizacion(vecino, str(org.id))
        vincular_vecino_a_organizacion(vecino, str(org.id))
        self.assertEqual(Dirigencia.objects.filter(vecino=vecino, junta_vecinos=org, vigente=True).count(), 1)

        # API devuelve el vecino y preselecciona su organización
        self.client.force_login(self.func1)
        resp = self.client.get(reverse("principal:api_buscar_vecino"), {"rut": "14111222-3"})
        datos = resp.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["junta_vecinos_id"], org.id)

    def test_asignacion_meta_valida_tope_ponderacion_100_y_roles_protegidos(self):
        m1 = CatalogoMeta.objects.create(codigo="M-01", nombre="Atenciones", cargo_sugerido=self.cargo_gestor, activa=True)
        m2 = CatalogoMeta.objects.create(codigo="M-02", nombre="Terrenos", cargo_sugerido=self.cargo_gestor, activa=True)

        AsignacionMeta.objects.create(
            funcionario=self.func1,
            trimestre=self.trimestre_abierto,
            catalogo_meta=m1,
            cantidad_exigida=10,
            ponderacion=70,
            tope_cumplimiento=120,
        )

        # 70% + 40% = 110% -> el formulario debe rechazarlo
        form_excedido = AsignacionMetaForm(
            data={
                "funcionario": self.func1.id,
                "trimestre": self.trimestre_abierto.id,
                "catalogo_meta": m2.id,
                "cantidad_exigida": 5,
                "ponderacion": 40,
                "tope_cumplimiento": 120,
            }
        )
        self.assertFalse(form_excedido.is_valid())
        self.assertIn("ponderacion", form_excedido.errors)

        # Rol base no puede eliminarse desde el CRUD de Administración
        self.client.force_login(self.admin)
        self.client.post(reverse("principal:catalogo_accion", args=["roles", self.g_func.id]))
        self.assertTrue(Group.objects.filter(pk=self.g_func.id).exists())


class MetasAusenciasYCorreoTests(BaseSGRTestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_felicitacion_exige_respaldo_formal_y_envia_correo_al_funcionario(self):
        url_ajuste = _url_de_vista(views.registrar_ajuste_desempeno)
        self.client.force_login(self.sup_a)

        # Sin archivo de respaldo -> rechazada
        self.client.post(
            url_ajuste,
            {
                "funcionario_id": self.func1.id,
                "trimestre_id": self.trimestre_abierto.id,
                "tipo": "Felicitación",
                "porcentaje_ajuste": "5",
                "motivo": "Buen trato en operativo",
            },
        )
        self.assertEqual(AjusteDesempeno.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

        # Con respaldo formal PDF -> aprobada y envía notificación por correo
        respaldo = SimpleUploadedFile("oficio_delegado.pdf", b"%PDF-1.4 respaldo", content_type="application/pdf")
        self.client.post(
            url_ajuste,
            {
                "funcionario_id": self.func1.id,
                "trimestre_id": self.trimestre_abierto.id,
                "tipo": "Felicitación",
                "porcentaje_ajuste": "5",
                "motivo": "Felicitación formal del delegado",
                "archivo_respaldo": respaldo,
            },
        )
        self.assertEqual(AjusteDesempeno.objects.count(), 1)
        ajuste = AjusteDesempeno.objects.first()
        self.assertEqual(ajuste.porcentaje_ajuste, Decimal("5"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.func1.email, mail.outbox[0].to)

    def test_ausencia_y_dashboard_funcionan_con_metas_al_tope_120(self):
        cat = CatalogoMeta.objects.create(codigo="M-120", nombre="Atenciones", cargo_sugerido=self.cargo_gestor, activa=True)
        asig = AsignacionMeta.objects.create(
            funcionario=self.func1,
            trimestre=self.trimestre_abierto,
            catalogo_meta=cat,
            cantidad_exigida=10,
            ponderacion=100,
            tope_cumplimiento=120,
        )

        # 15 evidencias aprobadas sobre meta de 10 (150% bruto -> tope 120%)
        for idx in range(15):
            Evidencia.objects.create(
                codigo=f"EVI-CAP-{idx}",
                funcionario=self.func1,
                estado="Aprobada",
                fecha_registro=self.hoy,
                item_medir=cat.nombre,
                solicitud=f"Solicitud {idx}",
                accion="Resuelta",
                contacto_nombre="Vecino",
                contacto_telefono="+56999999999",
                trimestre=self.trimestre_abierto,
                asignacion_meta=asig,
            )

        # Registrar ausencia por el supervisor
        url_ausencia = _url_de_vista(views.registrar_ausencia)
        tipo_aus = _primera_opcion(Ausencia, "tipo_ausencia", "Licencia médica")
        self.client.force_login(self.sup_a)
        self.client.post(
            url_ausencia,
            {
                "funcionario_id": self.func1.id,
                "trimestre_id": self.trimestre_abierto.id,
                "tipo_ausencia": tipo_aus,
                "fecha_inicio": self.hoy.isoformat(),
                "fecha_termino": self.hoy.isoformat(),
                "dias_descontados": "10",
                "observacion": "Licencia informada por delegado",
            },
        )
        self.assertEqual(Ausencia.objects.filter(funcionario=self.func1).count(), 1)

        # Verificar que tanto Equipo como Mi Panel rendericen correctamente y muestren tope 120%
        self.assertEqual(self.client.get(reverse("principal:equipo")).status_code, 200)
        self.client.force_login(self.func1)
        resp_panel = self.client.get(reverse("principal:panel"))
        self.assertEqual(resp_panel.status_code, 200)
        self.assertContains(resp_panel, "120")