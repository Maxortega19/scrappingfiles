# AGENTS.md — Scrapping

Python CLI tool to download files by file extension from one or more web pages.  
Supports crawling internal links for sites that spread files across sub-pages.

## Usage

```bash
# Install deps
pip install -r requirements.txt

# Interactive mode (prompts for all inputs)
python scraper.py

# OR via CLI arguments:
python scraper.py --url "https://example.com/files/" --exts ppt doc
python scraper.py --url "https://site.com/a/" --url "https://site.com/b/" --exts ppt
python scraper.py --url "https://9letras.wordpress.com/" --exts ppt --crawl --skip-blog-posts
```

## Project structure

```
scraper.py          # main CLI script — argparse + requests + BeautifulSoup + tqdm
requirements.txt    # requests, beautifulsoup4, lxml, tqdm
downloads/          # default output root (git-ignored)
```

## Architecture notes

- **Single-file script** — no packages, no modules, no separate lib dir.
- **Phases**: collect links (HTTP → parse HTML) then download (stream → disk).
- **Crawl** is opt-in (`--crawl`). Without it only the given URL(s) are scraped.
- **Section folders** are auto-named from the last path segment of the page URL.
- **Dedup**: URLs within the same collect run are deduped; file-path collisions get a numeric suffix.
- **Session**: one `requests.Session` with a browser-like User-Agent for the whole run.

## Usage patterns for 9letras

```bash
# Full site download (all .ppt by section)
python scraper.py --url "https://9letras.wordpress.com/" --exts ppt --crawl --skip-blog-posts

# Single section
python scraper.py --url "https://9letras.wordpress.com/lectoescritura/" --exts ppt

# All .doc and .ppt
python scraper.py --url "https://9letras.wordpress.com/" --exts ppt doc --crawl --skip-blog-posts
```
