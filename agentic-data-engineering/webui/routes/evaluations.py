"""GET /evaluations -- persisted Evaluation entities, optionally filtered by
subject.

Mirrors orchestrator/gate.py's module-private `_stored_evaluations()`
two-line read rather than importing a private symbol -- a deliberate small
duplication, not an oversight.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.enums import EntityType
from persistence.ports import MetadataRepository

from webui.context import get_metadata, get_templates

router = APIRouter()


@router.get("/evaluations")
async def evaluations(
    request: Request,
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    subject: str | None = None,
):
    all_evaluations = [
        Evaluation.model_validate(row.payload) for row in metadata.list(EntityType.EVALUATION)
    ]

    subject_error: str | None = None
    subject_ref: EntityRef | None = None
    if subject:
        try:
            subject_ref = EntityRef.parse(subject)
        except ValueError as exc:
            subject_error = str(exc)

    if subject_ref is not None:
        shown = [
            e
            for e in all_evaluations
            if e.subject_ref.type == subject_ref.type and e.subject_ref.id == subject_ref.id
        ]
    else:
        shown = all_evaluations
    shown.sort(key=lambda e: e.evaluated_at, reverse=True)

    return templates.TemplateResponse(
        request,
        "evaluations.html",
        {
            "evaluations": shown,
            "subject": subject or "",
            "subject_error": subject_error,
        },
        status_code=400 if subject_error else 200,
    )
