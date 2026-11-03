from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class CorreoInstitucionalBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            usuario = UserModel.objects.get(Q(email__iexact=username) | Q(username__iexact=username))
        except UserModel.DoesNotExist:
            return None
        else:
            if usuario.check_password(password) and self.user_can_authenticate(usuario):
                return usuario
        return None