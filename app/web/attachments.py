"""File attachments (photos, documents) for daily reports and NPT events.
Stored in-DB (ops_attachments.data). Images are shown inline as thumbnails;
anything else gets a download link. Upload/delete require an edit role and are
blocked on an approved/locked report."""
import io  # Usado para envolver los bytes del archivo en un stream al descargar

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile  # Piezas de FastAPI para rutas, inyección, archivos y errores HTTP
from fastapi.responses import HTMLResponse, StreamingResponse  # Respuestas HTML (partials) y de streaming (descarga de archivo)
from sqlalchemy import select  # Constructor de consultas explícitas para listar adjuntos
from sqlalchemy.orm import Session  # Tipado de la sesión de SQLAlchemy

from app.core.deps import get_current_user_web  # Dependencia que resuelve el usuario autenticado
from app.models.legacy import User  # Modelo User para tipar el usuario
from app.db.session import get_db  # Dependencia que entrega la sesión de base de datos
from app.core.permissions import require_ops_role  # Fábrica de dependencia que exige un rol operacional
from app.core.ops_roles import OpsRole  # Enum de roles operacionales
from app.models.attachment import Attachment  # Modelo del adjunto (archivo guardado en BD)
from app.repositories.daily_report_repository import DailyReportRepository  # Repositorio para verificar si el reporte dueño está bloqueado
from app.web.templating import templates  # Motor de templates Jinja compartido

router = APIRouter(prefix="/ops")

# Solo administradores u oficinistas de ingeniería pueden subir/borrar adjuntos
CAN_EDIT = require_ops_role(OpsRole.ADMIN, OpsRole.OFFICE_ENGINEER)
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
# Tipos de "dueño" válidos para un adjunto: un reporte diario o un evento NPT
OWNER_TYPES = {"daily_report", "npt"}


def _ensure_owner_editable(db: Session, owner_type: str, owner_id: str) -> None:
    """If the attachment hangs off a daily report (directly, or an NPT under it),
    block changes when that report is approved/locked."""
    report_id = None
    if owner_type == "daily_report":
        # Si el dueño es directamente el reporte diario, usamos su id tal cual
        report_id = owner_id
    elif owner_type == "npt":
        # Importamos aquí para evitar import circular con el repositorio de NPT
        from app.repositories.npt_repository import NptRepository
        # Buscamos el evento NPT para llegar al reporte diario que lo contiene
        npt = NptRepository(db).get(owner_id)
        report_id = str(npt.daily_report_id) if npt else None
    if report_id:
        # Buscamos el reporte diario dueño (directo o vía NPT)
        rep = DailyReportRepository(db).get(report_id)
        # Si el reporte existe y está bloqueado (aprobado), rechazamos la operación
        if rep is not None and getattr(rep, "is_locked", False):
            raise HTTPException(status_code=423, detail="Report is approved and locked.")


def _list_response(request: Request, db: Session, owner_type: str, owner_id: str) -> HTMLResponse:
    # Consultamos todos los adjuntos de este dueño, ordenados por fecha de creación
    items = db.execute(
        select(Attachment).where(Attachment.owner_type == owner_type, Attachment.owner_id == owner_id)
        .order_by(Attachment.created_at)
    ).scalars().all()
    # Renderizamos el partial con la lista de adjuntos para refrescar la UI
    return templates.TemplateResponse(
        request, "ops/partials/attachments.html",
        {"request": request, "items": items, "owner_type": owner_type, "owner_id": owner_id},
    )


@router.get("/attachments/{owner_type}/{owner_id}", response_class=HTMLResponse)
async def list_attachments(request: Request, owner_type: str, owner_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Validamos que el tipo de dueño sea uno de los soportados
    if owner_type not in OWNER_TYPES:
        raise HTTPException(404)
    # Devolvemos el listado de adjuntos como HTML parcial
    return _list_response(request, db, owner_type, owner_id)


@router.post("/attachments/{owner_type}/{owner_id}", response_class=HTMLResponse)
async def upload_attachment(request: Request, owner_type: str, owner_id: str, file: UploadFile = File(...), caption: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Validamos que el tipo de dueño sea uno de los soportados
    if owner_type not in OWNER_TYPES:
        raise HTTPException(404)
    # Bloqueamos la subida si el reporte dueño ya está aprobado/bloqueado
    _ensure_owner_editable(db, owner_type, owner_id)
    # Leemos el contenido completo del archivo subido
    data = await file.read()
    # Rechazamos archivos que excedan el límite de tamaño
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds 10 MB limit.")
    # Rechazamos archivos vacíos
    if not data:
        raise HTTPException(400, "Empty file.")
    # Creamos y guardamos el registro del adjunto con sus metadatos y los bytes del archivo
    db.add(Attachment(
        owner_type=owner_type, owner_id=owner_id, filename=(file.filename or "file")[:300],
        content_type=file.content_type, size_bytes=len(data), caption=(caption.strip() or None), data=data,
        created_by=current_user.id,
    ))
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la lista actualizada de adjuntos
    return _list_response(request, db, owner_type, owner_id)


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)):
    # Buscamos el adjunto por id
    att = db.get(Attachment, attachment_id)
    if att is None:
        raise HTTPException(404)
    # Mostramos inline solo tipos de imagen rasterizada reales (nunca SVG, que puede contener
    # <script> y se ejecutaría en el origen de la app si se sirve inline); cualquier otro tipo,
    # incluido SVG, se fuerza como descarga. El content_type lo elige el navegador del cliente al
    # subir el archivo, así que no podemos confiar en él para decidir ejecución, solo para el MIME.
    INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
    disposition = "inline" if (att.content_type or "") in INLINE_IMAGE_TYPES else "attachment"
    # Transmitimos los bytes del archivo como respuesta de streaming
    return StreamingResponse(
        io.BytesIO(att.data), media_type=att.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{att.filename}"',
            # Evitamos que el navegador reinterprete/"adivine" el tipo del archivo (MIME sniffing)
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}", response_class=HTMLResponse)
async def delete_attachment(request: Request, attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(CAN_EDIT)):
    # Buscamos el adjunto por id
    att = db.get(Attachment, attachment_id)
    if att is None:
        raise HTTPException(404)
    # Guardamos el tipo y id de dueño antes de borrar, para poder refrescar la lista después
    owner_type, owner_id = att.owner_type, str(att.owner_id)
    # Bloqueamos el borrado si el reporte dueño ya está aprobado/bloqueado
    _ensure_owner_editable(db, owner_type, owner_id)
    # Eliminamos el adjunto
    db.delete(att)
    # Confirmamos la transacción
    db.commit()
    # Devolvemos la lista actualizada de adjuntos
    return _list_response(request, db, owner_type, owner_id)
