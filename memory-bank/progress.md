# Vinyl Detective - Implementation Progress

## Plan 1: Project Foundation

| Step | Description | Status |
|------|------------|--------|
| 1 | Package structure + requirements + .env.example | Done |
| 2 | config.py (env loader) | Done |
| 3 | db.py - schema init | Pending |
| 4 | db.py - discogs_releases CRUD | Pending |
| 5 | db.py - other tables CRUD | Pending |
| 6 | db.py - FTS5 search | Pending |
| 7 | rate_limiter.py | Pending |
| 8 | __main__.py startup wiring | Pending |
| 9 | Lint + full test pass | Pending |

## Notes

- Using python3.12 (`/usr/bin/python3.12`)
- venv created at `./venv` with python-dotenv, pytest, ruff installed
- Step 2: `config.py` — frozen dataclass `Config` + `load_config()` with dotenv support, missing-key validation. 4 tests passing.
