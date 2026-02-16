# Tests Directory

This directory contains all test files for the PPSC MCQ Power Bank application.

## Test Files

### Core Tests
- `test_mcq.py` - MCQ model and CRUD operations tests
- `test_basic_imports.py` - Import verification tests
- `conftest.py` - Pytest configuration and fixtures

### Feature Tests
- `test_auto_detection.py` - Auto-detection system tests
- `test_collector.py` - URL collector tests
- `test_updated_collector.py` - Updated collector functionality tests
- `test_discovery_system.py` - Website discovery system tests
- `test_enhanced_system.py` - Enhanced system features tests
- `test_workflow.py` - Workflow integration tests

### Data Integrity Tests
- `test_duplicate_check.py` - Duplicate checking tests
- `test_duplicate_prevention.py` - Duplicate prevention tests
- `test_comprehensive_duplicate_prevention.py` - Comprehensive duplicate prevention tests
- `test_explanations.py` - MCQ explanation tests
- `test_five_plus_options.py` - Five+ options handling tests

### Database Tests
- `test_mysql.py` - MySQL database tests
- `test_tables.py` - Table structure tests
- `test_optimization.py` - Performance optimization tests

### External Service Tests
- `test_pakmcqs.py` - PakMCQs integration tests
- `test_pakmcqs_json.py` - PakMCQs JSON handling tests
- `test_website_data_service.py` - Website data service tests
- `test_website_tracking.py` - Website tracking tests

### Category Tests
- `test_dynamic_categories.py` - Dynamic category system tests

## Running Tests

Run all tests:
```bash
pytest
```

Run specific test file:
```bash
pytest tests/test_mcq.py
```

Run with coverage:
```bash
pytest --cov=app tests/
```

Run with verbose output:
```bash
pytest -v
```

## Test Configuration

Test configuration is defined in:
- `pytest.ini` - Pytest settings
- `conftest.py` - Shared fixtures and test setup
