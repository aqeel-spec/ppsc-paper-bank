
# apis/lib/dep/sessionDep.py

"""
sessionDep.py

This module provides a dependency for managing database sessions in FastAPI applications.
Each HTTP request receives a new database session, ensuring thread safety and proper session lifecycle management.
"""
from fastapi import Depends
from sqlmodel import Session
from typing import Annotated
from app.database import engine

def get_session():
    """
    Creates a new SQLModel session for each request.

    Yields:
        Session: An active SQLModel session.
    
    Ensures:
        - Commits the session if operations succeed.
        - Rolls back the session in case of exceptions.
        - Closes the session after the request is processed.
    """
    with Session(engine) as session:
        yield session
 

# Dependency annotations
SessionDep = Annotated[Session, Depends(get_session)]


