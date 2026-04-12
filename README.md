# Noisy

[![CI](https://github.com/adamkingdotnet/noisy/actions/workflows/ci.yml/badge.svg)](https://github.com/adamkingdotnet/noisy/actions/workflows/ci.yml)
[![Docker](https://github.com/adamkingdotnet/noisy/actions/workflows/docker.yml/badge.svg)](https://github.com/adamkingdotnet/noisy/actions/workflows/docker.yml)

A Python script that generates random HTTP/DNS traffic noise in the background while you go about your regular web browsing, to make your web traffic data less valuable for selling and for extra obscurity.

> **Fork of [1tayH/noisy](https://github.com/1tayH/noisy)** with memory stability fixes, template-based search query generation, and human-like browsing patterns.

## What's different from upstream

- **Memory stable** -- Recursive crawling replaced with iterative loop. Responses are size-capped and closed. Blacklist is bounded. No more OOM kills.
- **Search engine queries** -- 30% of activity is search queries on Google/Bing/DuckDuckGo, generated from ~11,000 unique combinations via templates and word lists across 15+ interest categories (cooking, health, finance, travel, pets, DIY, etc.).
- **Human-like patterns** -- Variable crawl depth, mid-session context switching, reading pauses, and inter-session breaks make traffic harder to fingerprint as automated.
- **Config-driven** -- Search templates, word lists, engines, and all crawl parameters live in `config.json`. Expand coverage by adding words or templates, no code changes needed.
- **Modernized** -- Python 3.14, pinned dependencies, pre-compiled regexes, connection reuse via `requests.Session`, no Python 2 compat.

## Getting Started

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

### Standalone

```bash
pip install requests
python noisy.py --config config.json
```

### Command line options

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

## Configuration

All behavior is controlled via `config.json`:

| Key | Description | Default |
|---|---|---|
| `max_depth` | Maximum link depth per crawl session | `15` |
| `min_sleep` / `max_sleep` | Base sleep range between requests (seconds) | `1` / `5` |
| `timeout` | Stop after N seconds, or `false` to run forever | `false` |
| `search_chance` | Probability of doing a search vs. a site crawl | `0.3` |
| `root_urls` | List of sites to start crawls from | -- |
| `blacklisted_urls` | URL substrings to never visit | -- |
| `user_agents` | User-Agent strings to rotate through | -- |
| `search.engines` | Search engine URL templates | Google, Bing, DDG |
| `search.templates` | Query templates with `{placeholder}` slots | 68 templates |
| `search.words` | Word lists keyed by placeholder name | 15 categories, 493 words |

### Adding search queries

Add templates to `search.templates` using `{placeholder}` syntax, and populate the word lists in `search.words`. Each `{placeholder}` is independently filled from its word list at runtime:

```json
{
  "search": {
    "templates": [
      "best {item} for {use_case}",
      "how to {action}",
      "{food} recipe"
    ],
    "words": {
      "item": ["mattress", "headphones", "laptop"],
      "use_case": ["beginners", "travel", "home office"],
      "action": ["patch drywall", "change oil"],
      "food": ["lasagna", "pad thai"]
    }
  }
}
```

This generates queries like "best mattress for travel", "how to change oil", "pad thai recipe", etc.

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

## Authors

* **Itay Hury** -- *Original project* -- [1tayH](https://github.com/1tayH)

See the upstream [contributors](https://github.com/1tayH/noisy/contributors).

## License

This project is licensed under the GNU GPLv3 License -- see the [LICENSE](LICENSE) file for details.
