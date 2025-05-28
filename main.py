# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.mcq import router as mcq_router
from app.database import lifespan

# -----------------------------------------------------------------------------
# App instantiation
# -----------------------------------------------------------------------------
# app = FastAPI(title=)

app = FastAPI(
    lifespan=lifespan,
    title="PPSC MCQ Power Bank",
    version="0.0.1",
)

# -----------------------------------------------------------------------------
# A tiny health-check so you never get a blank 500
# -----------------------------------------------------------------------------
@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok"}

# -----------------------------------------------------------------------------
# CORS (open for now; lock down in production!)
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Your MCQ routes, all under /mcqs
# -----------------------------------------------------------------------------
app.include_router(mcq_router, tags=["MCQs"])

# -----------------------------------------------------------------------------
# Make it runnable with `python main.py`
# -----------------------------------------------------------------------------
# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8000))
#     uvicorn.run(
#         "main:app", 
#         host="0.0.0.0", 
#         port=port, 
#         log_level="info", 
#         reload=True,         # hot-reload on code changes (dev only)
#     )


# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from contextlib import asynccontextmanager

# from app.database import create_db_and_tables
# from app.routes.mcq import router as mcq_router
# from sqlmodel import Session
# from app.database import create_db_and_tables, get_async_session

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # Startup
#     await create_db_and_tables()
#     yield
#     # Shutdown
#     pass



# app = FastAPI(title="PPSC MCQ Power Bank", lifespan=lifespan)



# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(mcq_router, tags=["MCQs"])

# # ——— make it runnable by “python main.py” —————————————
# if __name__ == "__main__":
#     import uvicorn
#     import os
#     # cPanel gives you PORT via env var; default to 8000 if missing
#     port = int(os.environ.get("PORT", 8000))
#     uvicorn.run("main:app", host="0.0.0.0", port=port)