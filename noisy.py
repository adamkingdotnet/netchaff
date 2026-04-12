import argparse
import datetime
import json
import logging
import random
import re
import time
from urllib.parse import quote_plus, urljoin, urlparse

import requests

MAX_RESPONSE_BYTES = 1_000_000  # 1MB - skip pages larger than this
MAX_LINKS = 200  # cap extracted links per page
MAX_BLACKLIST = 5000  # cap blacklist to bound memory

_URL_RE = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

_HREF_RE = re.compile(r"""href=["'](?!#)(.*?)["']""")

_TEMPLATE_RE = re.compile(r"\{(\w+)\}")


def generate_query(search_config):
    """Build a search query by picking a random template and filling its
    {placeholder} slots with random words from the configured word lists.
    When a template uses the same placeholder twice (e.g. "{item} vs {item}"),
    each occurrence gets an independent random pick."""
    templates = search_config["templates"]
    words = search_config["words"]

    template = random.choice(templates)

    def replace_slot(match):
        key = match.group(1)
        word_list = words.get(key)
        if not word_list:
            return match.group(0)
        return random.choice(word_list)

    return _TEMPLATE_RE.sub(replace_slot, template)


class Crawler:
    def __init__(self, config):
        self._config = config
        self._blacklisted = set(config.get("blacklisted_urls", []))
        self._session = requests.Session()
        self._start_time = None
        self._search_config = config.get("search", {})
        self._dry_run = config.get("dry_run", False)
        proxy = config.get("proxy")
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}

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

    class CrawlerTimedOut(Exception):
        pass

    def _request(self, url):
        if self._dry_run:
            logging.info("[dry-run] Would request: %s", url)
            return None
        random_user_agent = random.choice(self._config["user_agents"])
        self._session.headers["user-agent"] = random_user_agent

        response = self._session.get(url, timeout=10, stream=True)

        # check content-length before downloading the body
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_RESPONSE_BYTES:
            response.close()
            return None

        # read up to the limit, then discard
        body = response.content[:MAX_RESPONSE_BYTES]
        response.close()
        return body

    @staticmethod
    def _normalize_link(link, root_url):
        try:
            parsed_url = urlparse(link)
        except ValueError:
            return None
        parsed_root_url = urlparse(root_url)

        if link.startswith("//"):
            return "{}://{}{}".format(
                parsed_root_url.scheme, parsed_url.netloc, parsed_url.path
            )

        if not parsed_url.scheme:
            return urljoin(root_url, link)

        return link

    @staticmethod
    def _is_valid_url(url):
        return _URL_RE.match(url) is not None

    def _is_blacklisted(self, url):
        return any(bl in url for bl in self._blacklisted)

    def _should_accept_url(self, url):
        return url and self._is_valid_url(url) and not self._is_blacklisted(url)

    def _extract_urls(self, body, root_url):
        urls = _HREF_RE.findall(body.decode("utf-8", errors="replace"))
        normalized = [self._normalize_link(url, root_url) for url in urls]
        filtered = [u for u in normalized if self._should_accept_url(u)]
        random.shuffle(filtered)
        return filtered[:MAX_LINKS]

    def _blacklist(self, url):
        if len(self._blacklisted) < MAX_BLACKLIST:
            self._blacklisted.add(url)

    def _is_timeout_reached(self):
        timeout = self._config.get("timeout")
        if not timeout:
            return False
        end_time = self._start_time + datetime.timedelta(seconds=timeout)
        return datetime.datetime.now() >= end_time

    def _human_sleep(self):
        """Sleep with a distribution that mimics human browsing - mostly short
        pauses (scanning/clicking) with occasional longer ones (reading)."""
        if self._dry_run:
            return
        if random.random() < self._read_pause_chance:
            time.sleep(random.uniform(self._max_sleep, self._max_sleep * self._read_pause_multiplier))
        else:
            time.sleep(random.uniform(self._min_sleep, self._max_sleep))

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

    def _do_search(self):
        """Perform a search engine query and follow a few results, mimicking
        a user searching for something and clicking through."""
        query = generate_query(self._search_config)
        engines = self._search_config.get("engines", [])
        if not engines:
            return

        engine = random.choice(engines)
        url = engine.format(quote_plus(query))

        if self._dry_run:
            logging.info("[dry-run] Would search: %s -> %s", query, url)
            return

        logging.info("Searching: %s", query)
        try:
            body = self._request(url)
            if body is None:
                return

            links = self._extract_urls(body, url)
            del body

            self._human_sleep()

            # click 1-3 search results, like a real user would
            clicks = min(random.randint(1, 3), len(links))
            for result_link in random.sample(links, clicks) if links else []:
                if self._is_timeout_reached():
                    raise self.CrawlerTimedOut
                try:
                    logging.info("Search result: %s", result_link)
                    result_body = self._request(result_link)
                    if result_body is None:
                        continue

                    # sometimes follow one link deeper from the result
                    if random.random() < 0.4:
                        sub_links = self._extract_urls(result_body, result_link)
                        del result_body
                        if sub_links:
                            deeper = random.choice(sub_links)
                            logging.info("Following deeper: %s", deeper)
                            self._request(deeper)
                    else:
                        del result_body

                    self._human_sleep()

                except requests.exceptions.RequestException:
                    logging.debug("Search result failed: %s", result_link)

        except requests.exceptions.RequestException:
            logging.debug("Search failed: %s", url)

    def crawl(self):
        self._start_time = datetime.datetime.now()

        while True:
            if self._is_timeout_reached():
                logging.info("Timeout reached, exiting")
                return

            self._randomize_session()

            try:
                if random.random() < self._search_chance:
                    self._do_search()
                else:
                    url = random.choice(self._config["root_urls"])
                    logging.info("Starting new crawl from %s", url)
                    body = self._request(url)
                    if body is None:
                        continue
                    links = self._extract_urls(body, url)
                    del body
                    logging.debug("Found %d links", len(links))
                    self._browse_from_links(links)

                # inter-session pause: sometimes a brief gap, sometimes
                # a longer break like someone stepped away
                if random.random() < self._session_break_chance and not self._dry_run:
                    pause = random.uniform(30, 120)
                    logging.debug("Taking a %.0fs break", pause)
                    time.sleep(pause)

            except requests.exceptions.RequestException as e:
                logging.warning("Root error: %s", e)

            except MemoryError:
                logging.warning("MemoryError, continuing")

            except self.CrawlerTimedOut:
                logging.info("Timeout reached, exiting")
                return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log", metavar="-l", type=str, default="info", help="logging level"
    )
    parser.add_argument(
        "--config", metavar="-c", required=True, type=str, help="config file"
    )
    parser.add_argument(
        "--timeout",
        metavar="-t",
        required=False,
        type=int,
        default=None,
        help="runtime limit in seconds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="log URLs without making requests",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="proxy URL (e.g., http://host:port or socks5://host:port)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper()))

    with open(args.config, "r") as f:
        config = json.load(f)

    if args.timeout:
        config["timeout"] = args.timeout

    if args.dry_run:
        config["dry_run"] = True

    if args.proxy:
        config["proxy"] = args.proxy

    crawler = Crawler(config)
    crawler.crawl()


if __name__ == "__main__":
    main()
