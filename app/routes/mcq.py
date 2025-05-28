from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.mcq import MCQ, MCQCreate, MCQUpdate, MCQBulkCreate, Category

router = APIRouter(prefix="/mcqs")

@router.post(
    "/",
    response_model=MCQ,
    status_code=status.HTTP_201_CREATED
)
async def create_mcq(
    mcq_in: MCQCreate,
    session: Session = Depends(get_async_session)
):
    # 🔄 Replace deprecated from_orm with model_validate:
    db_mcq = MCQ.model_validate(mcq_in)  
    session.add(db_mcq)
    await session.commit()
    await session.refresh(db_mcq)
    return db_mcq


@router.get("/", response_model=List[MCQ])
async def get_mcqs(
    category: Optional[Category] = None,
    session: AsyncSession = Depends(get_async_session),
):
    query = select(MCQ)
    if category:
        query = query.where(MCQ.category == category)

    # use `execute`, not `exec`, on an AsyncSession
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{mcq_id}", response_model=MCQ)
async def get_mcq(
    mcq_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(MCQ).where(MCQ.id == mcq_id))
    mcq = result.scalar_one_or_none()
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")
    return mcq


@router.put("/{mcq_id}", response_model=MCQ)
async def update_mcq(
    mcq_id: int,
    mcq_update: MCQUpdate,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(MCQ).where(MCQ.id == mcq_id))
    db_mcq = result.scalar_one_or_none()
    if not db_mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")

    update_data = mcq_update.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(db_mcq, key, val)

    session.add(db_mcq)
    await session.commit()
    await session.refresh(db_mcq)
    return db_mcq


@router.delete("/{mcq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcq(
    mcq_id: int,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(MCQ).where(MCQ.id == mcq_id))
    mcq = result.scalar_one_or_none()
    if not mcq:
        raise HTTPException(status_code=404, detail="MCQ not found")
    await session.delete(mcq)
    await session.commit()


@router.post("/bulk", response_model=List[MCQ], status_code=status.HTTP_201_CREATED)
async def create_mcqs_bulk(
    mcqs: MCQBulkCreate,
    session: AsyncSession = Depends(get_async_session)
):
    # model_validate here too
    db_mcqs = [MCQ.model_validate(item) for item in mcqs.mcqs]
    session.add_all(db_mcqs)
    await session.commit()
    for obj in db_mcqs:
        await session.refresh(obj)
    return db_mcqs


@router.get("/category/{category}", response_model=List[MCQ])
async def get_mcqs_by_category(
    category: Category,
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(MCQ).where(MCQ.category == category))
    return result.scalars().all()





