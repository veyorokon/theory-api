# Getting Started

This guide orients you to the core loop and the minimal "steel thread".

## Mental Model

Planner → (propose Transitions) → World  
Executor → (apply Transition) → Ledger (events) → World (artifacts/streams)  
Predicates gate admission/success; Leases ensure safe parallel writes.

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Installation

1. **Clone and setup environment:**
   ```bash
   git clone <repository-url>
   cd backend/
   conda env create -f conda/environment.yml
   conda activate base  # or whatever name you chose
   ```

2. **Start services:**
   ```bash
   docker-compose up -d postgres minio redis
   ```

3. **Run migrations:**
   ```bash
   cd code/
   python manage.py migrate
   ```

4. **Create superuser:**
   ```bash
   python manage.py createsuperuser
   ```

5. **Start development server:**
   ```bash
   python manage.py runserver
   ```

## Smallest Flow

1. Create a Plan facet with one Transition (`tool:text.llm@1`) writing to `world://artifacts/script.json`.
2. Executor reserves budget, acquires a lease, and emits `execution.started`.
3. Adapter invokes the tool (e.g., Modal function). Tool emits progress events and produces an Artifact.
4. Post-predicates pass → `execution.succeeded`; budget settles.

## Storage Example

The storage app demonstrates the adapter pattern:

```python
from apps.storage.service import storage_service
import io

# Upload a file (automatically uses MinIO in dev, S3 in prod)
file_data = io.BytesIO(b"Hello, World!")
url = storage_service.upload_file(
    file=file_data,
    key="documents/hello.txt", 
    bucket="my-bucket"
)
print(f"File uploaded: {url}")
```

## Next Steps

👉 See **Concepts** and **Use Cases** for details on building complex workflows.

- Learn about [World, Plan, and Ledger](../concepts/world-plan-ledger)
- Understand [Facets and Paths](../concepts/facets-and-paths)  
- Explore [Use Cases](../use-cases/media-generation)