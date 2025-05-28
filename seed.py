import asyncio
from app.database import async_session_maker
from app.models.mcq import MCQ, AnswerOption

async def seed_database():
    async with async_session_maker() as session:
        sample_mcqs = [
            MCQ(
                question_text="What is the capital of Pakistan?",
                option_a="Islamabad",
                option_b="Lahore",
                option_c="Karachi",
                option_d="Peshawar",
                correct_answer=AnswerOption.OPTION_A
            ),
            MCQ(
                question_text="Which river is known as the lifeline of Punjab?",
                option_a="Indus",
                option_b="Jhelum",
                option_c="Chenab",
                option_d="Ravi",
                correct_answer=AnswerOption.OPTION_A
            ),
            MCQ(
                question_text="Who was the founder of Pakistan?",
                option_a="Allama Iqbal",
                option_b="Quaid-e-Azam Muhammad Ali Jinnah",
                option_c="Liaquat Ali Khan",
                option_d="Sir Syed Ahmad Khan",
                correct_answer=AnswerOption.OPTION_B
            )
        ]
        
        for mcq in sample_mcqs:
            session.add(mcq)
        
        await session.commit()

if __name__ == "__main__":
    asyncio.run(seed_database())
