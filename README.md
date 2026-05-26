# is4460-dynamic-app-lab-w-security

Simple Django online flower shop application with:

- Homepage
- Product model and full CRUD
- Order model and full CRUD
- Order-to-product many-to-many relationship
- Unit tests for homepage and all CRUD use cases
- Includes Docker build for GitHub Actions

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Apply migrations:

```bash
python manage.py migrate
```

3. Run development server:

```bash
python manage.py runserver
```

4. Run with Docker:

```bash
docker build -t flower-shop .
docker run -p 8000:8000 flower-shop
```

Or using Docker Compose:

```bash
docker compose up --build
```

5. Run unit tests:

```bash
python manage.py test
```

## Codespaces / Dev Container

This repository includes a `.devcontainer/devcontainer.json` configuration that:

- Uses a Python 3.12 development container image
- Installs dependencies on container creation
- Runs initial migrations automatically

VS Code task shortcuts are available in `.vscode/tasks.json`, including `Run Django Unit Tests`.
