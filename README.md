# PPSC MCQ Power Bank

A FastAPI-based application for managing Multiple Choice Questions (MCQs) with PostgreSQL database.

## Features

- CRUD operations for MCQs
- PostgreSQL database with SQLModel ORM
- Async database operations
- Input validation
- Automatic API documentation
- Test suite with pytest

## Prerequisites

- Python 3.8 or higher
- PostgreSQL database
- Poetry for dependency management

## Installation

1. Clone the repository
2. Install Poetry if you haven't already:

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. Install dependencies:

   ```bash
   poetry install
   ```

4. Create a PostgreSQL database named `mcq_db`

5. Copy `.env.example` to `.env` and update the database connection string if needed:
   ```bash
   cp .env.example .env
   ```

## Running the Application

1. Activate the virtual environment:

   ```bash
   poetry shell
   ```

2. Run the application:
   ```bash
   uvicorn main:app --reload
   ```

The API will be available at `http://localhost:8000`

## API Documentation

Once the application is running, you can access:

- Swagger UI documentation at `http://localhost:8000/docs`
- ReDoc documentation at `http://localhost:8000/redoc`

## Seeding the Database

To populate the database with sample MCQs:

```bash
python seed.py
```

## Running Tests

```bash
pytest
```

## API Endpoints

- `POST /mcqs/`: Create a new MCQ
- `GET /mcqs/`: List all MCQs
- `GET /mcqs/{id}`: Get a specific MCQ
- `PUT /mcqs/{id}`: Update a MCQ
- `DELETE /mcqs/{id}`: Delete a MCQ

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
