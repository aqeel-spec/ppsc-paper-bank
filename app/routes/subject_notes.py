from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models.subject_notes import (
    SubjectPreparationNote,
    SubjectPreparationNoteCreate,
    SubjectPreparationNoteRead,
    SubjectPreparationNoteUpdate,
)
from app.models.user import User
from app.security import require_admin, get_current_user

router = APIRouter(prefix="/api/subject-notes", tags=["Subject Notes"])


@router.get("", response_model=list[SubjectPreparationNoteRead])
def list_subject_notes(
    subject: Optional[str] = Query(default=None),
    visible_only: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    query = select(SubjectPreparationNote)

    if subject:
        query = query.where(SubjectPreparationNote.subject.ilike(f"%{subject}%"))

    if visible_only:
        query = query.where(SubjectPreparationNote.is_visible == True)

    if current_user.role != "admin":
        query = query.where(SubjectPreparationNote.is_visible == True)

    query = query.order_by(SubjectPreparationNote.created_at.desc())
    return db.exec(query).all()


@router.get("/{note_id}", response_model=SubjectPreparationNoteRead)
def get_subject_note(
    note_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    note = db.get(SubjectPreparationNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.is_visible is False and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="This note is not visible to you")

    return note


@router.post("", response_model=SubjectPreparationNoteRead, status_code=201)
def create_subject_note(
    payload: SubjectPreparationNoteCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    note = SubjectPreparationNote(
        title=payload.title.strip(),
        subject=payload.subject.strip(),
        format=(payload.format or "md").strip().lower(),
        summary=payload.summary.strip() if payload.summary else None,
        file_name=payload.file_name.strip() if payload.file_name else None,
        file_url=payload.file_url.strip() if payload.file_url else None,
        content_markdown=payload.content_markdown.strip() if payload.content_markdown else None,
        content_text=payload.content_text.strip() if payload.content_text else None,
        is_visible=bool(payload.is_visible),
        created_by=admin.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/{note_id}", response_model=SubjectPreparationNoteRead)
def update_subject_note(
    note_id: str,
    payload: SubjectPreparationNoteUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    note = db.get(SubjectPreparationNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field == "content_markdown" and value is not None:
            setattr(note, field, str(value).strip())
        elif field in {"title", "subject", "format", "summary", "file_name", "file_url", "content_text"}:
            setattr(note, field, str(value).strip())
        else:
            setattr(note, field, value)

    note.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/{note_id}/visibility")
def update_subject_note_visibility(
    note_id: str,
    is_visible: bool = Query(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    note = db.get(SubjectPreparationNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    note.is_visible = bool(is_visible)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "is_visible": note.is_visible}


@router.delete("/{note_id}", status_code=204)
def delete_subject_note(
    note_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    note = db.get(SubjectPreparationNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()
    return None
