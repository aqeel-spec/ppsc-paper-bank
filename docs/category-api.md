# Categories API Architecture

The Categories API handles fetching categories, building nested category trees, and interacting with Multiple Choice Questions (MCQs) assigned to those categories.

## Response Models

Almost all endpoints return data wrapped in a generic `PaginatedResponse` model, which ensures standard metadata is always available to frontend clients.

### `PaginatedResponse[T]`
```json
{
  "message": "success",
  "data": [ ... ], // Array of type T objects
  "page": 1,
  "limit": 10,
  "total_pages": 5,
  "total_items": 45,
  "has_next": true,
  "has_previous": false
}
```

### `CategoryDetailResponse`
The core object structure for categories. Designed to handle both nested hierarchy trees and attached MCQs without overwriting either. FastAPI's `exclude_none=True` ensures empty optional properties are discarded from the final JSON payload.

```typescript
type CategoryDetailResponse = {
  id: number;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  subcategories?: CategoryDetailResponse[]; // Only present if requested and valid
  mcqs?: MCQObject[];                       // Only present on leaf nodes
}
```

---

## Endpoints

### 1. `GET /categories/`
Fetch the root categories (e.g. `English-Mcqs`, `Math-Mcqs`).
- **Parameters**: 
  - `page`: int (default: 1)
  - `limit`: int (default: 10)
  - `include_subcategories`: bool (default: False). If True, maps all immediate subcategories into the `subcategories: []` array of their parent.

### 2. `GET /categories/{slug:path}`
**The Core Hierarchical Lookup Endpoint.** Dynamically alters its response payload based on the position of the requested category within the tree.

- **Parameters**: `page`, `limit`
- **Behavior**:
  - Requires the `{slug:path}` syntax, meaning slashes like `english-mcqs/antonyms-mcqs` are matched entirely as a single `slug` variable.
  - **Intermediate Nodes**: If the requested category has children (i.e. it is a parent node), it returns the category metadata and injects its paginated children into the `subcategories` array. It explicitly deletes the `mcqs` property to prevent loading massive MCQ lists prematurely.
  - **Leaf Nodes**: If the requested category has NO children, it completely drops the `subcategories` array. Instead, it queries the database for MCQs specifically assigned to this category and injects them into a paginated `mcqs` array.

#### Example: Intermediate Node (`/categories/subjectwise/english-mcqs`)
```json
{
  "message": "success",
  "data": [
    {
      "name": "English Mcqs",
      "slug": "subjectwise/english-mcqs",
      "subcategories": [
        { "name": "Antonyms Mcqs", "slug": "subjectwise/english-mcqs/antonyms-mcqs" }
      ]
    }
  ],
  "page": 1, // Pagination applies to the subcategories array
  "total_items": 12
}
```

#### Example: Leaf Node (`/categories/subjectwise/english-mcqs/antonyms-mcqs`)
```json
{
  "message": "success",
  "data": [
    {
      "name": "Antonyms Mcqs",
      "slug": "subjectwise/english-mcqs/antonyms-mcqs",
      "mcqs": [
        { "id": 2951, "question_text": "Antonym of ENTICE is...?" }
      ]
    }
  ],
  "page": 1, // Pagination applies to the mcqs array
  "total_items": 198
}
```

---

### 3. `GET /categories/{slug:path}/subcategories`
Fetches strictly the direct child `subcategories` of a given slug without retrieving the parent object itself, returned flat in the standard `PaginatedResponse` `data` array.

### 4. `GET /categories/slug/{slug:path}`
Fetches the absolute barebones `CategoryResponse` object for a specific slug, entirely bypassing all subcategory relationship mapping and MCQ queries. Ideal for lightweight validity checks or rendering a breadcrumb title.

### 5. `GET /categories/validate-slug/{slug:path}`
Utility endpoint that simply checks boolean existence of a full path slug.
```json
{
  "slug": "subjectwise/english-mcqs/antonyms-mcqs",
  "is_valid": true,
  "message": "Slug 'subjectwise/english-mcqs/antonyms-mcqs' exists in database"
}
```
