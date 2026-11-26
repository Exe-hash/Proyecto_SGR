
from django import forms
from django.contrib.auth.models import Group, User
from django.db.models import Q, Sum

from .models import (
    AsignacionMeta,
    Cargo,
    CatalogoMeta,
    Delegacion,
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
from .reglas import normalizar_rut

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
        queryset=Group.objects.filter(
            name__in=["Funcionario", "Supervisor", "Administrador"]
        ),
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
            "username": forms.TextInput(
                attrs={
                    "class": "form-control input-rut",
                    "placeholder": "RUT o Identificador",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ejemplo@laserena.cl",
                }
            ),
            "first_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            perfil = getattr(self.instance, "perfil", None)

            if perfil:
                self.fields["delegacion"].initial = perfil.delegacion
                self.fields["cargo"].initial = perfil.cargo
                self.fields["debe_cambiar_clave"].initial = (
                    perfil.debe_cambiar_clave
                )

            grupo_actual = self.instance.groups.first()

            if grupo_actual:
                self.fields["grupo"].initial = grupo_actual

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if not email:
            raise forms.ValidationError(
                "El correo institucional es obligatorio."
            )

        existe = User.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk).exists()

        if existe:
            raise forms.ValidationError(
                "Ya existe otro usuario registrado con este correo."
            )

        return email

    def clean_password(self):
        raw_password = self.cleaned_data.get("password")

        if not self.instance.pk and not raw_password:
            raise forms.ValidationError(
                "Debe asignar una contraseña temporal para crear el usuario."
            )

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

            exigir_cambio = self.cleaned_data.get(
                "debe_cambiar_clave",
                False,
            )

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

                if (
                    raw_password
                    or "debe_cambiar_clave" in self.changed_data
                ):
                    perfil.debe_cambiar_clave = exigir_cambio

                perfil.save()

        return usuario

