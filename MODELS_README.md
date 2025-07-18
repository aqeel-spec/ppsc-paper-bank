# Database Models Documentation

This document describes the database models and their relationships for the PPSC Paper Bank application.

## Model Structure

The application models are now organized into separate files based on their table names for better maintainability and separation of concerns.

### File Organization

```
app/models/
├── __init__.py          # Package initialization and exports
├── base.py             # Base model with common functionality
├── category.py         # Category model and schemas
├── mcqs_bank.py        # MCQ model and schemas
├── paper.py            # Paper model and schemas
├── website.py          # Website configuration model
├── websites.py         # Websites listing model
├── top_bar.py          # Top navigation model
├── side_bar.py         # Side navigation model
└── mcq.py              # Legacy compatibility file
```

### Models and Tables

#### 1. Category (`category` table)

- **Purpose**: Organizes MCQs into categories
- **Fields**: id, slug, name, created_at, updated_at
- **Relationships**: One-to-many with MCQs

#### 2. MCQs Bank (`mcqs_bank` table)

- **Purpose**: Stores multiple choice questions
- **Fields**: id, question_text, option_a, option_b, option_c, option_d, correct_answer, explanation, category_id, created_at, updated_at
- **Relationships**: Many-to-one with Category, Many-to-many with Papers

#### 3. Paper (`paper` table)

- **Purpose**: Represents exam papers or question sets
- **Fields**: id, website_id, title, paper_url, year, paper_type, mcq_links, difficulty, tags, created_at, updated_at
- **Relationships**: Many-to-many with MCQs through PaperMCQ

#### 4. Paper MCQ (`paper_mcq` table)

- **Purpose**: Junction table for Paper-MCQ many-to-many relationship
- **Fields**: paper_id, mcq_id

#### 5. Website (`website` table)

- **Purpose**: Website configuration and scraping state
- **Fields**: web_id, is_top_bar, is_paper_exit, is_side_bar, website_name, paper_urls, pages_count, current_page_url, last_scrapped_url, is_last_completed, created_at, updated_at, ul_config, current_page, total_pages

#### 6. Websites (`websites` table)

- **Purpose**: List of websites to scrape
- **Fields**: id, websites_urls, website_names, current_page_url, created_at, updated_at

#### 7. Top Bar (`top_bar` table)

- **Purpose**: Top navigation configuration
- **Fields**: id, title, names, urls

#### 8. Side Bar (`side_bar` table)

- **Purpose**: Side navigation configuration
- **Fields**: id, tile, names, urls, is_already_exists

### Schema Patterns

Each model follows a consistent pattern with three types of schemas:

1. **Base Model**: The SQLModel table class
2. **Create Schema**: For creating new records (excludes id, timestamps)
3. **Update Schema**: For updating records (all fields optional)
4. **Read Schema**: For API responses (includes all fields)

### Enums

#### CategorySlug

Predefined category slugs:

- `ppsc_all_mcqs_2025`
- `urdu`
- `english`
- `computer`
- `geography`

#### AnswerOption

MCQ answer options:

- `option_a`
- `option_b`
- `option_c`
- `option_d`

### Importing Models

**Recommended way (from package):**

```python
from app.models import MCQ, Category, PaperModel, AnswerOption
```

**Legacy compatibility (still works):**

```python
from app.models.mcq import MCQ, Category  # This imports from the new structure
```

### Relationships

The models use SQLModel relationships for database joins:

- `Category.mcqs` → List of MCQs in this category
- `MCQ.category` → The category this MCQ belongs to
- `PaperModel.paper_mcqs` → List of PaperMCQ junction records
- `PaperMCQ.paper` → The paper this junction belongs to
- `PaperMCQ.mcq` → The MCQ this junction belongs to

### Database Creation

When the application starts, all models are automatically registered with SQLModel metadata through the import in `app/database.py`:

```python
from app.models import *  # This ensures all table models are registered
```

This ensures that `SQLModel.metadata.create_all(engine)` creates all the necessary tables.

### Migration Notes

If you're migrating from the old structure:

1. All imports from `app.models.mcq` will continue to work due to the compatibility layer
2. The table structure remains the same, only the code organization has changed
3. All existing APIs and functionality should work without changes

### Best Practices

1. **Import from package level**: Use `from app.models import ...` instead of individual model files
2. **Use type hints**: All models include proper type hints for better IDE support
3. **Follow naming conventions**: Table names match the class names in snake_case
4. **Use appropriate schemas**: Use Create for input, Read for output, Update for partial updates
