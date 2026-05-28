"""
Web file scraper — downloads files by extension from one or more pages.

Examples:
  # Single page
  python scraper.py --url https://example.com/files/ --exts ppt doc

  # Multiple pages / sections
  python scraper.py --url https://site.com/a/ --url https://site.com/b/ --exts ppt

  # Crawl internal links (1 level deep, max 100 visited), skip blog-style posts
  python scraper.py --url https://example.com/ --exts ppt --crawl --skip-blog-posts

  # Crawl with a URL regex filter
  python scraper.py --url https://example.com/ --exts ppt --crawl --crawl-filter "/section/"
"""

import argparse
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Shared HTTP session (User-Agent avoids blocking on some servers)
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
)

# WordPress blog-post URLs look like /YYYY/MM/slug/ — useful to skip when
# crawling a WordPress site for file pages.
BLOG_POST_RE = re.compile(r"/\d{4}/\d{2}/")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _normalise(url, base):
    """Resolve relative → absolute and strip query-string / fragment."""
    if not url or url.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
        return None
    absolute = urljoin(base, url)
    parsed = urlparse(absolute)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _filename(url):
    """Extract a file-system-safe filename from *url*."""
    return os.path.basename(unquote(urlparse(url).path)) or None


def _section(url):
    """Return a folder-safe name from a URL path (the trailing segment)."""
    path = unquote(urlparse(url).path).strip("/")
    if not path:
        return ""
    return path.rsplit("/", 1)[-1] or ""


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def _scrape_file_links(html, base_url, extensions):
    """Return [(absolute-url, filename), ...] for every `<a href>` matching
    one of *extensions* (each must include the leading dot)."""
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    results = []

    for a in soup.find_all("a", href=True):
        clean = _normalise(a["href"].strip(), base_url)
        if not clean or clean in seen:
            continue
        seen.add(clean)

        if any(clean.lower().endswith(ext) for ext in extensions):
            fname = _filename(clean)
            if fname:
                results.append((clean, fname))

    return results


def _scrape_internal_pages(html, base_url, extensions, skip_blog, crawl_filter):
    """Return deduplicated list of same-domain page URLs found in *html*."""
    domain = urlparse(base_url).netloc
    soup = BeautifulSoup(html, "lxml")
    pages = set()

    for a in soup.find_all("a", href=True):
        clean = _normalise(a["href"].strip(), base_url)
        if not clean:
            continue

        # Same domain only
        if urlparse(clean).netloc != domain:
            continue

        # Skip if it points directly to a downloadable file
        if any(clean.lower().endswith(e) for e in extensions):
            continue

        # Optionally skip blog-post URLs
        if skip_blog and BLOG_POST_RE.search(clean):
            continue

        # Apply user-supplied URL filter
        if crawl_filter and not crawl_filter.search(clean):
            continue

        pages.add(clean)

    return list(pages)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _download(url, dest, retries=2):
    """Download *url* → *dest* with retries + progress bar. Returns bool."""
    for attempt in range(retries + 1):
        try:
            resp = SESSION.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))

            with open(dest, "wb") as fh, tqdm(
                desc=os.path.basename(dest),
                total=total,
                unit="B",
                unit_scale=True,
                leave=False,
            ) as bar:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
                    bar.update(len(chunk))
            return True

        except (requests.RequestException, OSError) as exc:
            if attempt < retries:
                time.sleep(2)
            else:
                tqdm.write(f"  FAILED  {url}  ({exc})")
    return False


def _resolve_dest(directory, name):
    """If *name* already exists in *directory*, produce ``name(2).ext``, etc."""
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(directory, name)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem}({n}){ext}")
        n += 1
    return candidate


# ---------------------------------------------------------------------------
# Collect phase – visit pages and gather all matching file links
# ---------------------------------------------------------------------------


