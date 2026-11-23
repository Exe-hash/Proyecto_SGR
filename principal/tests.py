from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


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