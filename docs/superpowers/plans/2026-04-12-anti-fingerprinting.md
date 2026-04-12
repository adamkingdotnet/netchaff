# Anti-Fingerprinting Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make noisy's traffic harder to fingerprint by randomizing behavioral parameters per session, varying timing, and harvesting cross-site tracker cookies.

**Architecture:** Three changes to the single `noisy.py` file: (1) a `_draw` helper + `_randomize_session` method that replaces all hardcoded behavioral constants with per-session random draws from configurable ranges, (2) updated `_human_sleep` to use the drawn parameters, (3) new `_extract_tracker_urls` and `_visit_trackers` methods that parse tracking resource URLs from HTML and hit them to accumulate cookies. Config changes to `config.json` convert fixed values to `[min, max]` ranges and add a `tracker_domains` list.

**Tech Stack:** Python 3.14, requests, pytest

---

## File Structure

| File | Responsibility |
|---|---|
| `noisy.py` | All runtime logic — `_draw`, `_randomize_session`, tracker methods, updated references |
| `config.json` | Range-format parameters, new timing keys, `tracker_domains` list |
| `tests/test_noisy.py` | Unit tests for `_draw`, randomization, tracker extraction |
| `README.md` | Document range config format, new parameters, tracker feature |

---

### Task 1: Add `_draw` helper and `_randomize_session` method

**Files:**
- Modify: `noisy.py:50-61` (Crawler.__init__) and add new methods
- Modify: `tests/test_noisy.py`

- [ ] **Step 1: Write failing tests for `_draw`**

Add to `tests/test_noisy.py`:

```python
class TestRandomization:
    def test_draw_scalar_returns_value(self):
        config = _load_config()
        crawler = Crawler(config)
        # When config has a scalar, _draw returns it as-is
        crawler._config["search_chance"] = 0.3
        assert crawler._draw("search_chance", 0.5) == 0.3

    def test_draw_range_returns_within_bounds(self):
        config = _load_config()
        crawler = Crawler(config)
        crawler._config["search_chance"] = [0.1, 0.9]
        for _ in range(100):
            val = crawler._draw("search_chance", 0.5)
            assert 0.1 <= val <= 0.9

    def test_draw_missing_key_returns_default(self):
        config = _load_config()
        crawler = Crawler(config)
        assert crawler._draw("nonexistent_key", 42) == 42

    def test_randomize_session_varies_values(self):
        config = _load_config()
        config["search_chance"] = [0.1, 0.9]
        config["max_depth"] = [3, 30]
        config["min_sleep"] = [0.5, 2.0]
        config["max_sleep"] = [3, 8]
        config["read_pause_chance"] = [0.05, 0.25]
        config["read_pause_multiplier"] = [2, 6]
        config["context_switch_chance"] = [0.05, 0.2]
        config["session_break_chance"] = [0.05, 0.15]
        crawler = Crawler(config)
        values = set()
        for _ in range(20):
            crawler._randomize_session()
            values.add(round(crawler._search_chance, 4))
        # With 20 draws from [0.1, 0.9], we should see more than 1 unique value
        assert len(values) > 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_noisy.py::TestRandomization -v
```

Expected: FAIL — `_draw` and `_randomize_session` don't exist yet.

- [ ] **Step 3: Implement `_draw` and `_randomize_session`**

Add these two methods to the `Crawler` class, after the `__init__` method (after line 61, before the `CrawlerTimedOut` class):

```python
    def _draw(self, key, default):
        """Return a value for key from config. If the config value is a
        two-element list, draw uniformly from [min, max]. If it's a scalar,
        return it as-is. If missing, return the default."""
        value = self._config.get(key, default)
        if isinstance(value, list) and len(value) == 2:
            return random.uniform(value[0], value[1])
        return value

    def _randomize_session(self):
        """Draw fresh behavioral parameters for this crawl session."""
        self._search_chance = self._draw("search_chance", 0.3)
        self._max_depth = int(self._draw("max_depth", 15))
        self._min_sleep = self._draw("min_sleep", 1)
        self._max_sleep = self._draw("max_sleep", 5)
        self._read_pause_chance = self._draw("read_pause_chance", 0.15)
        self._read_pause_multiplier = self._draw("read_pause_multiplier", 4)
        self._context_switch_chance = self._draw("context_switch_chance", 0.1)
        self._session_break_chance = self._draw("session_break_chance", 0.1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_noisy.py::TestRandomization -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add noisy.py tests/test_noisy.py
git commit -m "feat: add _draw and _randomize_session for per-session parameter variation"
```

