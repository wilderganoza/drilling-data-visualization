# Importamos json para serializar valores dentro de los templates
import json
# Importamos Path para construir las rutas de los directorios de plantillas y estáticos
from pathlib import Path

# Importamos Jinja2Templates para configurar el motor de plantillas de FastAPI
from fastapi.templating import Jinja2Templates
# Importamos Markup para marcar cadenas como HTML seguro (ya escapado) dentro de los templates
from markupsafe import Markup

# Calculamos el directorio de plantillas relativo a la raíz del paquete app
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
# Calculamos el directorio de archivos estáticos relativo a la raíz del paquete app
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Instanciamos el motor de plantillas Jinja2 apuntando al directorio de templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _asset(path: str) -> str:
    """Static URL with an mtime cache-buster (`?v=<mtime>`) so browsers always
    pick up CSS/JS edits instead of serving a stale cached copy."""
    try:
        # Leemos la fecha de modificación del archivo estático para usarla como versión
        v = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        # Si el archivo no existe o no se puede leer, usamos 0 como versión por defecto
        v = 0
    # Devolvemos la URL del estático con el parámetro de versión para invalidar la caché del navegador
    return f"/static/{path}?v={v}"


def _tojson(value) -> Markup:
    """Vanilla Jinja2 has no `tojson` filter (that's a Flask addition) — embed
    JSON safely inside a <script> tag by escaping the few HTML-sensitive chars."""
    # Serializamos el valor a JSON
    raw = json.dumps(value)
    # Escapamos los caracteres sensibles para HTML y marcamos el resultado como seguro
    return Markup(raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def _fmt_datetime(value) -> str:
    # Si no hay valor, mostramos un guion como placeholder
    if value is None:
        return "-"
    try:
        # Formateamos la fecha/hora en el formato usado por las plantillas
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        # Si el valor no es un datetime, devolvemos su representación como texto
        return str(value)


def _fmt_number(value, decimals: int = 1) -> str:
    # Si no hay valor, mostramos un guion como placeholder
    if value is None:
        return "-"
    try:
        # Formateamos el número con separador de miles y la cantidad de decimales indicada
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        # Si el valor no se puede convertir a float, devolvemos su representación como texto
        return str(value)


def _money(value) -> str:
    """$1,500,000 style — matches the local `money()` macros duplicated in
    variance.html/end_of_well.html before this shared filter existed. No
    currency-code awareness (matches what those macros already did)."""
    # Si no hay valor o está vacío, mostramos un guion largo como placeholder
    if value is None or value == "":
        return "—"
    try:
        # Formateamos el monto con símbolo de dólar, separador de miles y sin decimales
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        # Si el valor no se puede convertir a float, devolvemos su representación como texto
        return str(value)


# Registramos los filtros personalizados en el entorno de Jinja2
templates.env.filters["fmt_datetime"] = _fmt_datetime
templates.env.filters["fmt_number"] = _fmt_number
templates.env.filters["money"] = _money
templates.env.filters["tojson"] = _tojson
# Registramos asset como función global para poder llamarla directamente en los templates
templates.env.globals["asset"] = _asset
