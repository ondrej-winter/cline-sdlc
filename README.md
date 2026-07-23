# cline-sdlc

A Python application for Cline-assisted software development lifecycle workflows.

The project is initialized as an application shell. Business behavior will be added as feature-owned vertical slices.

## Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup

Install the application and development dependencies:

```bash
uv sync --group dev
```

## Quality checks

Format and validate the project with the configured local toolchain:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
```

Install the optional Git pre-commit hooks with:

```bash
uv run pre-commit install
```

## Architecture

Source code uses a `src/` layout and combines vertical feature slices with hexagonal architecture:

```text
src/cline_sdlc/
├── features/       # Business capabilities, each owned end to end
├── shared_kernel/  # Pure domain concepts genuinely shared by slices
└── bootstrap/      # Composition root and dependency wiring
```

Each feature slice may contain these internal layers as needed:

- `domain/`: pure business rules, entities, value objects, and domain errors
- `application/`: use cases, inbound and outbound ports, and boundary DTOs
- `adapters/`: inbound and outbound integrations with external systems

Dependencies point inward: adapters depend on application-owned ports, and the application layer depends on domain behavior.
The first concrete feature should introduce its own slice rather than placing business logic in a global service package.
