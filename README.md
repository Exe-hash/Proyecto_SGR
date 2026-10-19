# Sistema de Gestión de Resultados (SGR)

Proyecto académico descrito en `analisis_inicial.md`. Contiene una versión visual navegable basada en las referencias entregadas para el SGR. Las pantallas usan datos ficticios y no implementan aún la gestión real del sistema; consultar `frontend_trazabilidad.md` para conocer el alcance y los pendientes.

## Organización

- `manage.py`: entrada para ejecutar comandos de Django.
- `config/`: configuración general y rutas principales del proyecto.
- `principal/`: primera aplicación de Django, con su vista y rutas.
- `templates/`: archivos HTML de las páginas.
- `static/css/`: hojas de estilo.
- `static/js/`: archivos JavaScript.
- `static/img/`: imágenes que utilizará la aplicación.
- `disenos/`: referencias y exportaciones de Figma.
- `analisis_inicial.md`: alcance y preguntas pendientes.
- `frontend_trazabilidad.md`: referencias por pantalla y trabajo funcional pendiente.

## Iniciar en Windows con PowerShell

Desde una terminal ubicada en esta carpeta, crear el entorno e instalar las dependencias si todavía no se ha hecho:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para ejecutar el proyecto se necesita una base de datos MySQL disponible y un archivo `.env` en la carpeta principal. Ese archivo contiene la configuración local de la conexión y no debe subirse al repositorio.

La configuración reconoce las variables `SGR_DB_NAME`, `SGR_DB_USER`, `SGR_DB_PASSWORD`, `SGR_DB_HOST` y `SGR_DB_PORT`. La contraseña debe corresponder al usuario de MySQL configurado para la base de datos.

Después de configurar la conexión, preparar la base local y ejecutar el servidor:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir `http://127.0.0.1:8000/`. Para detener el servidor, usar `Ctrl+C` en su terminal.

El proyecto cuenta con un inicio de sesión que utiliza los usuarios de Django y una conexión local a MySQL. Para ingresar, es necesario crear previamente un usuario en la base de datos configurada.

Las vistas muestran datos ficticios de demostración. Los formularios, las decisiones y los cambios temporales todavía no se guardan como información del sistema.

El control de permisos por rol y delegación aún está pendiente. La configuración actual es para desarrollo y no está lista para uso en producción.

En desarrollo, si `DJANGO_SECRET_KEY` no está definida, Django genera una clave temporal que cambia entre ejecuciones; por eso las sesiones se invalidarán al reiniciar. Si se desactiva `DJANGO_DEBUG`, se debe configurar una clave secreta y revisar toda la configuración necesaria para producción. No guardar secretos en el repositorio.
