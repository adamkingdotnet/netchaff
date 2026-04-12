# Noisy Fork Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the noisy fork discoverable, credible, and more useful — add CI, GHCR Docker publishing, GitHub topics, proxy support, and a dry-run mode.

**Architecture:** Incremental additions to the existing single-file script. CI and Docker publishing are GitHub Actions workflows. Proxy support threads through the existing `requests.Session`. Dry-run mode intercepts requests at the `_request` level. No new dependencies besides `PySocks` (optional, for SOCKS proxy support).

**Tech Stack:** Python 3.14, requests, PySocks (optional), GitHub Actions, Docker, pytest

---

### Task 1: Remove stale CircleCI config and Dockerfile.pi

The `.circleci/config.yml` tests Python 2.7/3.6/3.7 on defunct CircleCI images. `Dockerfile.pi` uses Python 2.7. Both are dead artifacts from upstream.

**Files:**
- Delete: `.circleci/config.yml`
- Delete: `Dockerfile.pi`

- [ ] **Step 1: Delete stale files**

```bash
git rm .circleci/config.yml Dockerfile.pi
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove stale CircleCI config and Python 2.7 Dockerfile"
```

---

### Task 2: Add basic CI with GitHub Actions

A workflow that installs dependencies, verifies the script imports cleanly, runs unit tests, and does a 15-second live smoke test.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/__init__.py`
- Create: `tests/test_noisy.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_noisy.py`:

```python
import json
import re
from unittest.mock import MagicMock, patch

from noisy import Crawler, generate_query, _TEMPLATE_RE


def _load_config():
    with open("config.json") as f:
        return json.load(f)


class TestGenerateQuery:
    def test_returns_string(self):
        config = _load_config()
        query = generate_query(config["search"])
        assert isinstance(query, str)
        assert len(query) > 0

    def test_no_unfilled_placeholders(self):
        config = _load_config()
        for _ in range(50):
            query = generate_query(config["search"])
            assert not _TEMPLATE_RE.search(query), f"Unfilled placeholder in: {query}"

    def test_missing_word_list_keeps_placeholder(self):
        config = {
            "templates": ["find {nonexistent}"],
            "words": {},
        }
        query = generate_query(config)
        assert query == "find {nonexistent}"


class TestCrawler:
    def test_normalize_link_relative(self):
        result = Crawler._normalize_link("/about", "https://example.com/page")
        assert result == "https://example.com/about"

    def test_normalize_link_protocol_relative(self):
        result = Crawler._normalize_link("//cdn.example.com/img.js", "https://example.com")
        assert result == "https://cdn.example.com/img.js"

    def test_normalize_link_absolute(self):
        result = Crawler._normalize_link("https://other.com/page", "https://example.com")
        assert result == "https://other.com/page"

    def test_normalize_link_invalid(self):
        result = Crawler._normalize_link("://bad", "https://example.com")
        # should not raise, returns something
        assert result is not None

    def test_is_valid_url(self):
        assert Crawler._is_valid_url("https://example.com")
        assert Crawler._is_valid_url("http://example.com/path?q=1")
        assert not Crawler._is_valid_url("notaurl")
        assert not Crawler._is_valid_url("")
        assert not Crawler._is_valid_url("ftp://example.com")

    def test_blacklist_bounded(self):
        config = _load_config()
        crawler = Crawler(config)
        for i in range(6000):
            crawler._blacklist(f"https://example.com/{i}")
        assert len(crawler._blacklisted) <= 5000 + len(config.get("blacklisted_urls", []))

    def test_extract_urls_capped(self):
        config = _load_config()
        crawler = Crawler(config)
        # build HTML with 500 links
        links = "".join(f'<a href="https://example.com/{i}">link</a>' for i in range(500))
        body = f"<html><body>{links}</body></html>".encode()
        urls = crawler._extract_urls(body, "https://example.com")
        assert len(urls) <= 200


class TestDryRun:
    def test_dry_run_logs_without_requests(self):
        config = _load_config()
        config["timeout"] = 5
        config["dry_run"] = True
        config["min_sleep"] = 0
        config["max_sleep"] = 0
        crawler = Crawler(config)
        # should complete without making real HTTP requests
        crawler.crawl()


