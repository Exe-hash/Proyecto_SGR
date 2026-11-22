from django import forms
from django.contrib.auth.models import Group, User

from .models import Cargo, Delegacion, PerfilUsuario


class UsuarioCRUDForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Contraseña temporal (en edición dejar vacío para mantener)",
            }
        ),
        label="Contraseña temporal",
        required=False,
    )
    grupo = forms.ModelChoiceField(
        queryset=Group.objects.filter(name__in=["Funcionario", "Supervisor", "Administrador"]),
        required=True,
        label="Perfil de Sistema (Rol)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    delegacion = forms.ModelChoiceField(
        queryset=Delegacion.objects.filter(activa=True),
        required=True,
        label="Delegación Territorial",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cargo = forms.ModelChoiceField(
        queryset=Cargo.objects.filter(activo=True),
        required=True,
        label="Cargo a Desempeñar",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    debe_cambiar_clave = forms.BooleanField(
        required=False,
        initial=True,
        label="Exigir cambio de contraseña en el próximo ingreso",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "RUT o Identificador"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "ejemplo@laserena.cl"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            perfil = getattr(self.instance, "perfil", None)
            if perfil:
                self.fields["delegacion"].initial = perfil.delegacion
                self.fields["cargo"].initial = perfil.cargo
                self.fields["debe_cambiar_clave"].initial = perfil.debe_cambiar_clave
            grupo_actual = self.instance.groups.first()
            if grupo_actual:
                self.fields["grupo"].initial = grupo_actual

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("El correo institucional es obligatorio.")
        existe = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()
        if existe:
            raise forms.ValidationError("Ya existe otro usuario registrado con este correo.")
        return email

    def clean_password(self):
        raw_password = self.cleaned_data.get("password")
        if not self.instance.pk and not raw_password:
            raise forms.ValidationError("Debe asignar una contraseña temporal para crear el usuario.")
        return raw_password

    def save(self, commit=True):
        es_nuevo = self.instance.pk is None
        usuario = super().save(commit=False)
        raw_password = self.cleaned_data.get("password")
        if raw_password:
            usuario.set_password(raw_password)

        if commit:
            usuario.save()
            usuario.groups.clear()
            usuario.groups.add(self.cleaned_data["grupo"])

            exigir_cambio = self.cleaned_data.get("debe_cambiar_clave", False)
            if es_nuevo:
                exigir_cambio = True

            perfil, created = PerfilUsuario.objects.get_or_create(
                usuario=usuario,
                defaults={
                    "delegacion": self.cleaned_data["delegacion"],
                    "cargo": self.cleaned_data["cargo"],
                    "debe_cambiar_clave": exigir_cambio,
                },
            )
            if not created:
                perfil.delegacion = self.cleaned_data["delegacion"]
                perfil.cargo = self.cleaned_data["cargo"]
                if raw_password or "debe_cambiar_clave" in self.changed_data:
                    perfil.debe_cambiar_clave = exigir_cambio
                perfil.save()

        return usuario