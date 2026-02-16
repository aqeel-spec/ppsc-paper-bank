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

## Project Structure

```
ppsc-paper-bank/
├── app/                    # Main application code
│   ├── models/            # Database models
│   ├── routes/            # API routes
│   ├── services/          # Business logic
│   └── utils/             # Utility functions
├── tests/                 # Test files
├── scripts/               # Utility scripts
│   ├── utilities/         # General utilities (seed, flush, etc.)
│   ├── check/             # Validation scripts
│   ├── debug/             # Debugging scripts
│   ├── verify/            # Verification scripts
│   └── migration/         # Database migrations
├── docs/                  # Documentation
├── migrations/            # Database migration files
└── main.py               # Application entry point
```

## Seeding the Database

To populate the database with sample MCQs:

```bash
python scripts/utilities/seed.py
```

## Running Tests

Run all tests:
```bash
pytest
```

Run specific test:
```bash
pytest tests/test_mcq.py
```

See [tests/README.md](tests/README.md) for more testing information.

## Utility Scripts

The project includes various utility scripts organized in the `scripts/` directory:

- **Utilities**: Database seeding, flushing, URL management
- **Check**: Data validation and integrity checks
- **Debug**: Troubleshooting and debugging tools
- **Verify**: Data verification and consistency checks
- **Migration**: Database schema migrations

See [scripts/README.md](scripts/README.md) for detailed usage.

## API Endpoints

- `POST /mcqs/`: Create a new MCQ
- `GET /mcqs/`: List all MCQs
- `GET /mcqs/{id}`: Get a specific MCQ
- `PUT /mcqs/{id}`: Update a MCQ
- `DELETE /mcqs/{id}`: Delete a MCQ

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- Implementation guides
- Feature documentation
- System architecture
- API usage guides

See [docs/README.md](docs/README.md) for the complete documentation index.

## Recent Updates

See [RECENT_UPDATES.md](RECENT_UPDATES.md) for the latest API + AI changes (chat vs stream split, DB cached ai_explanation, roadmap endpoint, embedded agent service).

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
