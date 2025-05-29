# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.mcq import router as mcq_router
from app.routes.paper import router as paper_router
from app.routes.scrape import router as scrape_router
from app.routes.papers_view import router as papers_view_router
from app.database import lifespan
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)


# -----------------------------------------------------------------------------
# App instantiation
# -----------------------------------------------------------------------------
# app = FastAPI(title=)

app = FastAPI(
    lifespan=lifespan,
    title="PPSC MCQ Power Bank",
    version="0.0.1",
)

# mount your static directory
app.mount(
    "/static",
    StaticFiles(directory="app/utils/static"),
    name="static",
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    # THIS is what you need:
    schema["servers"] = [
       # {"url": "https://ppsc-paper-bank.vercel.app", "description": "Production server"}
       {"url": "http://localhost:8000", "description": "Production server"}
    ]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# A tiny health-check so you never get a blank 500
# -----------------------------------------------------------------------------
@app.get("/", summary="Health check")
async def health_check():
    return {"status": "ok"}


@app.get(
    "/privacy",
    response_class=HTMLResponse,
    summary="Privacy Policy",
    description="Our privacy policy for the PPSC MCQ Power Bank GPT."
)
async def privacy_policy():
    html = """
    <html>
      <head><title>Privacy Policy</title></head>
      <body>
        <h1>Privacy Policy</h1>
        <p><strong>Last updated:</strong> 2025-05-28</p>
        <p>
          This is an educational service provided to help students prepare for exams
          by generating and organizing MCQs. We do <em>not</em> collect any personal
          data unless you explicitly provide it in your questions or requests.
        </p>
        <h2>Data Usage</h2>
        <ul>
          <li>All MCQs and usage logs are stored anonymously for analytics only.</li>
          <li>No personally identifiable information (PII) is retained.</li>
          <li>We do not share your data with third parties.</li>
        </ul>
        <h2>Cookies & Tracking</h2>
        <p>
          We use only essential cookies for session management; no tracking or advertising cookies are used.
        </p>
        <h2>Contact</h2>
        <p>
          If you have any questions about this policy, please contact us at
          <a href="mailto:privacy@ppsc-paper-bank.vercel.app">privacy@ppsc-paper-bank.vercel.app</a>.
        </p>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)

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
app.include_router(paper_router, tags=["Papers"])
app.include_router(scrape_router, tags=["Scraping"])
app.include_router(papers_view_router, tags=["Papers View"])

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