# Web File Scraper

Downloads files (PPT, DOC, images, PDF, etc.) from web pages by scanning for download links. Supports crawling internal links for sites that spread files across multiple pages or categories.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Interactive mode

```bash
python scraper.py
```

Guides you step by step: URL, file extensions, crawl settings, and download options.

### Command-line mode

```bash
# Single page
python scraper.py --url "https://example.com/files/" --exts ppt doc

# Multiple pages
python scraper.py --url "https://site.com/a/" --url "https://site.com/b/" --exts ppt

# Crawl internal links (follows navigation menu, skips blog posts)
python scraper.py --url "https://9letras.wordpress.com/" --exts ppt --crawl --skip-blog-posts

# Crawl with a filter (only follow URLs matching /section/)
python scraper.py --url "https://example.com/" --exts ppt --crawl --crawl-filter "/section/"
```

### Options

| Argument | Default | Description |
|---|---|---|
| `--url` | — | One or more page URLs to scrape |
| `--exts` | — | Extensions to download (e.g. `ppt doc jpg`) |
| `--output` | `downloads` | Output directory |
| `--crawl` | off | Follow internal links on the same domain |
| `--depth` | `1` | Max crawl depth (levels of links to follow) |
| `--max-pages` | `100` | Max pages to visit when crawling |
| `--delay` | `1.0` | Seconds between downloads |
| `--ignore-ssl` | off | Disable SSL certificate verification |
| `--skip-blog-posts` | off | Skip URLs matching `/YYYY/MM/` (WordPress blog posts) |
| `--crawl-filter` | — | Regex to only follow matching internal URLs |

## Example: 9letras.wordpress.com

Download all `.ppt` files from every section:

```bash
python scraper.py --url "https://9letras.wordpress.com/" --exts ppt --crawl --skip-blog-posts
```

Files are saved to `downloads/9letras.wordpress.com/<section-name>/`.

## Output structure

```
downloads/
└── example.com/
    ├── section-a/
    │   ├── file1.ppt
    │   └── file2.ppt
    ├── section-b/
    │   └── file3.ppt
    └── root/
        └── file4.doc
```
