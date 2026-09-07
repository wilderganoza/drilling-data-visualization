# Importamos json para serializar el mensaje del toast en la cabecera HX-Trigger
import json

# Importamos las clases de FastAPI para el router, inyección de dependencias y la request
from fastapi import APIRouter, Depends, Request
# Importamos las respuestas HTML (fragmento tras borrar un caso) y de redirección (ruta legacy /cases)
from fastapi.responses import HTMLResponse, RedirectResponse
# Importamos Session para tipar la sesión de base de datos
from sqlalchemy.orm import Session

# Importamos la dependencia que resuelve el usuario autenticado desde la cookie
from app.core.deps import get_current_user_web
# Importamos el modelo User para tipar el usuario autenticado
from app.models.legacy import User
# Importamos el repositorio de pozos para resolver los nombres de los pozos
from app.repositories.well_repository import WellRepository
# Importamos el gestor de bases de datos y la dependencia de sesión sobre la BD de profundidad
from app.db.session import db_manager, get_depth_db
# Importamos el servicio de detección de outliers, dueño de los datasets/casos guardados
from app.services.outlier_detection import OutlierDetectionService
# Importamos las plantillas Jinja2 para renderizar el fragmento de la tabla de casos
from app.web.templating import templates

# Creamos el router de casos (sin prefijo)
router = APIRouter()


def _get_outlier_service(db: Session) -> OutlierDetectionService:
    # Obtenemos la tabla well_data del dominio de profundidad sobre la que trabaja el servicio
    table = db_manager.get_depth_table("well_data")
    # Instanciamos el servicio de detección de outliers con la sesión y la tabla resueltas
    return OutlierDetectionService(db, table)


def _cases_context(db: Session) -> dict:
    # Creamos el servicio de outliers para esta sesión
    service = _get_outlier_service(db)
    # Listamos todos los datasets/casos guardados
    datasets = service.list_all_datasets()

    # Creamos el repositorio de pozos
    well_repo = WellRepository(db)
    # Armamos un mapa id de pozo -> nombre de pozo para no consultar uno por uno
    well_name_by_id = {w.id: w.well_name for w in well_repo.get_all(skip=0, limit=1000)}

    # Acumulamos aquí las filas que va a consumir la plantilla de la tabla de casos
    rows = []
    for ds in datasets:
        rows.append(
            {
                "id": ds.id,
                "name": ds.name,
                "well_id": ds.well_id,
                # Resolvemos el nombre del pozo desde el mapa, con un nombre de respaldo si no está
                "well_name": well_name_by_id.get(ds.well_id, f"Well {ds.well_id}"),
                "status": ds.status,
                "record_count": ds.record_count,
                # Tomamos el conteo de outliers desde las métricas del dataset, si existen
                "outliers": ds.metrics.outlier_records if ds.metrics else 0,
                # Tomamos el porcentaje de outliers desde las métricas del dataset, si existen
                "outlier_pct": ds.metrics.outlier_percentage if ds.metrics else None,
                "created_at": ds.created_at,
            }
        )
    # Devolvemos el contexto con las filas ya armadas
    return {"rows": rows}


# Definimos la ruta legacy de la página de casos
@router.get("/cases")
async def cases_page(current_user: User = Depends(get_current_user_web)):
    """Relocated into Analytics (Saved Cases). Redirect keeps old links working;
    the delete action below (DELETE /cases/{id}) is unchanged."""
    # Redirigimos permanentemente (307, conserva el método) a la nueva ubicación en Analytics
    return RedirectResponse(url="/analytics/cases", status_code=307)


# Definimos la ruta que borra un caso/dataset guardado
@router.delete("/cases/{dataset_id}", response_class=HTMLResponse)
async def delete_case(
    dataset_id: int,
    request: Request,
    db: Session = Depends(get_depth_db),
    current_user: User = Depends(get_current_user_web),
):
    # Creamos el servicio de outliers para esta sesión
    service = _get_outlier_service(db)
    # Intentamos borrar el dataset indicado
    deleted = service.delete_dataset(dataset_id)

    # Recalculamos el contexto de la tabla de casos ya sin el dataset borrado
    ctx = _cases_context(db)
    # Agregamos al contexto la request y el usuario actual, requeridos por la plantilla
    ctx.update({"request": request, "current_user": current_user})
    # Renderizamos el fragmento de la tabla de casos actualizada
    response = templates.TemplateResponse(request, "partials/cases_table.html", ctx)
    # Armamos el mensaje del toast según si el borrado tuvo éxito o falló
    toast = {"message": "Case deleted"} if deleted else {"message": "Error deleting case", "type": "error"}
    # Disparamos el evento HTMX para que el frontend muestre el toast
    response.headers["HX-Trigger"] = json.dumps({"toast": toast})
    # Devolvemos la respuesta con el fragmento y el toast
    return response
