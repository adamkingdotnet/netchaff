# netchaff

Network infrastructure and server management — chaff scripts, monitoring configs, and utility tooling for managing Adam King's network services.

## Structure

- **`netchaff.py`** — Main source file (single-file project, ~410 lines).
- **`config.json`** — Runtime configuration (targets, intervals, chaff types).
- **`tests/`** — Test suite (`test_netchaff.py`).
- **`examples/`** — Usage examples: `docker-compose/`, `systemd/`.
- **`Dockerfile`** — Container build config.
- **`ruff.toml`** — Linting config. **`mypy.ini`** — Type checking config.

## Commands

| Action | Command |
|--------|---------|
| run | `python3 netchaff.py --config config.json` (`--config` is required) |
| lint | `ruff check .` |
| typecheck | `mypy netchaff.py` |
| test | `pytest tests/` |

## Key Files

- `netchaff.py` — Main source file. All logic lives here.
- `config.json` — Behavior controlled here, not hardcoded.
- `tests/test_netchaff.py` — Test suite.
- `examples/` — Usage examples: `docker-compose/`, `systemd/`.
- `ruff.toml` — Linting config. `mypy.ini` — Type checking config.

## Skip These

- `__pycache__/` — Python cache.
- `*.pyc` — Compiled Python.
- `.venv/` — Python venv (if present).
- `requirements*.txt` — Dependency lists (read only if changing dependencies).

## Patterns

### Code style
- Single-file architecture: all logic in `netchaff.py`.
- Type hints required (mypy strict).
- Config-driven: behavior controlled by `config.json`, not hardcoded values.

## Notes

- Refresh the `user_agents` pool in `config.json` ~quarterly — stale UAs are
  themselves a strong bot fingerprint (last refreshed 2026-08, Chrome 149–151 /
  Firefox 152–153 / Safari 26.5 era).

<!-- Quick-add scratchpad below -->