---

### Task 2: Wire randomized parameters into crawl logic

Replace all hardcoded behavioral constants and config lookups with the session-randomized attributes.

**Files:**
- Modify: `noisy.py:50-61` (__init__), `noisy.py:132-142` (_human_sleep), `noisy.py:144-192` (_browse_from_links), `noisy.py:218-248` (_do_search), `noisy.py:256-293` (crawl)

- [ ] **Step 1: Update `__init__` — remove `self._search_chance` initialization**

In `Crawler.__init__`, remove this line (currently line 56):

```python
        self._search_chance = config.get("search_chance", 0.3)
```

`_search_chance` will now be set by `_randomize_session()` instead.

- [ ] **Step 2: Update `_human_sleep` to use session attributes**

Replace the `_human_sleep` method with:

```python
    def _human_sleep(self):
        """Sleep with a distribution that mimics human browsing - mostly short
        pauses (scanning/clicking) with occasional longer ones (reading)."""
        if self._dry_run:
            return
        if random.random() < self._read_pause_chance:
            time.sleep(random.uniform(self._max_sleep, self._max_sleep * self._read_pause_multiplier))
        else:
            time.sleep(random.uniform(self._min_sleep, self._max_sleep))
```

Note: the method signature changes from `_human_sleep(self, min_sleep, max_sleep)` to `_human_sleep(self)` — it reads from instance attributes now.

- [ ] **Step 3: Update `_browse_from_links` to use session attributes**

Replace the `_browse_from_links` method with:

```python
    def _browse_from_links(self, links):
        # vary depth per session - sometimes shallow, sometimes deep
        max_depth = random.randint(
            max(1, self._max_depth // 3),
            self._max_depth,
        )

        for depth in range(max_depth):
            if not links:
                logging.debug("Dead end at depth %d, returning to root", depth)
                return

            if self._is_timeout_reached():
                raise self.CrawlerTimedOut

            # occasionally jump to a completely unrelated root mid-crawl
            # this mimics opening a new tab / switching context
            if depth > 0 and random.random() < self._context_switch_chance:
                logging.debug("Context switch at depth %d", depth)
                return

            link = random.choice(links)
            try:
                logging.info("Depth %d: %s", depth, link)
                body = self._request(link)
                if body is None:
                    logging.debug("Skipping oversized page: %s", link)
                    links.remove(link)
                    self._blacklist(link)
                    continue

                new_links = self._extract_urls(body, link)
                del body  # free immediately

                self._human_sleep()

                if len(new_links) > 1:
                    links = new_links
                else:
                    links.remove(link)
                    self._blacklist(link)

            except requests.exceptions.RequestException:
                logging.debug("Request failed: %s", link)
                links = [u for u in links if u != link]
                self._blacklist(link)
```

Changes from current version:
- `self._config["max_depth"]` → `self._max_depth` (lines 146-149)
- `random.random() < 0.1` → `random.random() < self._context_switch_chance` (line 161)
- `self._human_sleep(self._config["min_sleep"], self._config["max_sleep"])` → `self._human_sleep()` (lines 178-181)

- [ ] **Step 4: Update `_do_search` to use session attributes**

Replace the two `self._human_sleep(...)` calls in `_do_search` (currently at lines 218-221 and 245-248):

Change:
```python
            self._human_sleep(
                self._config["min_sleep"],
                self._config["max_sleep"],
            )
```

To (in both locations):
```python
            self._human_sleep()
```

- [ ] **Step 5: Update `crawl()` to call `_randomize_session` and use session attributes**

In the `crawl` method, add `self._randomize_session()` call at the top of the while loop, and replace the hardcoded session break chance:

Replace:
```python
        while True:
            if self._is_timeout_reached():
                logging.info("Timeout reached, exiting")
                return

            try:
                if random.random() < self._search_chance:
```