def _collect(start_urls, extensions, crawl, depth, max_pages, skip_blog, crawl_filter):
    """Walk pages; return OrderedDict {section_name: [(url, filename), …]}."""
    visited = set()
    # queue: (url, section_label, depth)
    queue = [(u, "", 0) for u in start_urls]
    collected = OrderedDict()

    scan = tqdm(desc="Scanning", unit=" pages", total=min(len(start_urls), max_pages or float("inf")))

    while queue:
        url, section, d = queue.pop(0)
        if url in visited:
            continue
        if max_pages and len(visited) >= max_pages:
            break

        visited.add(url)
        scan.update(1)

        # Update total when crawling (total is unknown ahead of time)
        if crawl:
            scan.total = min(len(visited) + len(queue) + 1, max_pages or 99999)

        try:
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            tqdm.write(f"  SKIP  {url}  ({exc})")
            continue

        html = resp.text

        # --- downloadable links on this page ---
        label = section or _section(url) or ""
        links = _scrape_file_links(html, url, extensions)
        if links:
            collected.setdefault(label, []).extend(links)

        # --- crawl deeper ---
        if crawl and d < depth:
            pages = _scrape_internal_pages(html, url, extensions, skip_blog, crawl_filter)
            for p in pages:
                if p not in visited:
                    queue.append((p, _section(p) or "", d + 1))

    scan.close()
    return collected


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        description="Download files from web pages by file extension."
    )
    p.add_argument(
        "--url", required=True, nargs="+",
        help="One or more page URLs to scrape.",
    )
    p.add_argument(
        "--exts", required=True, nargs="+",
        help="Extensions to download (ppt doc zip pdf jpg png …).",
    )
    p.add_argument(
        "--output", default="downloads",
        help="Output root directory.  Default: downloads",
    )
    p.add_argument(
        "--crawl", action="store_true",
        help="Follow internal links on the same domain.",
    )
    p.add_argument(
        "--depth", type=int, default=1,
        help="Max crawl depth.  Default: 1",
    )
    p.add_argument(
        "--max-pages", type=int, default=100,
        help="Max pages to visit when crawling.  Default: 100",
    )
    p.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between downloads.  Default: 1",
    )
    p.add_argument(
        "--ignore-ssl", action="store_true",
        help="Disable SSL certificate verification.",
    )
    p.add_argument(
        "--skip-blog-posts", action="store_true",
        help='Skip crawl URLs matching "/YYYY/MM/" (WordPress blog posts).',
    )
    p.add_argument(
        "--crawl-filter", type=str, default=None,
        help="Regex – only follow internal URLs matching it.",
    )
    return p


def main():
    args = build_parser().parse_args()

    # Normalise extensions
    extensions = [f".{e.lstrip('.')}" for e in args.exts]

    # SSL
    if args.ignore_ssl:
        SESSION.verify = False

    # Crawl filter
    crawl_filter = re.compile(args.crawl_filter) if args.crawl_filter else None

    # -----------------------------------------------------------------------
    # Phase 1 – collect links
    # -----------------------------------------------------------------------
    print(f"Site(s):      {', '.join(args.url)}")
    print(f"Extensions:   {', '.join(extensions)}")
    print(f"Output:       {args.output}")
    if args.crawl:
        flags = [f"depth={args.depth}", f"max={args.max_pages}p"]
        if args.skip_blog_posts:
            flags.append("skip-posts")
        if args.crawl_filter:
            flags.append(f"filter={args.crawl_filter}")
        print(f"Crawl:        {', '.join(flags)}")
    print()

    all_links = _collect(
        args.url, extensions, args.crawl, args.depth,
        args.max_pages, args.skip_blog_posts, crawl_filter,
    )

    total = sum(len(v) for v in all_links.values())
    if total == 0:
        print("No matching files found.")
        return

    print(f"\nFound {total} file(s) in {len(all_links)} section(s).\n")

    # -----------------------------------------------------------------------
    # Phase 2 – download
    # -----------------------------------------------------------------------
    domain = urlparse(args.url[0]).netloc
    base_dir = Path(args.output) / domain

    ok = fail = skip = 0

    for section, links in all_links.items():
        safe_dir = re.sub(r'[<>:"/\\|?*]', "_", section) if section else "root"
        dir_path = base_dir / safe_dir
        dir_path.mkdir(parents=True, exist_ok=True)

        for file_url, file_name in links:
            safe_name = re.sub(r'[<>:"/\\|?*]', "_", file_name)
            dest = _resolve_dest(str(dir_path), safe_name)

            tqdm.write(f"  {safe_dir}/{safe_name}")
            if _download(file_url, dest):
                ok += 1
            else:
                fail += 1

            if args.delay:
                time.sleep(args.delay)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n--- Done ---")
    print(f"  Downloaded: {ok}")
    print(f"  Failed:     {fail}")
    print(f"  Skipped:    {skip}")


if __name__ == "__main__":
    main()
