# netchaff

<!-- BEGIN working-agreement (vendored from adamkingdotnet/config — edit there, then re-vendor) -->
## Working agreement

These four tenets are non-negotiable:

1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.
2. Simplest solution first. Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.
3. Don't touch unrelated code. If a file or function is not directly part of the current task, do not modify it, even if you think it could be improved.
4. Flag uncertainty explicitly. If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

Operating instructions:

- Keep remote CI/CD green — after pushing **and** after merging. A change isn't done until checks pass on the merged result. (See **Applies here** below for what runs where — some repos gate on PRs only, some have no CI yet.)
- Reach infrastructure directly over SSH (`ssh nas`, `ssh vps`, …) for logs, inspection, and deploys rather than asking for output.
- Drive providers with their own tooling (e.g. `wrangler` for Cloudflare) rather than asking to click through a dashboard.
- Verify implementation specifics against the **latest** upstream docs — don't trust model-ingrained versions or APIs that may be stale; check the live docs first.
<!-- END working-agreement -->
Single-file Python HTTP noise generator: crawls the web issuing randomized search queries to blend real traffic into decoy noise. `config.json`-driven; Python 3.14, runtime dep is `requests` only. Published as `ghcr.io/adamkingdotnet/netchaff`. Config schema and usage live in [README.md](README.md) — don't duplicate them here.

## Code map
- `netchaff.py` — everything. `class Crawler` (the crawl loop + nested `CrawlerTimedOut`), `generate_query()` (builds randomized search strings from config), `main()` / argparse. `__version__` at top.
- `config.json` — DATA, not code. Words/templates/sites the generator draws from.
- `tests/` — pytest suite. `docs/`, `examples/` — supporting material.

## Dev loop
Verbatim from `.github/workflows/ci.yml` (install `pip install -r requirements-dev.txt`):
```
ruff check netchaff.py tests/
mypy netchaff.py
python -m pytest tests/ -v
python netchaff.py --config config.json --timeout 15 --log warning   # 15s smoke run
```

## Conventions
- Extend behavior by adding words/templates/sites to `config.json`, NOT by editing `netchaff.py`.
- The `requests` version lives in 2 files, in two forms: `Dockerfile` (`requests==2.34.2`, exact) and `requirements.txt` (`requests>=2.34.2`, floor). Keep them consistent. (README just says `pip install requests`, no version.)
- Bump `__version__` on releases.

## CI / release
- `ci.yml` and `docker.yml` are thin callers into org reusable workflows (`adamkingdotnet/.github`: `python-check.yml` + `ghcr-publish.yml`).
- Push to `main` runs checks and publishes the ghcr image.

### Applies here
- **CI-green** and **verify-latest**: load-bearing — CI must pass and the ghcr image auto-ships on merge to main.
- **ssh** and **wrangler/Cloudflare**: N/A — no server, no Workers.
- CI lives in `.github/workflows/` (`ci.yml`, `docker.yml`). No CLAUDE.md; this file is canonical.
