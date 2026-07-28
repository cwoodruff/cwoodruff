#!/usr/bin/env python3
"""Update the profile README with latest blog posts, YouTube videos, and repos.

Simplicity-first by design: Python standard library only, no dependencies.
Each source fails soft — if a fetch errors, the existing README section is
left untouched rather than clobbered.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"

BLOG_FEEDS = [
    "https://woodruff.dev/category/blog/feed/",
    "https://woodruff.dev/feed/",  # fallback if the category feed is empty
]
YOUTUBE_FEED = (
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCxPeKO4KK3m2FJevc_3Of2w"
)
SUBSTACK = "https://simplicityfirstphilosophy.substack.com"
NEWSLETTER_FEED = f"{SUBSTACK}/feed"
NEWSLETTER_API = f"{SUBSTACK}/api/v1/archive?sort=new&offset=0&limit=12"
GITHUB_USER = "cwoodruff"
MAX_ITEMS = 5

ATOM = "{http://www.w3.org/2005/Atom}"


BOT_UA = "cwoodruff-profile-updater/1.0 (+https://github.com/cwoodruff)"
# Some hosts (Substack/Cloudflare) reject non-browser agents from datacenter
# IPs with a 403 — retry those with a browser-like identity.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _fetch_once(url: str, ua: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "application/rss+xml, application/atom+xml, "
            "application/xml, text/xml, application/json, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data


def fetch(url: str) -> bytes:
    try:
        return _fetch_once(url, BOT_UA)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 406, 429):
            print(f"fetch: {url} returned {exc.code} with bot UA, "
                  f"retrying with browser UA", file=sys.stderr)
            return _fetch_once(url, BROWSER_UA)
        raise


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%b %d, %Y").replace(" 0", " ")


def parse_rss(raw: bytes) -> list[dict]:
    """Parse an RSS 2.0 feed (WordPress) into [{title, link, date}]."""
    root = ET.fromstring(raw)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        try:
            date = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            date = None
        items.append({"title": title, "link": link, "date": date})
    return items


def parse_atom(raw: bytes) -> list[dict]:
    """Parse a YouTube Atom feed into [{title, link, date}]."""
    root = ET.fromstring(raw)
    items = []
    for entry in root.iter(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        link_el = entry.find(f"{ATOM}link[@rel='alternate']")
        if link_el is None:
            link_el = entry.find(f"{ATOM}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        pub = (entry.findtext(f"{ATOM}published") or "").strip()
        if not title or not link:
            continue
        try:
            date = datetime.fromisoformat(pub)
        except ValueError:
            date = None
        items.append({"title": title, "link": link, "date": date})
    return items


def get_blog_posts() -> list[dict]:
    for url in BLOG_FEEDS:
        try:
            posts = parse_rss(fetch(url))
            if posts:
                return posts[:MAX_ITEMS]
        except Exception as exc:  # noqa: BLE001 — fail soft per source
            print(f"blog: {url} failed: {exc}", file=sys.stderr)
    return []


def parse_substack_api(raw: bytes) -> list[dict]:
    """Parse Substack's public archive JSON into [{title, link, date}]."""
    posts = json.loads(raw)
    items = []
    for p in posts:
        title = (p.get("title") or "").strip()
        link = (p.get("canonical_url") or "").strip()
        pub = (p.get("post_date") or "").strip()
        if not title or not link:
            continue
        try:
            date = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            date = None
        items.append({"title": title, "link": link, "date": date})
    return items


def get_newsletter() -> list[dict]:
    try:
        issues = parse_rss(fetch(NEWSLETTER_FEED))[:MAX_ITEMS]
        if issues:
            return issues
        print("newsletter: RSS feed returned no items", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"newsletter: RSS failed: {exc}", file=sys.stderr)
    try:
        return parse_substack_api(fetch(NEWSLETTER_API))[:MAX_ITEMS]
    except Exception as exc:  # noqa: BLE001
        print(f"newsletter: archive API failed: {exc}", file=sys.stderr)
        return []


def get_videos() -> list[dict]:
    try:
        return parse_atom(fetch(YOUTUBE_FEED))[:MAX_ITEMS]
    except Exception as exc:  # noqa: BLE001
        print(f"youtube: failed: {exc}", file=sys.stderr)
        return []


def get_repos() -> list[dict]:
    url = f"https://api.github.com/users/{GITHUB_USER}/repos?sort=pushed&per_page=100"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            repos = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        print(f"repos: failed: {exc}", file=sys.stderr)
        return []
    picked = []
    for r in repos:
        if r.get("fork") or r.get("archived") or r.get("name") == GITHUB_USER:
            continue
        picked.append(
            {
                "title": r["name"],
                "link": r["html_url"],
                "desc": (r.get("description") or "").strip(),
                "stars": r.get("stargazers_count", 0),
                "date": datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")),
            }
        )
        if len(picked) >= MAX_ITEMS:
            break
    return picked


def md_list(items: list[dict], with_desc: bool = False) -> str:
    lines = []
    for it in items:
        date = f" — <sub>{fmt_date(it['date'])}</sub>" if it.get("date") else ""
        extra = ""
        if with_desc:
            bits = []
            if it.get("desc"):
                bits.append(it["desc"])
            if it.get("stars"):
                bits.append(f"★ {it['stars']}")
            if bits:
                extra = f" — {' · '.join(bits)}"
        lines.append(f"- [{it['title']}]({it['link']}){extra}{date}")
    return "\n".join(lines)


def replace_section(text: str, marker: str, content: str) -> str:
    """Replace content between <!-- MARKER:START --> and <!-- MARKER:END -->."""
    pattern = re.compile(
        rf"(<!-- {marker}:START -->)(.*?)(<!-- {marker}:END -->)", re.DOTALL
    )
    if not pattern.search(text):
        print(f"warning: markers for {marker} not found", file=sys.stderr)
        return text
    return pattern.sub(rf"\g<1>\n{content}\n\g<3>", text)


def main() -> int:
    text = README.read_text(encoding="utf-8")
    original = text

    posts = get_blog_posts()
    if posts:
        text = replace_section(text, "BLOG", md_list(posts))

    issues = get_newsletter()
    if issues:
        text = replace_section(text, "NEWSLETTER", md_list(issues))

    videos = get_videos()
    if videos:
        text = replace_section(text, "VIDEOS", md_list(videos))

    repos = get_repos()
    if repos:
        text = replace_section(text, "REPOS", md_list(repos, with_desc=True))

    if text != original:
        stamp = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
        stamped = re.sub(
            r"(<!-- STAMP:START -->)(.*?)(<!-- STAMP:END -->)",
            rf"\g<1>{stamp}\g<3>",
            text,
            flags=re.DOTALL,
        )
        README.write_text(stamped, encoding="utf-8")
        print(
            f"README updated ({len(posts)} posts, {len(issues)} newsletter issues, "
            f"{len(videos)} videos, {len(repos)} repos)"
        )
    else:
        print("No changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