With:
```python
        while True:
            if self._is_timeout_reached():
                logging.info("Timeout reached, exiting")
                return

            self._randomize_session()

            try:
                if random.random() < self._search_chance:
```

And replace:
```python
                if random.random() < 0.1 and not self._dry_run:
```

With:
```python
                if random.random() < self._session_break_chance and not self._dry_run:
```

- [ ] **Step 6: Run all tests**

```bash
python3 -m pytest tests/test_noisy.py -v
```

Expected: All 17 tests PASS (including the existing 13 + 4 new randomization tests).

- [ ] **Step 7: Commit**

```bash
git add noisy.py
git commit -m "refactor: wire randomized session parameters into all crawl logic"
```

---

### Task 3: Add tracker harvesting

**Files:**
- Modify: `noisy.py` — add `_TRACKER_RE`, `_extract_tracker_urls`, `_visit_trackers`, update `__init__`, `_browse_from_links`, `_do_search`
- Modify: `tests/test_noisy.py` — add `TestTrackerHarvesting`

- [ ] **Step 1: Write failing tests for tracker harvesting**

Add to `tests/test_noisy.py`:

```python
class TestTrackerHarvesting:
    def test_extract_tracker_urls_finds_matching_domains(self):
        config = _load_config()
        config["tracker_domains"] = ["tracker.example.com", "ads.example.com"]
        crawler = Crawler(config)
        html = b'''<html>
        <script src="https://tracker.example.com/t.js"></script>
        <img src="https://ads.example.com/pixel.gif">
        <img src="https://safe.example.com/logo.png">
        <iframe src="https://tracker.example.com/frame"></iframe>
        </html>'''
        urls = crawler._extract_tracker_urls(html, "https://example.com")
        assert len(urls) == 3
        assert all("tracker.example.com" in u or "ads.example.com" in u for u in urls)

    def test_extract_tracker_urls_returns_empty_for_no_trackers(self):
        config = _load_config()
        config["tracker_domains"] = ["tracker.example.com"]
        crawler = Crawler(config)
        html = b'<html><img src="https://safe.example.com/logo.png"></html>'
        urls = crawler._extract_tracker_urls(html, "https://example.com")
        assert urls == []

    def test_extract_tracker_urls_skipped_when_no_domains(self):
        config = _load_config()
        # No tracker_domains key at all
        config.pop("tracker_domains", None)
        crawler = Crawler(config)
        assert crawler._tracker_domains == []

    def test_visit_trackers_calls_request(self):
        config = _load_config()
        config["tracker_domains"] = ["tracker.example.com"]
        config["dry_run"] = True
        crawler = Crawler(config)
        tracker_urls = [
            "https://tracker.example.com/a",
            "https://tracker.example.com/b",
            "https://tracker.example.com/c",
            "https://tracker.example.com/d",
            "https://tracker.example.com/e",
        ]
        with patch.object(crawler, "_request") as mock_req:
            crawler._visit_trackers(tracker_urls)
            # Should call _request 1-3 times (not all 5)
            assert 1 <= mock_req.call_count <= 3

    def test_visit_trackers_noop_with_empty_list(self):
        config = _load_config()
        crawler = Crawler(config)
        with patch.object(crawler, "_request") as mock_req:
            crawler._visit_trackers([])
            mock_req.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_noisy.py::TestTrackerHarvesting -v
```

Expected: FAIL — `_extract_tracker_urls`, `_visit_trackers`, `_tracker_domains` don't exist.

- [ ] **Step 3: Add `_TRACKER_RE` module-level regex**

Add after the `_TEMPLATE_RE` line (currently line 27):

```python
_TRACKER_RE = re.compile(
    r"""<(?:script|img|iframe)\s[^>]*?src=["'](https?://[^"']+)["']""",
    re.IGNORECASE,
)
```

- [ ] **Step 4: Add `self._tracker_domains` to `__init__`**

In `Crawler.__init__`, after the proxy setup block, add:

```python
        self._tracker_domains = config.get("tracker_domains", [])
```

- [ ] **Step 5: Add `_extract_tracker_urls` method**

Add to the `Crawler` class, after `_extract_urls`:

```python
    def _extract_tracker_urls(self, body, root_url):
        """Extract URLs from script/img/iframe src attributes that match
        known tracking domains."""
        text = body.decode("utf-8", errors="replace")
        urls = _TRACKER_RE.findall(text)
        normalized = [self._normalize_link(u, root_url) for u in urls]
        return [
            u for u in normalized
            if u and any(domain in u for domain in self._tracker_domains)
        ]
```

- [ ] **Step 6: Add `_visit_trackers` method**

Add right after `_extract_tracker_urls`:

```python
    def _visit_trackers(self, tracker_urls):
        """Hit 1-3 tracker URLs to accumulate cookies. Failures are silently
        ignored since trackers often reject non-browser clients."""
        if not tracker_urls:
            return
        count = min(random.randint(1, 3), len(tracker_urls))
        for url in random.sample(tracker_urls, count):
            try:
                logging.debug("Tracker: %s", url)
                self._request(url)
            except requests.exceptions.RequestException:
                pass
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_noisy.py::TestTrackerHarvesting -v
```

Expected: All 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add noisy.py tests/test_noisy.py
git commit -m "feat: add tracker URL extraction and cookie harvesting"
```

---

### Task 4: Integrate tracker harvesting into crawl and search paths

**Files:**
- Modify: `noisy.py` — `_browse_from_links`, `_do_search`

- [ ] **Step 1: Add tracker harvesting to `_browse_from_links`**

In `_browse_from_links`, after extracting links and before `del body`, add tracker harvesting. Replace:

```python
                new_links = self._extract_urls(body, link)
                del body  # free immediately
```

With:

```python
                new_links = self._extract_urls(body, link)
                if self._tracker_domains:
                    tracker_urls = self._extract_tracker_urls(body, link)
                    self._visit_trackers(tracker_urls)
                del body  # free immediately
```

- [ ] **Step 2: Add tracker harvesting to `_do_search` — after search page load**

In `_do_search`, after extracting links from the search page and before `del body`, add tracker harvesting. Replace:

```python
            links = self._extract_urls(body, url)
            del body
```

With:

```python
            links = self._extract_urls(body, url)
            if self._tracker_domains:
                tracker_urls = self._extract_tracker_urls(body, url)
                self._visit_trackers(tracker_urls)
            del body
```

- [ ] **Step 3: Add tracker harvesting to `_do_search` — after each search result load**

In `_do_search`, after loading a search result (where `result_body` is available), add tracker harvesting. Replace:

```python
                    # sometimes follow one link deeper from the result
                    if random.random() < 0.4:
                        sub_links = self._extract_urls(result_body, result_link)
                        del result_body
```

With:

```python
                    if self._tracker_domains:
                        result_tracker_urls = self._extract_tracker_urls(result_body, result_link)
                        self._visit_trackers(result_tracker_urls)

                    # sometimes follow one link deeper from the result
                    if random.random() < 0.4:
                        sub_links = self._extract_urls(result_body, result_link)
                        del result_body
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest tests/test_noisy.py -v
```

Expected: All 22 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add noisy.py
git commit -m "feat: integrate tracker harvesting into crawl and search paths"
```

---

### Task 5: Update config.json with range parameters and tracker domains

**Files:**
- Modify: `config.json`

- [ ] **Step 1: Update config.json**

Replace the fixed parameter values at the top of `config.json` with range format, add new timing parameters, and add the `tracker_domains` list. The top of the file should become:

```json
{
  "max_depth": [5, 25],
  "min_sleep": [0.5, 2.0],
  "max_sleep": [3, 8],
  "timeout": false,
  "search_chance": [0.15, 0.45],
  "read_pause_chance": [0.05, 0.25],
  "read_pause_multiplier": [2, 6],
  "context_switch_chance": [0.05, 0.2],
  "session_break_chance": [0.05, 0.15],
  "tracker_domains": [
    "doubleclick.net",
    "google-analytics.com",
    "googleadservices.com",
    "googlesyndication.com",
    "googletagmanager.com",
    "adservice.google.com",
    "facebook.com/tr",
    "connect.facebook.net",
    "facebook.net",
    "ads.linkedin.com",
    "snap.licdn.com",
    "analytics.twitter.com",
    "ads.twitter.com",
    "amazon-adsystem.com",
    "ad.doubleclick.net",
    "adsrvr.org",
    "demdex.net",
    "criteo.com",
    "criteo.net",
    "taboola.com",
    "outbrain.com",
    "scorecardresearch.com",
    "quantserve.com",
    "adnxs.com",
    "rubiconproject.com",
    "pubmatic.com",
    "casalemedia.com"
  ],
```

