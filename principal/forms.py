from django import forms
from django.contrib.auth.models import User, Group
from .models import PerfilUsuario, Delegacion, Cargo

class UsuarioCRUDForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Dejar en blanco para mantener'}), 
        label="Contraseña", 
        required=False
    )
    grupo = forms.ModelChoiceField(
        queryset=Group.objects.filter(name__in=["Funcionario", "Supervisor", "Administrador"]), 
        required=True, 
        label="Perfil de Sistema (Rol)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    delegacion = forms.ModelChoiceField(
        queryset=Delegacion.objects.all(), 
        required=True, 
        label="Delegación Territorial",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    cargo = forms.ModelChoiceField(
        queryset=Cargo.objects.all(), 
        required=True, 
        label="Cargo a Desempeñar",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RUT o Identificador'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@laserena.cl'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

    def save(self, commit=True):
        usuario = super().save(commit=False)
        raw_password = self.cleaned_data.get("password")
        if raw_password:
            usuario.set_password(raw_password)
            
        if commit:
            usuario.save()
            usuario.groups.clear()
            usuario.groups.add(self.cleaned_data['grupo'])
            
            perfil, created = PerfilUsuario.objects.get_or_create(usuario=usuario, defaults={
                'delegacion': self.cleaned_data['delegacion'],
                'cargo': self.cleaned_data['cargo']
            })
            if not created:
                perfil.delegacion = self.cleaned_data['delegacion']
                perfil.cargo = self.cleaned_data['cargo']
                perfil.save()
                
        return usuario