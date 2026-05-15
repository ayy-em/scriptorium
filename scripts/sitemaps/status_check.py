"""CLI and programmatic interface for checking HTTP status of all URLs in a sitemap."""

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path
import random
import sys
import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from core.argparse import ScriptoriumParser
from core.paths import outputs_dir as _core_outputs_dir

TITLE = "Sitemap Status Check"
DESCRIPTION = "Check HTTP status and response times for every URL in a sitemap."

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

_CSV_COLUMNS = ["url", "status_code", "response_time_ms", "content_type", "content_length", "error"]


def _outputs_dir() -> Path:
    """Return the default sitemaps outputs directory, creating it if needed."""
    return _core_outputs_dir("sitemaps")


def _resolve_sitemap_url(url: str) -> str:
    """Ensure the URL points to a sitemap XML resource.

    If the URL already ends with ``.xml``, it is returned as-is. Otherwise the
    path is stripped to the bare origin and ``/sitemap.xml`` is appended.

    Args:
        url: User-provided URL (sitemap URL or bare domain).

    Returns:
        A URL ending in ``.xml``.
    """
    if url.lower().endswith(".xml"):
        return url
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}/sitemap.xml"


def _parse_sitemap_urls(xml_text: str) -> list[str]:
    """Extract ``<loc>`` entries from a sitemap XML document.

    Only processes ``<url><loc>`` entries. If the document is a sitemap index
    (contains ``<sitemap>`` entries instead), a ValueError is raised.

    Args:
        xml_text: Raw XML string of the sitemap.

    Returns:
        List of URL strings found in the sitemap.

    Raises:
        ValueError: If the sitemap is a sitemap index or contains no URLs.
    """
    root = ET.fromstring(xml_text)

    index_entries = root.findall("sm:sitemap", _SITEMAP_NS)
    if index_entries:
        raise ValueError(
            "This is a sitemap index file (contains nested sitemaps). "
            "Only flat sitemaps with <url> entries are supported."
        )

    urls = [loc.text for loc in root.findall(".//sm:url/sm:loc", _SITEMAP_NS) if loc.text]
    if not urls:
        loc_entries = [loc.text for loc in root.findall(".//{*}loc") if loc.text]
        if loc_entries:
            return loc_entries
        raise ValueError("No <url><loc> entries found in sitemap.")
    return urls


def _check_url(
    url: str,
    *,
    timeout: float,
    user_agent: str,
) -> dict[str, str]:
    """Send a GET request to a single URL and return result metadata.

    Args:
        url: The URL to check.
        timeout: Request timeout in seconds.
        user_agent: User-Agent header value.

    Returns:
        Dict with keys matching _CSV_COLUMNS.
    """
    row: dict[str, str] = {
        "url": url,
        "status_code": "",
        "response_time_ms": "",
        "content_type": "",
        "content_length": "",
        "error": "",
    }
    try:
        start = time.monotonic()
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout, allow_redirects=True)
        elapsed_ms = round((time.monotonic() - start) * 1000)
        row["status_code"] = str(resp.status_code)
        row["response_time_ms"] = str(elapsed_ms)
        row["content_type"] = resp.headers.get("Content-Type", "")
        row["content_length"] = resp.headers.get("Content-Length", "")
    except requests.RequestException as exc:
        row["error"] = str(exc)
    return row


def status_check(
    url: str,
    outputs_dir: Path,
    *,
    delay: float = 1.0,
    timeout: float = 10.0,
    user_agent: str = CHROME_USER_AGENT,
) -> Path:
    """Check HTTP status and response times for every URL in a sitemap.

    Fetches the sitemap from the provided URL, extracts all ``<loc>`` entries,
    then issues a GET request to each one. Results are written to a CSV file.

    A random jitter of 0.8x to 1.2x the base delay is applied between requests
    to avoid triggering rate limits.

    Args:
        url: Sitemap URL or bare domain (``/sitemap.xml`` is appended if needed).
        outputs_dir: Directory where the output CSV is written.
        delay: Base delay in seconds between requests (jittered 0.8x-1.2x).
        timeout: Per-request timeout in seconds.
        user_agent: User-Agent header for all requests.

    Returns:
        Path to the output CSV file.

    Raises:
        requests.RequestException: If fetching the sitemap itself fails.
        ValueError: If the sitemap is a sitemap index or contains no URLs.
    """
    sitemap_url = _resolve_sitemap_url(url)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    resp = requests.get(sitemap_url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()

    page_urls = _parse_sitemap_urls(resp.text)

    domain = urlparse(sitemap_url).netloc.replace(":", "_")
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    output_path = outputs_dir / f"status_{domain}_{timestamp}.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for i, page_url in enumerate(page_urls):
            row = _check_url(page_url, timeout=timeout, user_agent=user_agent)
            writer.writerow(row)
            if i < len(page_urls) - 1:
                time.sleep(random.uniform(0.8 * delay, 1.2 * delay))

    return output_path


_EXAMPLES = """
examples:
  uv run main.py sitemaps.status_check https://example.com/sitemap.xml
  uv run main.py sitemaps.status_check https://example.com
  uv run main.py sitemaps.status_check https://example.com --delay 2.0 --timeout 15
  uv run main.py sitemaps.status_check https://example.com/sitemap.xml --user-agent "MyBot/1.0"
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py sitemaps.status_check",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "url",
        ui_label="Sitemap URL",
        help="Sitemap URL or bare domain (appends /sitemap.xml if needed).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        ui_label="Delay (seconds)",
        help="Base delay between requests; actual delay jitters 0.8x-1.2x (default: 1.0).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        ui_label="Timeout (seconds)",
        help="Per-request timeout in seconds (default: 10.0).",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        metavar="STRING",
        ui_label="User-Agent",
        help="Custom User-Agent header (default: current Chrome UA).",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: sitemaps/outputs/).",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to status_check()."""
    args = get_parser().parse_args()

    out_dir = args.outputs or _outputs_dir()
    user_agent = args.user_agent or CHROME_USER_AGENT

    try:
        output = status_check(
            args.url,
            out_dir,
            delay=args.delay,
            timeout=args.timeout,
            user_agent=user_agent,
        )
        print(output)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
