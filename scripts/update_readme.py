import os, re, json, requests, feedparser, subprocess
from datetime import datetime, timezone

README = "README.md"

def between(s, start, end, new_block):
    pattern = re.compile(rf"({re.escape(start)})(.*)({re.escape(end)})", re.S)
    return pattern.sub(rf"\1\n{new_block}\n\3", s)

def fmt_item(title, url, meta=None):
    if meta:
        return f"- [{title}]({url})  \n  {meta}"
    return f"- [{title}]({url})"

def fetch_wordpress(feed_url, limit):
    d = feedparser.parse(feed_url)
    items = []
    for e in d.entries[:limit]:
        title = e.title
        link = e.link
        # Prefer published_parsed; fallback gracefully
        date = None
        if getattr(e, "published_parsed", None):
            date = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).date().isoformat()
        elif getattr(e, "updated_parsed", None):
            date = datetime(*e.updated_parsed[:6], tzinfo=timezone.utc).date().isoformat()
        summary = (e.summary or "").strip()
        # Trim summaries a bit
        summary = re.sub("<.*?>", "", summary)
        if len(summary) > 160:
            summary = summary[:157] + "..."
        meta = f"*{date}* — {summary}" if date else summary
        items.append(fmt_item(title, link, meta))
    return "\n".join(items) if items else "_No recent posts_"

def gh_headers():
    pat = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}

def fetch_release_candidates(user, release_repos):
    # If explicit repos supplied, use those. Else list user repos and filter by "has_releases".
    headers = gh_headers()
    repos = []
    if release_repos:
        repos = [r.strip() for r in release_repos.split(",") if r.strip()]
    else:
        page = 1
        while True:
            resp = requests.get(f"https://api.github.com/users/{user}/repos?per_page=100&page={page}", headers=headers, timeout=30)
            if resp.status_code != 200 or not resp.json():
                break
            for r in resp.json():
                repos.append(f"{r['owner']['login']}/{r['name']}")
            page += 1
    return repos

def fetch_latest_releases(repos, limit):
    headers = gh_headers()
    rels = []
    for full in repos:
        owner, name = full.split("/", 1)
        r = requests.get(f"https://api.github.com/repos/{owner}/{name}/releases?per_page=1", headers=headers, timeout=30)
        if r.status_code == 200 and r.json():
            rel = r.json()[0]
            rels.append({
                "repo": full,
                "tag": rel.get("tag_name"),
                "name": rel.get("name") or rel.get("tag_name"),
                "url": rel.get("html_url"),
                "published_at": rel.get("published_at")
            })
    # Sort by published date desc
    rels.sort(key=lambda x: x["published_at"] or "", reverse=True)
    out = []
    for r in rels[:limit]:
        date = r["published_at"][:10] if r["published_at"] else ""
        meta = f"*{date}* — {r['repo']}"
        out.append(fmt_item(r["name"], r["url"], meta))
    return "\n".join(out) if out else "_No recent releases_"

def fetch_linkedin_items(linkedin_rss, linkedin_webhook_cache, limit):
    # Preferred: an RSS feed URL (see notes). Fallback: a JSON cache URL produced by a low-code tool/webhook.
    if linkedin_rss:
        d = feedparser.parse(linkedin_rss)
        items = []
        for e in d.entries[:limit]:
            title = e.title
            link = e.link
            date = None
            if getattr(e, "published_parsed", None):
                date = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).date().isoformat()
            meta = f"*{date}*" if date else None
            items.append(fmt_item(title, link, meta))
        return "\n".join(items) if items else "_No recent issues_"
    elif linkedin_webhook_cache:
        r = requests.get(linkedin_webhook_cache, timeout=30)
        if r.status_code == 200:
            arr = r.json()[:limit]
            items = [fmt_item(x["title"], x["url"], f"*{x.get('date','')}*") for x in arr]
            return "\n".join(items) if items else "_No recent issues_"
    return "_Not configured_"

def main():
    readme = open(README, "r", encoding="utf-8").read()

    limit = int(os.environ.get("ITEMS_PER_SECTION", "10"))

    # WordPress
    wp_feed = os.environ.get("WORDPRESS_FEED")
    wp_block = fetch_wordpress(wp_feed, limit) if wp_feed else "_Not configured_"
    readme = between(readme, "<!-- WP:START -->", "<!-- WP:END -->", wp_block)

    # Releases
    user = os.environ.get("GITHUB_USER")
    rel_repos = os.environ.get("RELEASE_REPOS", "")
    repos = fetch_release_candidates(user, rel_repos)
    rel_block = fetch_latest_releases(repos, limit)
    readme = between(readme, "<!-- REL:START -->", "<!-- REL:END -->", rel_block)

    # LinkedIn
    li_rss = os.environ.get("LINKEDIN_RSS", "")
    li_cache = os.environ.get("LINKEDIN_WEBHOOK_CACHE", "")
    li_block = fetch_linkedin_items(li_rss, li_cache, limit)
    readme = between(readme, "<!-- LI:START -->", "<!-- LI:END -->", li_block)

    with open(README, "w", encoding="utf-8") as f:
        f.write(readme)

if __name__ == "__main__":
    main()
