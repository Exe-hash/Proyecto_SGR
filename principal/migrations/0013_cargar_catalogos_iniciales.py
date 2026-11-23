

from django.db import migrations


def cargar_catalogos(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Delegacion = apps.get_model("principal", "Delegacion")
    Territorio = apps.get_model("principal", "Territorio")

    for rol in ("Administrador", "Supervisor", "Funcionario"):
        Group.objects.get_or_create(name=rol)

    datos = {
        "Casa Central": ["Centro Histórico", "Sector Universitario", "La Recova"],
        "Las Compañías": ["Las Compañías Alta", "Las Compañías Baja", "El Olivar"],
        "La Antena": ["La Antena", "La Florida", "Coll"],
        "La Pampa": ["La Pampa", "San Joaquín", "El Milagro"],
        "Avenida del Mar": ["El Faro", "Avenida del Mar", "Peñuelas Norte"],
        "Sector Rural": ["Algarrobito", "Altovalsol", "Coquimbito"],
    }

    for nombre_delegacion, territorios in datos.items():
        delegacion, _ = Delegacion.objects.get_or_create(nombre=nombre_delegacion)
        for nombre_territorio in territorios:
            Territorio.objects.get_or_create(
                delegacion=delegacion,
                nombre=nombre_territorio,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("principal", "0012_compromiso_descripcion"),
    ]

    operations = [
        migrations.RunPython(cargar_catalogos, migrations.RunPython.noop),
    ]