The rest of the file (`search`, `root_urls`, `blacklisted_urls`, `user_agents`) stays the same.

Also remove `"https://t.co"` from the `blacklisted_urls` array (it conflicts with tracker harvesting — we want to be able to visit tracking redirects).

- [ ] **Step 2: Run all tests to verify config changes don't break anything**

```bash
python3 -m pytest tests/test_noisy.py -v
```

Expected: All 22 tests PASS. Tests that call `_load_config()` now get range values, but `_draw` handles them correctly and `_randomize_session` is only called from `crawl()`.

- [ ] **Step 3: Commit**

```bash
git add config.json
git commit -m "config: convert fixed params to ranges, add tracker domains"
```

---

### Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Configuration table**

Replace the existing configuration table with one that reflects the new range-format parameters and new keys:

```markdown
| Key | Description | Default |
|---|---|---|
| `max_depth` | Maximum link depth per crawl session | `[5, 25]` |
| `min_sleep` / `max_sleep` | Sleep range between requests (seconds) | `[0.5, 2.0]` / `[3, 8]` |
| `timeout` | Stop after N seconds, or `false` to run forever | `false` |
| `search_chance` | Probability of doing a search vs. a site crawl | `[0.15, 0.45]` |
| `read_pause_chance` | Probability of a longer "reading" pause | `[0.05, 0.25]` |
| `read_pause_multiplier` | How much longer reading pauses are vs. normal | `[2, 6]` |
| `context_switch_chance` | Probability of abandoning a crawl mid-session | `[0.05, 0.2]` |
| `session_break_chance` | Probability of a longer break between sessions | `[0.05, 0.15]` |
| `tracker_domains` | Tracking domains to harvest cookies from | 27 domains |
| `root_urls` | List of sites to start crawls from | -- |
| `blacklisted_urls` | URL substrings to never visit | -- |
| `user_agents` | User-Agent strings to rotate through | -- |
| `search.engines` | Search engine URL templates | Google, Bing, DDG |
| `search.templates` | Query templates with `{placeholder}` slots | 68 templates |
| `search.words` | Word lists keyed by placeholder name | 15 categories, 493 words |
```

- [ ] **Step 2: Add a section about parameter randomization**

After the configuration table and before the "Adding search queries" subsection, add:

```markdown
### Parameter randomization

Most behavioral parameters accept either a fixed value or a `[min, max]` range. When a range is provided, each crawl session draws a fresh random value from that range. This makes the traffic pattern vary over time, making it harder to fingerprint as automated.

```json
"search_chance": 0.3          // fixed: always 30%
"search_chance": [0.15, 0.45] // range: 15-45%, randomized per session
```

Existing configs with fixed values continue to work unchanged.
```

- [ ] **Step 3: Add a section about tracker cookie harvesting**

After the "Proxy support" section, add:

```markdown
### Tracker cookie harvesting

Noisy automatically detects tracking pixels, analytics scripts, and ad network resources embedded in visited pages and makes requests to them. This accumulates real cross-site tracking cookies in the session, polluting tracker databases with noisy's randomized browsing data.

Configure which domains to harvest via `tracker_domains` in `config.json`. Set to an empty list to disable:

```json
{
  "tracker_domains": []
}
```
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document parameter randomization, tracker harvesting, and updated config"
```

---

## Task Summary

| Task | What | Files |
|------|------|-------|
| 1 | `_draw` helper + `_randomize_session` method + tests | `noisy.py`, `tests/test_noisy.py` |
| 2 | Wire randomized params into all crawl logic | `noisy.py` |
| 3 | Tracker extraction + visiting methods + tests | `noisy.py`, `tests/test_noisy.py` |
| 4 | Integrate trackers into browse and search paths | `noisy.py` |
| 5 | Update config.json with ranges + tracker domains | `config.json` |
| 6 | Update README | `README.md` |