class TipoOrganizacionForm(forms.ModelForm):
    class Meta:
        model = TipoOrganizacion
        fields = ["nombre", "descripcion", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Agrupación Cultural"}),
            "descripcion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Descripción breve (opcional)"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre del tipo de organización es obligatorio.")
        existe = TipoOrganizacion.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists()
        if existe:
            raise forms.ValidationError("Ya existe un tipo de organización con ese nombre.")
        return nombre


class JuntaVecinosForm(forms.ModelForm):
    class Meta:
        model = JuntaVecinos
        fields = [
            "nombre",
            "tipo",
            "territorio",
            "direccion",
            "socios_activos",
            "fecha_constitucion",
            "personalidad_juridica",
            "fecha_inscripcion_registro",
            "registro_directorio_numero",
            "activa",
        ]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre oficial de la organización"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "territorio": forms.Select(attrs={"class": "form-select"}),
            "direccion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Domicilio legal (opcional)"}),
            "socios_activos": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "fecha_constitucion": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "personalidad_juridica": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 4006"}),
            "fecha_inscripcion_registro": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "registro_directorio_numero": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 9759 (opcional)"}),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, delegacion_restringida=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoOrganizacion.objects.filter(activo=True).order_by("nombre")
        self.fields["tipo"].required = True
        self.fields["tipo"].empty_label = "-- Seleccione tipo de organización --"

        territorios = Territorio.objects.filter(activo=True).select_related("delegacion").order_by("delegacion__nombre", "nombre")
        if delegacion_restringida is not None:
            territorios = territorios.filter(delegacion=delegacion_restringida)
        self.fields["territorio"].queryset = territorios
        self.fields["territorio"].empty_label = "-- Seleccione territorio --"

    def clean(self):
        cleaned = super().clean()
        nombre = (cleaned.get("nombre") or "").strip()
        territorio = cleaned.get("territorio")
        f_const = cleaned.get("fecha_constitucion")
        f_insc = cleaned.get("fecha_inscripcion_registro")

        if nombre and territorio:
            duplicado = (
                JuntaVecinos.objects.filter(territorio=territorio, nombre__iexact=nombre)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicado:
                self.add_error("nombre", "Ya existe una organización con ese nombre en este territorio.")

        if f_const and f_insc and f_insc < f_const:
            self.add_error(
                "fecha_inscripcion_registro",
                "La fecha de inscripción no puede ser anterior a la fecha de constitución.",
            )

        cleaned["nombre"] = nombre
        return cleaned

class UsuarioLabelChoiceField(forms.ModelChoiceField):
    """Muestra nombre completo + username en selectores de funcionarios."""

    def label_from_instance(self, obj):
        nombre = obj.get_full_name().strip()
        return f"{nombre} ({obj.username})" if nombre else obj.username


class DelegacionForm(forms.ModelForm):
    class Meta:
        model = Delegacion
        fields = ["nombre", "activa"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Delegación Las Compañías"}),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if Delegacion.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una delegación registrada con este nombre.")
        return nombre


class TerritorioForm(forms.ModelForm):
    class Meta:
        model = Territorio
        fields = ["delegacion", "nombre", "activo"]
        widgets = {
            "delegacion": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Antena, Alfalfares, La Florida"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        delegacion = cleaned.get("delegacion")
        nombre = (cleaned.get("nombre") or "").strip()
        if delegacion and nombre:
            if Territorio.objects.filter(delegacion=delegacion, nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
                self.add_error("nombre", "Ya existe este territorio dentro de la delegación seleccionada.")
        cleaned["nombre"] = nombre
        return cleaned


class CargoForm(forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nombre", "es_area_social", "meta_minima_porcentaje", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gestor Territorial"}),
            "es_area_social": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "meta_minima_porcentaje": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 100}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if Cargo.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un cargo con este nombre.")
        return nombre


class VecinoForm(forms.ModelForm):
    class Meta:
        model = Vecino
        fields = ["rut", "nombre_completo", "telefono", "correo", "direccion", "territorio", "activo"]
        widgets = {
            "rut": forms.TextInput(attrs={"class": "form-control input-rut", "placeholder": "12.345.678-9"}),
            "nombre_completo": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control", "placeholder": "+56 9 ..."}),
            "correo": forms.EmailInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "territorio": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_rut(self):
        rut_norm = normalizar_rut(self.cleaned_data.get("rut"))
        rut_sin_puntos = rut_norm.replace(".", "")
        if not rut_norm:
            raise forms.ValidationError("El RUT es obligatorio.")
        existe = (
            Vecino.objects.filter(Q(rut__iexact=rut_norm) | Q(rut__iexact=rut_sin_puntos))
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existe:
            raise forms.ValidationError("Ya existe un vecino registrado con este RUT.")
        return rut_norm


class HitoForm(forms.ModelForm):
    responsable = UsuarioLabelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("first_name", "last_name", "username"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Funcionario responsable",
    )

    class Meta:
        model = Hito
        fields = ["nombre", "descripcion", "territorio", "responsable", "fecha_comprometida", "estado"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Operativo Plaza Buenos Aires"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "territorio": forms.Select(attrs={"class": "form-select"}),
            "fecha_comprometida": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "estado": forms.Select(attrs={"class": "form-select"}),
        }


class TipoAtencionForm(forms.ModelForm):
    class Meta:
        model = TipoAtencion
        fields = ["nombre", "area", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Atención de Público"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if TipoAtencion.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un tipo de atención con ese nombre.")
        return nombre


class SubtipoAtencionForm(forms.ModelForm):
    class Meta:
        model = SubtipoAtencion
        fields = ["tipo_atencion", "nombre", "es_coordinacion", "activo"]
        widgets = {
            "tipo_atencion": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Envío de correos / Coordinación previa"}),
            "es_coordinacion": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_atencion")
        nombre = (cleaned.get("nombre") or "").strip()
        if tipo and nombre:
            if SubtipoAtencion.objects.filter(tipo_atencion=tipo, nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
                self.add_error("nombre", "Ya existe este subtipo dentro del tipo de atención elegido.")
        cleaned["nombre"] = nombre
        return cleaned


class TrimestreForm(forms.ModelForm):
    class Meta:
        model = Trimestre
        fields = [
            "codigo",
            "nombre",
            "fecha_inicio",
            "fecha_termino",
            "dias_computables",
            "tope_maximo_porcentaje",
            "cerrado",
        ]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 2026-Q4"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Trimestre Oct - Dic 2026"}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "fecha_termino": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "dias_computables": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 95}),
            "tope_maximo_porcentaje": forms.NumberInput(attrs={"class": "form-control", "min": 100, "max": 150}),
            "cerrado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip().upper()
        if Trimestre.objects.filter(codigo__iexact=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un trimestre con este código.")
        return codigo

    def clean(self):
        cleaned = super().clean()
        f_ini = cleaned.get("fecha_inicio")
        f_fin = cleaned.get("fecha_termino")
        if f_ini and f_fin and f_fin < f_ini:
            self.add_error("fecha_termino", "La fecha de término no puede ser anterior a la fecha de inicio.")
        return cleaned


class CatalogoMetaForm(forms.ModelForm):
    class Meta:
        model = CatalogoMeta
        fields = ["codigo", "nombre", "descripcion", "cargo_sugerido", "es_porcentual", "activa"]
        widgets = {
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: META-TER-01"}),
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Atenciones territoriales resueltas"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "cargo_sugerido": forms.Select(attrs={"class": "form-select"}),
            "es_porcentual": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip().upper()
        if CatalogoMeta.objects.filter(codigo__iexact=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una meta en el catálogo con este código.")
        return codigo


class AsignacionMetaForm(forms.ModelForm):
    funcionario = UsuarioLabelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("first_name", "last_name", "username"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Funcionario",
    )

    class Meta:
        model = AsignacionMeta
        fields = [
            "funcionario",
            "trimestre",
            "catalogo_meta",
            "cantidad_exigida",
            "ponderacion",
            "tope_cumplimiento",
        ]
        widgets = {
            "trimestre": forms.Select(attrs={"class": "form-select"}),
            "catalogo_meta": forms.Select(attrs={"class": "form-select"}),
            "cantidad_exigida": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "ponderacion": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 100}),
            "tope_cumplimiento": forms.NumberInput(attrs={"class": "form-control", "min": 100, "max": 150}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["catalogo_meta"].queryset = CatalogoMeta.objects.filter(activa=True).order_by("codigo")
        self.fields["trimestre"].queryset = Trimestre.objects.all().order_by("-fecha_inicio")

    def clean_cantidad_exigida(self):
        cantidad = self.cleaned_data.get("cantidad_exigida") or 0
        if cantidad < 1:
            raise forms.ValidationError("La cantidad exigida debe ser mayor o igual a 1.")
        return cantidad

    def clean(self):
        cleaned = super().clean()
        funcionario = cleaned.get("funcionario")
        trimestre = cleaned.get("trimestre")
        catalogo_meta = cleaned.get("catalogo_meta")
        ponderacion = cleaned.get("ponderacion") or 0

        if funcionario and trimestre and catalogo_meta:
            duplicado = (
                AsignacionMeta.objects.filter(
                    funcionario=funcionario,
                    trimestre=trimestre,
                    catalogo_meta=catalogo_meta,
                )
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicado:
                self.add_error("catalogo_meta", "Este funcionario ya tiene asignada esta meta en el trimestre seleccionado.")

        if funcionario and trimestre:
            suma_actual = (
                AsignacionMeta.objects.filter(funcionario=funcionario, trimestre=trimestre)
                .exclude(pk=self.instance.pk)
                .aggregate(total=Sum("ponderacion"))["total"]
                or 0
            )
            if suma_actual + ponderacion > 100:
                disponible = max(0, 100 - suma_actual)
                self.add_error(
                    "ponderacion",
                    f"La ponderación acumulada del funcionario en {trimestre.codigo} supera el 100% (actual: {suma_actual}%, disponible: {disponible}%).",
                )
        return cleaned

ROLES_BASE_SISTEMA = {"Funcionario", "Supervisor", "Administrador"}


class RolForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name"]
        labels = {"name": "Nombre del rol"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Auditor / Delegado"}),
        }

    def clean_name(self):
        nombre = (self.cleaned_data.get("name") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre del rol es obligatorio.")
        if self.instance.pk and self.instance.name in ROLES_BASE_SISTEMA and nombre != self.instance.name:
            raise forms.ValidationError(
                f"El rol base '{self.instance.name}' no puede renombrarse porque controla permisos críticos del sistema."
            )
        if Group.objects.filter(name__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un rol registrado con ese nombre.")
        return nombre