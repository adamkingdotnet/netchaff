import json
import pathlib
from unittest.mock import MagicMock, patch

from netchaff import Crawler, generate_query, MAX_RESPONSE_BYTES, _TEMPLATE_RE

_REPO_ROOT = pathlib.Path(__file__).parent.parent


def _load_config():
    with open(_REPO_ROOT / "config.json") as f:
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

    def test_normalize_link_protocol_relative_preserves_query(self):
        result = Crawler._normalize_link(
            "//cdn.example.com/i.js?v=2#frag", "https://example.com/page"
        )
        assert result == "https://cdn.example.com/i.js?v=2#frag"

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
        assert len(crawler._blacklisted) <= 5000

    def test_is_blacklisted_pattern_substring(self):
        config = _load_config()
        crawler = Crawler(config)
        # config patterns (e.g. ".png") still match as substrings
        assert crawler._is_blacklisted("https://example.com/logo.png")
        assert not crawler._is_blacklisted("https://example.com/article")

    def test_is_blacklisted_runtime_is_exact(self):
        config = _load_config()
        crawler = Crawler(config)
        crawler._blacklist("https://example.com/dead")
        assert crawler._is_blacklisted("https://example.com/dead")
        # runtime entries match exactly, not as substrings of other URLs
        assert not crawler._is_blacklisted("https://example.com/dead2")

    def test_extract_urls_capped(self):
        config = _load_config()
        crawler = Crawler(config)
        # build HTML with 500 links
        links = "".join(f'<a href="https://example.com/{i}">link</a>' for i in range(500))
        body = f"<html><body>{links}</body></html>".encode()
        urls = crawler._extract_urls(body, "https://example.com")
        assert len(urls) <= 200


class TestRequestCap:
    def test_request_caps_body_without_content_length(self):
        # A response with no content-length header must still be capped at
        # MAX_RESPONSE_BYTES rather than buffered in full.
        config = _load_config()
        crawler = Crawler(config)
        oversized = b"x" * (MAX_RESPONSE_BYTES + 50_000)
        response = MagicMock()
        response.headers = {}  # no content-length
        response.iter_content = lambda chunk_size=8192: (
            oversized[i:i + chunk_size]
            for i in range(0, len(oversized), chunk_size)
        )
        with patch.object(crawler._session, "get", return_value=response):
            body = crawler._request("https://example.com")
        assert len(body) == MAX_RESPONSE_BYTES

    def test_request_skips_oversized_content_length(self):
        config = _load_config()
        crawler = Crawler(config)
        response = MagicMock()
        response.headers = {"content-length": str(MAX_RESPONSE_BYTES + 1)}
        with patch.object(crawler._session, "get", return_value=response):
            assert crawler._request("https://example.com") is None


class TestDryRun:
    def test_dry_run_logs_without_requests(self):
        config = _load_config()
        config["timeout"] = 5
        config["dry_run"] = True
        config["min_sleep"] = 0
        config["max_sleep"] = 0
        crawler = Crawler(config)
        with patch.object(crawler._session, "get") as mock_get:
            crawler.crawl()
            mock_get.assert_not_called()


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
            assert 1 <= mock_req.call_count <= 3

    def test_visit_trackers_noop_with_empty_list(self):
        config = _load_config()
        crawler = Crawler(config)
        with patch.object(crawler, "_request") as mock_req:
            crawler._visit_trackers([])
            mock_req.assert_not_called()
