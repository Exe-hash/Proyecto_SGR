from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse


class ControlAccesoPorRolTests(TestCase):
    def setUp(self):
        self.funcionario = User.objects.create_user(
            username="funcionario_test",
            password="ClaveDePrueba123",
        )
        self.jefatura = User.objects.create_user(
            username="jefatura_test",
            password="ClaveDePrueba123",
        )
        self.verificador = User.objects.create_user(
            username="verificador_test",
            password="ClaveDePrueba123",
        )

        grupo_funcionario = Group.objects.create(name="Funcionario")
        grupo_jefatura = Group.objects.create(name="Jefatura")
        grupo_verificador = Group.objects.create(name="Verificador")

        self.funcionario.groups.add(grupo_funcionario)
        self.jefatura.groups.add(grupo_jefatura)
        self.verificador.groups.add(grupo_verificador)

    def test_funcionario_accede_a_registro_de_actividades(self):
        self.client.force_login(self.funcionario)

        respuesta = self.client.get(reverse("principal:actividades"))

        self.assertEqual(respuesta.status_code, 200)

    def test_funcionario_no_accede_a_resumen_de_equipo(self):
        self.client.force_login(self.funcionario)

        respuesta = self.client.get(reverse("principal:equipo"))

        self.assertEqual(respuesta.status_code, 403)

    def test_jefatura_accede_a_resumen_de_equipo(self):
        self.client.force_login(self.jefatura)

        respuesta = self.client.get(reverse("principal:equipo"))

        self.assertEqual(respuesta.status_code, 200)

    def test_verificador_accede_a_revision_de_evidencias(self):
        self.client.force_login(self.verificador)

        respuesta = self.client.get(reverse("principal:verificacion"))

        self.assertEqual(respuesta.status_code, 200)

    def test_usuario_sin_sesion_es_redirigido_al_inicio(self):
        respuesta = self.client.get(reverse("principal:panel"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("principal:inicio"), respuesta.url)