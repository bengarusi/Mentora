import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.api.dependencies import (
    get_current_student,
    get_material_service,
    get_tutor_service,
)
from app.core.config import settings
from app.core.enums import MaterialKind, SessionMode
from app.files.extraction import SUPPORTED_EXTENSIONS
from app.models.material import StudyMaterial
from app.models.student import Student
from app.schemas.material import (
    MaterialListResponse,
    MaterialResponse,
    MaterialUpdate,
    SupportedFormatsResponse,
)
from app.services.material_service import MaterialService
from app.services.tutor_service import TutorService

log = logging.getLogger("app.api.materialController")

router = APIRouter(prefix="/materials", tags=["materials"])


def _to_response(
    material: StudyMaterial, chunk_count: int | None = None
) -> MaterialResponse:
    """chunk_count isn't a column, so the DTO is built explicitly rather than
    validated straight off the ORM row. List endpoints pass a pre-computed
    count to avoid a lazy load per material."""
    return MaterialResponse(
        **{
            field: getattr(material, field)
            for field in MaterialResponse.model_fields
            if field != "chunk_count"
        },
        chunk_count=(
            chunk_count
            if chunk_count is not None
            else MaterialService.chunk_count(material)
        ),
    )


def _to_list_response(
    rows: list[StudyMaterial], materials: MaterialService
) -> MaterialListResponse:
    counts = materials.materials.chunk_counts_for([m.id for m in rows])
    return MaterialListResponse(
        materials=[_to_response(m, counts.get(m.id, 0)) for m in rows]
    )


@router.get("/supported-formats", response_model=SupportedFormatsResponse)
def get_supported_formats(_: Student = Depends(get_current_student)):
    """Lets the frontend build its file picker from what the server can
    actually read, so the two can't drift apart. Authenticated like every other
    route here, so the API has no unauthenticated surface."""
    return SupportedFormatsResponse(
        extensions=sorted(set(SUPPORTED_EXTENSIONS)),
        max_upload_mb=settings.MATERIAL_MAX_UPLOAD_MB,
    )


@router.get("/{material_id}/file")
def get_material_file(
    material_id: int,
    materials: MaterialService = Depends(get_material_service),
):
    """The original uploaded bytes — lets the student view/download exactly
    what they submitted (a study material or a homework page), not just its
    extracted text. Ownership is enforced the same way every other
    material endpoint does, via MaterialService."""
    data, material = materials.get_file(material_id)
    content_type = material.content_type or "application/octet-stream"
    # Browsers render PDFs, images, and plain text inline; everything else
    # (docx/pptx have no native viewer) downloads instead.
    disposition = "inline" if content_type.startswith(("image/", "application/pdf", "text/")) else "attachment"
    safe_name = material.filename.replace('"', "")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"'},
    )


# ---------------------------------------------------------------------------
# Study materials — persistent, topic-tagged learning resources
# ---------------------------------------------------------------------------

@router.post("/", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def upload_study_material(
    file: UploadFile = File(...),
    subject: str | None = Form(None),
    topic: str | None = Form(None),
    subtopic: str | None = Form(None),
    title: str | None = Form(None),
    materials: MaterialService = Depends(get_material_service),
):
    """Upload one study material. The response carries the extraction status, so
    the client can show whether the file is retrievable yet."""
    data = await file.read()
    material = materials.upload_material(
        data=data,
        filename=file.filename or "upload",
        content_type=file.content_type,
        kind=MaterialKind.STUDY_MATERIAL,
        subject=subject,
        topic=topic,
        subtopic=subtopic,
        title=title,
    )
    return _to_response(material)


@router.get("/", response_model=MaterialListResponse)
def list_study_materials(
    subject: str | None = None,
    topic: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    materials: MaterialService = Depends(get_material_service),
):
    rows = materials.list_study_materials(
        subject=subject, topic=topic, limit=limit, offset=offset
    )
    return _to_list_response(rows, materials)


@router.patch("/{material_id}", response_model=MaterialResponse)
def update_material(
    material_id: int,
    body: MaterialUpdate,
    materials: MaterialService = Depends(get_material_service),
):
    """Re-file a material under a different subject/topic so retrieval can find
    it in the right lessons."""
    return _to_response(materials.update_material(material_id, body))


@router.post("/{material_id}/reprocess", response_model=MaterialResponse)
def reprocess_material(
    material_id: int,
    materials: MaterialService = Depends(get_material_service),
):
    """Retry extraction on a stored file — used after a material was parked as
    unsupported."""
    return _to_response(materials.reprocess(material_id))


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    material_id: int,
    materials: MaterialService = Depends(get_material_service),
):
    materials.delete_material(material_id)


# ---------------------------------------------------------------------------
# Homework files — scoped to one Homework Help session
# ---------------------------------------------------------------------------

@router.post(
    "/homework/{session_id}",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_homework(
    session_id: int,
    file: UploadFile = File(...),
    materials: MaterialService = Depends(get_material_service),
    tutor: TutorService = Depends(get_tutor_service),
):
    """Attach a homework file to a Homework Help session.

    Ownership and mode are checked through TutorService so a homework file can
    never be attached to someone else's session, or to a normal lesson."""
    session = tutor._get_session(session_id)  # 404s unless the student owns it
    if session.mode != SessionMode.HOMEWORK.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Homework files can only be added to a Homework Help session.",
        )

    data = await file.read()
    material = materials.upload_material(
        data=data,
        filename=file.filename or "homework",
        content_type=file.content_type,
        kind=MaterialKind.HOMEWORK,
        subject=session.subject,
        session_id=session_id,
    )
    return _to_response(material)


@router.get("/homework/{session_id}", response_model=MaterialListResponse)
def list_homework(
    session_id: int,
    materials: MaterialService = Depends(get_material_service),
    tutor: TutorService = Depends(get_tutor_service),
):
    tutor._get_session(session_id)  # ownership check
    rows = materials.materials.list_session_materials(session_id)
    return _to_list_response(rows, materials)
