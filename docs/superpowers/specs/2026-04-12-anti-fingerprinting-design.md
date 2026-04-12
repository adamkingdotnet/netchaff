# Anti-Fingerprinting Improvements Design

**Goal:** Make noisy's traffic harder to distinguish from real browsing by randomizing behavioral parameters per session, varying timing models, and harvesting tracker cookies from visited pages.

**Scope:** Three tightly related changes to `noisy.py` and `config.json`, plus tests and docs.

---

## 1. Per-Session Parameter Randomization

### Problem

Every noisy instance worldwide uses the same fixed parameters: `search_chance: 0.3`, `max_depth: 15`, sleep range `1-5s`, etc. A provider who reads the source can build a classifier that flags traffic matching these exact values.

### Solution

Replace fixed config values with optional `[min, max]` ranges. At the start of each crawl loop iteration, draw fresh values from these ranges into instance attributes.

New method on `Crawler`:

```python
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

Helper method:

```python
def _draw(self, key, default):
    """Return a value for key from config. If the config value is a
    two-element list, draw uniformly from [min, max]. If it's a scalar,
    return it as-is. If missing, return the default."""
    value = self._config.get(key, default)
    if isinstance(value, list) and len(value) == 2:
        return random.uniform(value[0], value[1])
    return value
```

### Backward Compatibility

- If a config value is a single number (old format), it works exactly as before.
- If it's a two-element array `[min, max]`, it draws uniformly from that range.
- Existing `config.json` files remain valid without changes.

### Config Changes

The shipped `config.json` will use range format for all randomizable parameters:

```json
{
  "max_depth": [5, 25],
  "min_sleep": [0.5, 2.0],
  "max_sleep": [3, 8],
  "search_chance": [0.15, 0.45],
  "read_pause_chance": [0.05, 0.25],
  "read_pause_multiplier": [2, 6],
  "context_switch_chance": [0.05, 0.2],
  "session_break_chance": [0.05, 0.15]
}
```

### Code Changes

Replace all references to the hardcoded/config values with the instance attributes set by `_randomize_session()`:

- `self._config["max_depth"]` → `self._max_depth`
- `self._config["min_sleep"]` / `self._config["max_sleep"]` → `self._min_sleep` / `self._max_sleep`
- `self._search_chance` (already an attribute, but now re-drawn each session)
- Hardcoded `0.15` in `_human_sleep` → `self._read_pause_chance`
- Hardcoded `4` in `_human_sleep` → `self._read_pause_multiplier`
- Hardcoded `0.1` context switch in `_browse_from_links` → `self._context_switch_chance`
- Hardcoded `0.1` session break in `crawl()` → `self._session_break_chance`

`_randomize_session()` is called at the top of each iteration of the `while True` loop in `crawl()`, before the search-vs-crawl decision.

---

## 2. Timing Model Variation

### Problem

`_human_sleep` always uses an 85/15 split (85% quick clicks, 15% long reading pauses with a fixed 4x multiplier). This is a fingerprintable constant.

### Solution

This is handled entirely by the per-session randomization above. Each session draws its own:

- `read_pause_chance` from `[0.05, 0.25]` — varies how often long pauses happen (5%–25%)
- `read_pause_multiplier` from `[2, 6]` — varies how long the long pauses are (2x–6x)

The updated `_human_sleep`:

```python
def _human_sleep(self, min_sleep, max_sleep):
    if self._dry_run:
        return
    if random.random() < self._read_pause_chance:
        time.sleep(random.uniform(max_sleep, max_sleep * self._read_pause_multiplier))
    else:
        time.sleep(random.uniform(min_sleep, max_sleep))
```

No additional mechanism needed. Different sessions naturally produce different timing profiles.

---

## 3. Tracker Cookie Harvesting

### Problem

Real browsers accumulate cross-site tracking cookies from ad networks, analytics providers, and social media pixels embedded in pages. Noisy currently ignores these embedded resources, so its traffic lacks the cookie patterns that real browsing produces. Polluting tracker databases with noisy's randomized browsing data would reduce the value of the tracking data.

### Solution

After loading each page, extract URLs from `<script src>`, `<img src>`, and `<iframe src>` attributes that match known tracking domains. Hit a subset of them to accumulate cookies in the session jar.

### New: `_TRACKER_RE` regex

Compiled regex to extract `src` attributes from script, img, and iframe tags:

```python
_TRACKER_RE = re.compile(r"""<(?:script|img|iframe)\s[^>]*?src=["'](https?://[^"']+)["']""", re.IGNORECASE)
```

### New: `_extract_tracker_urls(body, tracker_domains)`

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

### New: `_visit_trackers(tracker_urls)`

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

### Integration Points

Called after each successful page load in:
- `_browse_from_links` — after `_extract_urls` and before `_human_sleep`
- `_do_search` — after loading each search result page

The body is already available at both call sites. Pass it to `_extract_tracker_urls`, then call `_visit_trackers` with the results.

### Dry-run and Proxy Compatibility

Both work automatically:
- `_visit_trackers` calls `self._request()`, which short-circuits in dry-run mode
- The `requests.Session` proxy config applies to all requests including tracker hits

### Cookie Persistence

`requests.Session` automatically stores cookies from `Set-Cookie` headers and replays them on subsequent requests to the same domain. No additional cookie management code is needed. As the crawler visits pages across different sites that embed the same trackers, the session accumulates and replays tracker cookies — exactly the cross-site behavior we want to pollute.

### Config: `tracker_domains`

New config key with ~25 common tracking domains:

```json
{
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
    "t.co",
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
  ]
}
```

Users can expand this list. If `tracker_domains` is empty or missing, tracker harvesting is skipped entirely.

**Note:** `t.co` is currently in `blacklisted_urls`. It should be removed from the blacklist since we now want to visit it for tracker cookie purposes. The blacklist check in `_should_accept_url` applies to link-following, but tracker URLs go through `_visit_trackers` which calls `_request` directly, bypassing the blacklist check. So this is not strictly necessary for functionality, but it's cleaner to remove the conflict.

---

## 4. Files Changed

| File | Changes |
|---|---|
| `noisy.py` | Add `_draw`, `_randomize_session`, `_extract_tracker_urls`, `_visit_trackers`. Add `_TRACKER_RE`. Refactor `_human_sleep`, `_browse_from_links`, `crawl()` to use session attributes. Store `self._tracker_domains` in `__init__`. |
| `config.json` | Convert fixed values to `[min, max]` ranges. Add `read_pause_chance`, `read_pause_multiplier`, `context_switch_chance`, `session_break_chance` ranges. Add `tracker_domains` list. Remove `t.co` from `blacklisted_urls`. |
| `tests/test_noisy.py` | Add `TestRandomization` (test `_draw` with scalar, range, and missing key; test `_randomize_session` produces varying values). Add `TestTrackerHarvesting` (test `_extract_tracker_urls` finds matching domains, ignores non-tracker URLs; test `_visit_trackers` calls `_request` for subset of URLs). |
| `README.md` | Document range-format config, new parameters, tracker harvesting feature. |

---

## 5. What This Does NOT Do

- Does not execute JavaScript (no headless browser)
- Does not generate fake cookies — only accumulates real cookies set by servers
- Does not guarantee tracker pollution — many trackers will reject non-browser requests or require JS for cookie setting. The value is probabilistic.
- Does not add new dependencies
