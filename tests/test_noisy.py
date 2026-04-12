import json
import pathlib
from unittest.mock import patch

from noisy import Crawler, generate_query, _TEMPLATE_RE

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
