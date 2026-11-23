from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class CorreoInstitucionalBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        identificador = username.strip()
        usuario = (
            UserModel.objects.filter(
                Q(email__iexact=identificador) | Q(username__iexact=identificador)
            )
            .order_by("id")
            .first()
        )
        if usuario and usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None