class TestProxy:
    def test_proxy_config_sets_session_proxies(self):
        config = _load_config()
        config["proxy"] = "http://127.0.0.1:8080"
        crawler = Crawler(config)
        assert crawler._session.proxies["http"] == "http://127.0.0.1:8080"
        assert crawler._session.proxies["https"] == "http://127.0.0.1:8080"

    def test_no_proxy_config_no_proxies(self):
        config = _load_config()
        crawler = Crawler(config)
        assert not crawler._session.proxies
```

- [ ] **Step 2: Create empty `tests/__init__.py`**

```bash
touch tests/__init__.py
```

- [ ] **Step 3: Run tests to verify the import/query/crawler tests pass and dry-run/proxy tests fail**

```bash
python -m pytest tests/test_noisy.py -v
```

Expected: `TestGenerateQuery` and most `TestCrawler` tests PASS. `TestDryRun` and `TestProxy` tests FAIL (features not yet implemented).

- [ ] **Step 4: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          allow-prereleases: true

      - name: Install dependencies
        run: pip install requests pytest

      - name: Run tests
        run: python -m pytest tests/ -v

      - name: Smoke test (15s live run)
        run: python noisy.py --config config.json --timeout 15 --log warning
```

- [ ] **Step 5: Commit**

```bash
git add tests/ .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow with unit tests and smoke test"
```

---

### Task 3: Add dry-run mode

When `dry_run` is set in config or `--dry-run` is passed on the CLI, the crawler logs every URL it would visit without making real HTTP requests. Useful for evaluating the tool before trusting it.

**Files:**
- Modify: `noisy.py`

- [ ] **Step 1: Add `--dry-run` CLI argument**

In the `main()` function, after the `--timeout` argument, add:

```python
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="log URLs without making requests",
    )
```

And after `if args.timeout:`, add:

```python
    if args.dry_run:
        config["dry_run"] = True
```

- [ ] **Step 2: Modify `Crawler.__init__` to store dry_run flag**

Add to the end of `__init__`:

```python
        self._dry_run = config.get("dry_run", False)
```

- [ ] **Step 3: Modify `_request` to short-circuit in dry-run mode**

At the top of `_request`, before the user-agent line, add:

```python
        if self._dry_run:
            logging.info("[dry-run] Would request: %s", url)
            return None
```

- [ ] **Step 4: Modify `_do_search` to log in dry-run mode**

In `_do_search`, after building the `url` variable (the search engine URL), add before the `try:`:

```python
        if self._dry_run:
            logging.info("[dry-run] Would search: %s -> %s", query, url)
            return
```

- [ ] **Step 5: Modify `_human_sleep` to skip sleeping in dry-run mode**

Change `_human_sleep` from a `@staticmethod` to a regular method and add a short-circuit. Replace the method:

```python
    def _human_sleep(self, min_sleep, max_sleep):
        """Sleep with a distribution that mimics human browsing - mostly short
        pauses (scanning/clicking) with occasional longer ones (reading)."""
        if self._dry_run:
            return
        if random.random() < 0.15:
            # 15% chance of a longer "reading" pause
            time.sleep(random.uniform(max_sleep, max_sleep * 4))
        else:
            # quick click-through
            time.sleep(random.uniform(min_sleep, max_sleep))
```

Update the call in `crawl()` for the inter-session pause — wrap the sleep in a dry-run check:

```python
                if random.random() < 0.1 and not self._dry_run:
```

- [ ] **Step 6: Run tests to verify TestDryRun passes**

```bash
python -m pytest tests/test_noisy.py::TestDryRun -v
```

Expected: PASS

- [ ] **Step 7: Manual smoke test**

```bash
python noisy.py --config config.json --dry-run --timeout 10
```

Expected: log lines like `[dry-run] Would request: ...` and `[dry-run] Would search: ...`, no actual HTTP traffic, completes in under a second.

- [ ] **Step 8: Commit**

```bash
git add noisy.py
git commit -m "feat: add --dry-run mode to preview traffic without making requests"
```

---

### Task 4: Add proxy support

Support HTTP and SOCKS proxies via a `proxy` key in config or a `--proxy` CLI flag. Uses `requests`' built-in proxy support (SOCKS requires the optional `PySocks` package).

**Files:**
- Modify: `noisy.py`
- Modify: `README.md`

- [ ] **Step 1: Add `--proxy` CLI argument**

In `main()`, after the `--dry-run` argument, add:

```python
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="proxy URL (e.g., http://host:port or socks5://host:port)",
    )
```

And after the `dry_run` config line:

```python
    if args.proxy:
        config["proxy"] = args.proxy
```

