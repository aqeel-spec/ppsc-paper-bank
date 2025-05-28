import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.mcq import MCQ, MCQCreate, Category

def create_test_mcq_data() -> dict:
    return {
        "question_text": "Test question?",
        "option_a": "Option A",
        "option_b": "Option B",
        "option_c": "Option C",
        "option_d": "Option D",
        "correct_answer": "option_a",
        "category": Category.ENGLISH
    }

@pytest.mark.asyncio
async def test_create_mcq(client: AsyncClient, async_session: AsyncSession):
    # 1) Validate input against your create schema
    payload = MCQCreate.model_validate(create_test_mcq_data()).model_dump()

    # 2) Call the endpoint
    response = await client.post("/mcqs/", json=payload)
    assert response.status_code == 201

    body = response.json()
    mcq_id = body["id"]
    assert body["question_text"] == payload["question_text"]
    assert body["category"] == payload["category"]

    # 3) Verify that the record exists in the database
    result = await async_session.get(MCQ, mcq_id)
    assert result is not None
    assert result.question_text == payload["question_text"]
    assert result.category == payload["category"]

