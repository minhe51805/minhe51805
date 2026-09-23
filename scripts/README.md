# README auto-update

Profile README (`minhe51805/minhe51805`) with a self-refreshing projects table.

## What updates itself

| Block | Mechanism | Refresh |
| :--- | :--- | :--- |
| Stats / Streak / Top Languages | `github-readme-stats` + `github-readme-streak-stats` image endpoints | every page load |
| Star badges in the projects table | `img.shields.io/github/stars/...` | every page load |
| Projects table rows | `scripts/update_readme.py` + GitHub Actions | daily at 03:17 UTC |
| "Last updated" stamp | same workflow | monthly |

The two image-card services do not cache, so stars, commits and streaks are
always live. Only the *list of repositories* and their descriptions is baked
into the file, which is what the workflow regenerates.

## How it works

`README.md` contains two marker pairs. Everything between a pair is owned by the
script and is rewritten on every run:

```markdown
<!-- PROJECTS:START -->
...generated table...
<!-- PROJECTS:END -->

<!-- LAST-UPDATED:START -->
<sub>Last updated: September 2026</sub>
<!-- LAST-UPDATED:END -->
```

The rest of the file is hand written and never touched.

## Local usage

```bash
# preview the regenerated file without writing anything
python scripts/update_readme.py --dry-run

# rewrite README.md in place
python scripts/update_readme.py

# CI guard: exit 1 when README.md is stale
python scripts/update_readme.py --check
```

### Environment variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GITHUB_TOKEN` | *(empty)* | optional, lifts the 60 req/h anonymous API rate limit |
| `README_USERNAME` | `minhe51805` | account to read repositories from |
| `README_PATH` | `README.md` | file to rewrite |

## Adding a new repository

Repositories are picked up automatically on the next run. To control which ones
appear and how they are described, edit the constants at the top of
`scripts/update_readme.py`:

| Constant | Effect |
| :--- | :--- |
| `EXCLUDED` | repos that never appear (coursework, practice, the profile repo itself) |
| `FEATURED_ORDER` | pin these first, in this exact order |
| `CURATED` | hand written name + description, overriding GitHub's own |
| `IGNORED_TOPICS` | topics too generic to render as a badge |
| `LANGUAGE_BADGES` / `TOPIC_BADGES` | badge colours and [simple-icons](https://simpleicons.org) slugs |

Anything missing from `CURATED` still shows up, falling back to the GitHub
description or a generated `<Language> project` line.
