# Setup — cwoodruff profile README

GitHub renders the README of a repo named **exactly `cwoodruff`** (same as your username) at the top of github.com/cwoodruff.

## Install (5 minutes)

1. Create the repo `cwoodruff/cwoodruff` on GitHub (public). If it already exists, you'll be adding these files to it.
2. Copy everything in this folder into the repo root (`README.md`, `scripts/`, `.github/`), commit, and push to `main`. You can delete this `SETUP.md` after setup.
3. Go to the repo's **Actions** tab → "Update profile README" → **Run workflow**. Within a minute the three dynamic sections fill in and the bot commits the refreshed README.
4. Done. It re-runs every morning at 7:17 AM Eastern, and any push that touches `scripts/` or the workflow file also triggers a refresh.

No secrets to configure — the workflow uses the built-in `GITHUB_TOKEN`, and the blog/YouTube feeds are public.

## How it works

- `scripts/update_readme.py` (Python stdlib only, zero dependencies) pulls:
  - **Blog** — RSS from `woodruff.dev/category/blog/feed/` (falls back to the site-wide feed)
  - **Newsletter** — RSS from `simplicityfirstphilosophy.substack.com/feed`
  - **Videos** — the YouTube channel Atom feed for `UCxPeKO4KK3m2FJevc_3Of2w`
  - **Repos** — GitHub API, your 5 most recently pushed non-fork repos with stars
- It rewrites only the text between the `<!-- BLOG/VIDEOS/REPOS:START/END -->` markers, so you can edit everything else in the README freely.
- Each source fails soft: if a feed is down, that section keeps its previous content and the run still succeeds.
- The workflow commits only when something actually changed.

## Tweaks

- **Item count:** change `MAX_ITEMS` in the script.
- **Schedule:** edit the `cron` line in `.github/workflows/update-profile.yml` (UTC).
- **On-brand extras (from the playbook):** pin htmxRazor, SimplicityTools, both book repos, and ChinookDatabase on your profile; the README's static sections already carry the tagline, bio, three filters, and ecosystem links.
