#!/usr/bin/env python3
"""Auto-update the projects table and the last-updated stamp in README.md.

Fetches every public repository owned by ``USERNAME`` from the GitHub REST API,
rebuilds the table located between the ``<!-- PROJECTS:START -->`` and
``<!-- PROJECTS:END -->`` markers, then refreshes the date between the
``<!-- LAST-UPDATED:START -->`` and ``<!-- LAST-UPDATED:END -->`` markers.

The script only depends on the Python standard library so it can run both in
GitHub Actions and on a developer machine.

Usage
-----
    python scripts/update_readme.py              # rewrite README.md
    python scripts/update_readme.py --dry-run    # print, do not write
    python scripts/update_readme.py --check      # exit 1 when README is stale

Environment
-----------
    GITHUB_TOKEN      optional, lifts the anonymous API rate limit
    README_USERNAME   optional, defaults to ``minhe51805``
    README_PATH       optional, defaults to ``README.md``
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

USERNAME = os.environ.get("README_USERNAME", "minhe51805")
README_PATH = os.environ.get("README_PATH", "README.md")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

API_ROOT = "https://api.github.com"
USER_AGENT = f"{USERNAME}-readme-updater"

PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"
UPDATED_START = "<!-- LAST-UPDATED:START -->"
UPDATED_END = "<!-- LAST-UPDATED:END -->"

MAX_STACK_BADGES = 9
SHIELDS = "https://img.shields.io"


def badge(label: str, color: str, logo: str | None = None, logo_color: str | None = None) -> str:
    """Return a flat-square shields.io badge URL."""
    url = f"{SHIELDS}/badge/{label}-{color}?style=flat-square"
    if logo:
        url += f"&logo={logo}"
        if logo_color:
            url += f"&logoColor={logo_color}"
    return url


def stars_badge(repo: str) -> str:
    """Return the star-count badge for ``repo`` (value is fetched by shields.io)."""
    return (
        f"![stars]({SHIELDS}/github/stars/{USERNAME}/{repo}"
        "?style=flat-square&color=f5c542&logo=github&label=%E2%98%85)"
    )


# --------------------------------------------------------------------------- #
# Language / topic -> badge mapping
# --------------------------------------------------------------------------- #

# language -> (label, colour, simple-icons slug, logo colour)
LANGUAGE_BADGES: dict[str, tuple[str, str, str | None, str | None]] = {
    "TypeScript": ("TypeScript", "3178C6", "typescript", "white"),
    "JavaScript": ("JavaScript", "F7DF1E", "javascript", "black"),
    "Python": ("Python", "3776AB", "python", "white"),
    "Dart": ("Dart", "0175C2", "dart", "white"),
    "PHP": ("PHP", "777BB4", "php", "white"),
    "Java": ("Java", "ED8B00", "openjdk", "white"),
    "C#": ("C%23", "512BD4", "dotnet", "white"),
    "C++": ("C%2B%2B", "00599C", "cplusplus", "white"),
    "C": ("C", "A8B9CC", "c", "black"),
    "Rust": ("Rust", "000000", "rust", "white"),
    "Go": ("Go", "00ADD8", "go", "white"),
    "HTML": ("HTML5", "E34F26", "html5", "white"),
    "CSS": ("CSS3", "1572B6", "css", "white"),
    "SCSS": ("SCSS", "CC6699", "sass", "white"),
    "Sass": ("Sass", "CC6699", "sass", "white"),
    "Jupyter Notebook": ("Jupyter", "F37626", "jupyter", "white"),
    "Shell": ("Shell", "4EAA25", "gnubash", "white"),
    "Dockerfile": ("Docker", "2496ED", "docker", "white"),
    "Vue": ("Vue.js", "4FC08D", "vuedotjs", "white"),
    "Svelte": ("Svelte", "FF3E00", "svelte", "white"),
    "Kotlin": ("Kotlin", "7F52FF", "kotlin", "white"),
    "Swift": ("Swift", "F05138", "swift", "white"),
    "Ruby": ("Ruby", "CC342D", "ruby", "white"),
    "Lua": ("Lua", "2C2D72", "lua", "white"),
    "Perl": ("Perl", "39457E", "perl", "white"),
    "R": ("R", "276DC3", "r", "white"),
    "CMake": ("CMake", "064F8C", "cmake", "white"),
    "Blade": ("Blade", "F7523F", "laravel", "white"),
    "GDScript": ("GDScript", "478CBF", "godotengine", "white"),
    "PowerShell": ("PowerShell", "5391FE", None, None),
}

# repository topic -> badge (checked before the language badge is appended)
TOPIC_BADGES: dict[str, tuple[str, str, str | None, str | None]] = {
    "nextjs": ("Next.js", "000000", "nextdotjs", "white"),
    "react": ("React", "61DAFB", "react", "black"),
    "vite": ("Vite", "646CFF", "vite", "white"),
    "fastapi": ("FastAPI", "009688", "fastapi", "white"),
    "express": ("Express", "000000", "express", "white"),
    "tailwindcss": ("Tailwind%20CSS", "06B6D4", "tailwindcss", "white"),
    "nodejs": ("Node.js", "339933", "nodedotjs", "white"),
    "postgresql": ("PostgreSQL", "4169E1", "postgresql", "white"),
    "mongodb": ("MongoDB", "47A248", "mongodb", "white"),
    "mysql": ("MySQL", "4479A1", "mysql", "white"),
    "sqlite": ("SQLite", "003B57", "sqlite", "white"),
    "duckdb": ("DuckDB", "FFF000", "duckdb", "black"),
    "libsql": ("libSQL", "0093A6", None, None),
    "redisdb": ("Redis", "DC382D", "redis", "white"),
    "redis": ("Redis", "DC382D", "redis", "white"),
    "mssql": ("SQL%20Server", "CC2927", None, None),
    "cloudflare-d1": ("Cloudflare%20D1", "F38020", "cloudflare", "white"),
    "flutter": ("Flutter", "02569B", "flutter", "white"),
    "esp32": ("ESP32", "E7352C", "espressif", "white"),
    "arduino": ("Arduino", "00979D", "arduino", "white"),
    "tensorflow": ("TensorFlow", "FF6F00", "tensorflow", "white"),
    "keras": ("Keras", "D00000", "keras", "white"),
    "pytorch": ("PyTorch", "EE4C2C", "pytorch", "white"),
    "machine-learning": ("ML", "FF6F00", "scikitlearn", "white"),
    "ml-classification": ("ML", "FF6F00", "scikitlearn", "white"),
    "blockchain": ("Blockchain", "3C3C3D", "ethereum", "white"),
    "ethereum": ("Blockchain", "3C3C3D", "ethereum", "white"),
    "solidity": ("Solidity", "363636", "solidity", "white"),
    "smart-contract": ("Solidity", "363636", "solidity", "white"),
    "fiware": ("FIWARE", "00528A", None, None),
    "ngsi-ld": ("NGSI--LD", "00528A", None, None),
    "orion-ld": ("Orion-LD", "00528A", None, None),
    "tauri": ("Tauri", "24C8D8", "tauri", "black"),
    "threejs": ("Three.js", "000000", "threedotjs", "white"),
    "webgl": ("WebGL", "990000", "webgl", "white"),
    "nfc": ("NFC", "4A90D9", "nfc", "white"),
    "iot": ("IoT", "E7352C", "espressif", "white"),
    "smart-city": ("Smart%20City", "00528A", None, None),
    "open-data": ("Open%20Data", "2EA44F", "opendatacommons", "white"),
    "geospatial": ("Geospatial", "2EA44F", "openstreetmap", "white"),
    "docker": ("Docker", "2496ED", "docker", "white"),
}

# topics that only describe context, never rendered as a badge
IGNORED_TOPICS = {
    "air-quality", "citizen-reporting", "urban-infrastructure", "portfolio",
    "profile", "readme", "template", "hackathon", "coursework", "university",
}


# --------------------------------------------------------------------------- #
# Curated metadata
# --------------------------------------------------------------------------- #

# Repos that deserve a hand written name/description instead of the raw
# GitHub description. Anything missing here falls back to the API values.
CURATED: dict[str, dict[str, str]] = {
    "UrbanReflex": {
        "name": "UrbanReflex",
        "description": "Open-source smart city platform \u2014 bridges fragmented urban data into a unified NGSI-LD ecosystem",
    },
    "TabLer": {
        "name": "TableR",
        "description": "Cross-platform desktop database client \u2014 explore schemas, write SQL, visualize results, AI-assisted",
    },
    "hdbank_team": {
        "name": "FinLedgerAI",
        "description": "Personalized finance assistant \u2014 ML propensity models, LLM advice, Zalo Bot, on-chain audit trail",
    },
    "Pione_AIBlockchainIoT-WAGTeam": {
        "name": "Pione AI-Blockchain-IoT",
        "description": "Smart farming platform \u2014 IoT sensing, AI analysis, blockchain-verified data",
    },
    "Xaydungtuonglai": {
        "name": "Xaydungtuonglai",
        "description": "PHP web platform with blog, charity, auth and admin dashboard modules",
    },
    "Web3D": {
        "name": "Web3D E-Commerce",
        "description": "Modern e-commerce storefront with interactive 3D product elements",
    },
    "Web_SmartSwitch_BangD": {
        "name": "Smart Switch Control",
        "description": "Web control panel for smart switch devices with 3D model preview",
    },
    "Landing-page-n--c-y-n": {
        "name": "Product Landing Page",
        "description": "Responsive product landing page tuned for mobile, tablet and desktop breakpoints",
    },
    "NFC-master": {
        "name": "NFC Flutter App",
        "description": "Flutter application for NFC card reading and writing",
    },
    "app_web_shopping_228060170": {
        "name": "Shopping App",
        "description": "Flutter shopping application built as a university coursework project",
    },
    "LotusHack-2026": {
        "name": "EduPath",
        "description": "AI study abroad counselor \u2014 every answer grounded in the center's own database, zero hallucinated figures",
    },
    "DACongcu": {
        "name": "CONVOI Platform",
        "description": "Modular multi-purpose PHP platform bundling blog, e-commerce, charity and AI chatbot",
    },
    "mamothon": {
        "name": "Mamothon",
        "description": "Next.js web app with claim flow, contexts and a typed API layer",
    },
    "APP_DMT-phongDEV": {
        "name": "ESP32 CSI Desktop App",
        "description": "PySide6 desktop tool that streams and charts ESP32 CSI sensor data",
    },
}

# Show these first, in this exact order.
FEATURED_ORDER = [
    "UrbanReflex",
    "TabLer",
    "hdbank_team",
    "Pione_AIBlockchainIoT-WAGTeam",
    "Xaydungtuonglai",
    "Web3D",
    "Web_SmartSwitch_BangD",
    "Landing-page-n--c-y-n",
    "NFC-master",
    "app_web_shopping_228060170",
]

# Repos that must never be listed (the profile repo itself, scratch folders...).
EXCLUDED = {
    USERNAME,
    "Profile_cv",
    "copy-mathematical",
    "ser",
    "B1",
    "B2",
    "Ktrgiuakyccvmtrptr",
    "ltw_giuky",
    "baitapccvmtrptr220925",
}


# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #


def api_get(path: str) -> object:
    """GET ``API_ROOT + path`` and decode the JSON body."""
    request = urllib.request.Request(f"{API_ROOT}{path}", headers={"User-Agent": USER_AGENT})
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_repos() -> list[dict]:
    """Return every public, non-fork repository owned by ``USERNAME``."""
    repos: list[dict] = []
    page = 1
    while True:
        batch = api_get(f"/users/{USERNAME}/repos?per_page=100&type=owner&sort=pushed&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    return [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("private")
        and repo.get("name") not in EXCLUDED
    ]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def clean_cell(text: str) -> str:
    """Make ``text`` safe to embed inside a markdown table cell."""
    return text.replace("|", "/").replace("\r", " ").replace("\n", " ").strip()


def stack_badges(repo: dict) -> list[str]:
    """Build the ordered, de-duplicated badge list for one repository."""
    seen: set[str] = set()
    out: list[str] = []

    def push(spec: tuple[str, str, str | None, str | None]) -> None:
        label, color, logo, logo_color = spec
        if label in seen:
            return
        seen.add(label)
        out.append(f"![{label}]({badge(label, color, logo, logo_color)})")

    for topic in repo.get("topics") or []:
        topic = topic.lower()
        if topic in IGNORED_TOPICS:
            continue
        spec = TOPIC_BADGES.get(topic)
        if spec:
            push(spec)
        if len(out) >= MAX_STACK_BADGES:
            return out

    language = repo.get("language")
    if language:
        push(LANGUAGE_BADGES.get(language, (language.replace(" ", "%20"), "555555", None, None)))

    return out[:MAX_STACK_BADGES]


def fallback_description(repo: dict) -> str:
    """Build a readable description when the repo has none on GitHub."""
    language = repo.get("language")
    topics = [t for t in (repo.get("topics") or []) if t not in IGNORED_TOPICS]

    if topics:
        pretty = ", ".join(t.replace("-", " ") for t in topics[:3])
        return f"Public {language or 'code'} project focused on {pretty}"

    if language:
        return f"Public {language} project"

    return "Public project"


def sort_key(repo: dict) -> tuple:
    """Featured repos first (in FEATURED_ORDER), then stars, then recency."""
    name = repo["name"]
    featured = FEATURED_ORDER.index(name) if name in FEATURED_ORDER else len(FEATURED_ORDER)
    return (featured, -repo.get("stargazers_count", 0), repo.get("pushed_at") or "")



def render_table(repos: list[dict]) -> str:
    """Render the full markdown block (table + link) for the projects section."""
    lines = [
        "| Project | Description | Stack |",
        "| :--- | :--- | :--- |",
    ]

    for repo in sorted(repos, key=sort_key):
        name = repo["name"]
        meta = CURATED.get(name, {})
        title = meta.get("name", name)
        description = meta.get("description") or repo.get("description") or fallback_description(repo)
        stack = " ".join(stack_badges(repo)) or "\u2014"
        lines.append(
            f"| {stars_badge(name)}<br/>[**{clean_cell(title)}**]"
            f"(https://github.com/{USERNAME}/{name}) "
            f"| {clean_cell(description)} | {stack} |"
        )

    lines.append("")
    lines.append(
        f"<sub>[See all repositories \u2192](https://github.com/{USERNAME}?tab=repositories)</sub>"
    )
    return "\n".join(lines)


def render_stamp(now: datetime) -> str:
    """Return the 'last updated' line for the footer.

    Month granularity keeps the repository quiet: the stamp only changes once
    per month instead of producing a commit on every single day.
    """
    return f"<sub>Last updated: {now:%B %Y}</sub>"


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #


def replace_block(text: str, start: str, end: str, payload: str) -> tuple[str, bool]:
    """Replace the content between ``start`` and ``end``. Returns (text, changed)."""
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"marker pair not found in README: {start} ... {end}")
    updated = pattern.sub(lambda _: f"{start}\n{payload}\n{end}", text, count=1)
    return updated, updated != text



# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the result instead of writing")
    parser.add_argument("--check", action="store_true", help="exit 1 when README.md is out of date")
    parser.add_argument("--path", default=README_PATH, help="path to the README file")
    args = parser.parse_args()

    # Windows consoles default to a legacy code page; force UTF-8 so emoji and
    # arrows in the generated markdown never crash the run.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    with open(args.path, encoding="utf-8") as handle:
        original = handle.read()

    try:
        repos = fetch_repos()
    except Exception as exc:  # network hiccup, rate limit, ...
        print(f"error: could not fetch repositories from GitHub ({exc})", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)

    updated, table_changed = replace_block(
        original, PROJECTS_START, PROJECTS_END, render_table(repos)
    )
    updated, stamp_changed = replace_block(updated, UPDATED_START, UPDATED_END, render_stamp(now))
    changed = table_changed or stamp_changed

    print(f"repositories considered : {len(repos)}")
    print(f"projects table changed  : {table_changed}")
    print(f"timestamp changed       : {stamp_changed}")

    if args.dry_run:
        print()
        print(updated)
        return 0

    if args.check:
        if changed:
            print("README.md is stale - run the updater to refresh it", file=sys.stderr)
            return 1
        print("README.md is up to date")
        return 0

    if not changed:
        print("nothing to do")
        return 0

    with open(args.path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
