from app.models.subject_notes import SubjectPreparationNote, SubjectPreparationNoteCreate


def test_subject_note_contract():
    note = SubjectPreparationNote(
        title="Constitutional Law",
        subject="Law",
        format="md",
        content_markdown="# Constitutional Law\n\nKey points",
        is_visible=False,
    )

    assert note.title == "Constitutional Law"
    assert note.subject == "Law"
    assert note.format == "md"
    assert note.is_visible is False


def test_note_create_schema_accepts_file_metadata():
    payload = SubjectPreparationNoteCreate(
        title="Current Affairs",
        subject="General Knowledge",
        format="pdf",
        file_name="current_affairs.pdf",
        file_url="/uploads/current_affairs.pdf",
        summary="Short summary",
    )

    assert payload.file_name == "current_affairs.pdf"
    assert payload.format == "pdf"
    assert payload.subject == "General Knowledge"