- [ ] **Step 2: Modify `Crawler.__init__` to configure proxy on the session**

After `self._dry_run = ...`, add:

```python
        proxy = config.get("proxy")
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
```

- [ ] **Step 3: Run tests to verify TestProxy passes**

```bash
python -m pytest tests/test_noisy.py::TestProxy -v
```

Expected: PASS

- [ ] **Step 4: Update README with proxy docs**

Add a new section after the Configuration table:

```markdown
### Proxy support

Route all traffic through an HTTP or SOCKS proxy:

```bash
# HTTP proxy
python noisy.py --config config.json --proxy http://127.0.0.1:8080

# SOCKS5 proxy (requires: pip install requests[socks])
python noisy.py --config config.json --proxy socks5://127.0.0.1:1080
```

Or set it in `config.json`:

```json
{
  "proxy": "http://127.0.0.1:8080"
}
```
```

- [ ] **Step 5: Commit**

```bash
git add noisy.py README.md
git commit -m "feat: add proxy support via --proxy flag or config"
```

---

### Task 5: Add GHCR Docker image publishing via GitHub Actions

Publish a multi-platform Docker image to `ghcr.io/adamkingdotnet/noisy` on every push to master.

**Files:**
- Create: `.github/workflows/docker.yml`
- Modify: `Dockerfile` (add `config.json` copy and default CMD)

- [ ] **Step 1: Update Dockerfile to include config and set default CMD**

Replace the Dockerfile contents:

```dockerfile
FROM python:3.14-alpine

RUN pip install --no-cache-dir requests==2.33.1

COPY noisy.py /noisy.py
COPY config.json /config.json

ENTRYPOINT ["python", "/noisy.py"]
CMD ["--config", "/config.json"]
```

- [ ] **Step 2: Create the Docker publish workflow**

Create `.github/workflows/docker.yml`:

```yaml
name: Docker

on:
  push:
    branches: [master]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/setup-buildx-action@v3

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64,linux/arm64
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile .github/workflows/docker.yml
git commit -m "ci: add GHCR Docker image publishing on push to master"
```

---

### Task 6: Add GitHub topics and update README with badges

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Set GitHub topics via CLI**

```bash
gh repo edit --add-topic privacy,traffic-generator,noise,obfuscation,privacy-tools,docker,python
```

- [ ] **Step 2: Add badges to README**

At the top of `README.md`, after the `# Noisy` heading, add:

```markdown
[![CI](https://github.com/adamkingdotnet/noisy/actions/workflows/ci.yml/badge.svg)](https://github.com/adamkingdotnet/noisy/actions/workflows/ci.yml)
[![Docker](https://github.com/adamkingdotnet/noisy/actions/workflows/docker.yml/badge.svg)](https://github.com/adamkingdotnet/noisy/actions/workflows/docker.yml)
```

- [ ] **Step 3: Update README Docker section to mention GHCR**

Replace the Docker getting-started section with:

```markdown
### Docker (recommended)

Pre-built images are available from GitHub Container Registry:

```bash
docker run -d --name noisy --memory=256m ghcr.io/adamkingdotnet/noisy:latest
```

Or build locally:

```bash
docker build -t noisy .
docker run -d --name noisy --memory=256m noisy
```
```

- [ ] **Step 4: Add dry-run to the CLI help section in README**

Update the command line options section to include the new flags:

```
python noisy.py --help
usage: noisy.py [-h] [--log -l] --config -c [--timeout -t] [--dry-run] [--proxy PROXY]

optional arguments:
  -h, --help    show this help message and exit
  --log -l      logging level
  --config -c   config file
  --timeout -t  runtime limit in seconds
  --dry-run     log URLs without making requests
  --proxy PROXY proxy URL (e.g., http://host:port or socks5://host:port)
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add CI/Docker badges, GHCR instructions, and new CLI flags to README"
```

---

## Summary of tasks

| Task | What | Files |
|------|------|-------|
| 1 | Remove stale CircleCI + Py2 Dockerfile | Delete `.circleci/`, `Dockerfile.pi` |
| 2 | CI + unit tests | `.github/workflows/ci.yml`, `tests/` |
| 3 | Dry-run mode | `noisy.py` |
| 4 | Proxy support | `noisy.py`, `README.md` |
| 5 | GHCR Docker publishing | `.github/workflows/docker.yml`, `Dockerfile` |
| 6 | GitHub topics + README badges | `README.md`, `gh repo edit` |
