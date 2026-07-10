# netchaff

<!-- BEGIN working-agreement (vendored from adamkingdotnet/config — edit there, then re-vendor) -->
## Working agreement

These five tenets are non-negotiable:

1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.
2. Simplest solution first. Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.
3. Don't touch unrelated code. If a file or function isn't part of the current task, don't refactor or restyle it just because you'd do it differently. (A bug you encounter isn't "unrelated" — that's tenet 5.)
4. Flag uncertainty explicitly. If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.
5. Extreme ownership. Leave it better than you found it. If you see a defect, you own it — no matter who wrote it or whether it's "yours" to fix. No "not from this session," no "pre-existing," no disowning. Fix it when the fix is small and safe; when it's larger or riskier, surface it plainly and fix it in a scoped, called-out change (or own it and offer to take it on separately). Flag-and-disown is not acceptable — flag-and-fix is.

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

## Shared agent layer

This repo consumes the **`king-agents`** plugin from `adamkingdotnet/config` (auto-enabled via the `extraKnownMarketplaces` + `enabledPlugins` block in the committed `.claude/settings.json`). It provides a **verify-before-done** `Stop` hook that runs this repo's gate — declared in `.claude/king.json` as `ruff check netchaff.py tests/ && mypy netchaff.py && python -m pytest tests/ -v` — and blocks turn-end until it passes (the same "verify before done" rule under **Applies here**, now enforced, not just advised). Permissions live in the committed `.claude/settings.json`, byte-gated to the `python` template — don't hand-edit it; changes belong in the config template, and `settings-check.yml` fails the PR on any drift. Only machine-local grants go in `.claude/settings.local.json` (gitignored). Run `/king:doctor` for a health check (plugin version, gate, agreement/settings drift).
