#!/usr/bin/env python3
"""Generate the profile README SVGs."""

from __future__ import annotations

import base64
import calendar
import html
import json
import os
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
USERNAME = os.getenv("USER_NAME", "rylena")
DISPLAY_NAME = "Rylen Anil"
BIRTHDAY = date.fromisoformat(os.getenv("BIRTHDAY", "2009-10-30"))
TIMEZONE = os.getenv("PROFILE_TIMEZONE", "Asia/Dubai")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("ACCESS_TOKEN")

if not TOKEN:
    try:
        TOKEN = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        TOKEN = None

@dataclass(frozen=True)
class Theme:
    filename: str
    portrait_filename: str
    background: str
    foreground: str
    muted: str
    key: str
    value: str
    accent: str


THEMES = [
    Theme(
        filename="dark_mode.svg",
        portrait_filename="profile_ascii_dark.png",
        background="#161b22",
        foreground="#c9d1d9",
        muted="#6e7681",
        key="#ffa657",
        value="#a5d6ff",
        accent="#3fb950",
    ),
    Theme(
        filename="light_mode.svg",
        portrait_filename="profile_ascii_light.png",
        background="#f6f8fa",
        foreground="#24292f",
        muted="#6e7781",
        key="#953800",
        value="#0969da",
        accent="#1a7f37",
    ),
]


def request_json(url: str) -> dict:
    return api_json(url)


def api_json(url: str, payload: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rylena-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def graphql(query: str, variables: dict) -> dict:
    if not TOKEN:
        raise RuntimeError("GitHub GraphQL requires a token")
    payload = {"query": query, "variables": variables}
    data = api_json("https://api.github.com/graphql", payload)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def age_string(birthday: date, today: date) -> str:
    years = today.year - birthday.year
    anniversary = add_months(birthday, years * 12)
    if anniversary > today:
        years -= 1
        anniversary = add_months(birthday, years * 12)

    months = 0
    while add_months(anniversary, months + 1) <= today:
        months += 1

    monthiversary = add_months(anniversary, months)
    days = (today - monthiversary).days

    def unit(amount: int, label: str) -> str:
        suffix = "" if amount == 1 else "s"
        return f"{amount} {label}{suffix}"

    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"


def public_repositories(username: str) -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"per_page": 100, "page": page, "type": "owner", "sort": "updated"}
        )
        batch = request_json(f"https://api.github.com/users/{username}/repos?{query}")
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def commit_count(username: str) -> int | None:
    query = urllib.parse.quote(f"author:{username} is:public")
    try:
        data = request_json(f"https://api.github.com/search/commits?q={query}")
        return int(data.get("total_count", 0))
    except Exception as exc:
        print(f"Commit search unavailable: {exc}")
        return None


def contributed_repo_count(username: str, fallback: int) -> int:
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(
          first: 1
          ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]
          privacy: PUBLIC
        ) {
          totalCount
        }
      }
    }
    """
    try:
        data = graphql(query, {"login": username})
        return int(data["user"]["repositories"]["totalCount"])
    except Exception as exc:
        print(f"Contributed repo count unavailable: {exc}")
        return fallback


def line_totals(username: str, owner_id: str, repos: list[dict]) -> dict[str, int] | None:
    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100, after: $cursor) {
                edges {
                  node {
                    additions
                    deletions
                    author {
                      user {
                        id
                        login
                      }
                    }
                  }
                }
                pageInfo {
                  endCursor
                  hasNextPage
                }
              }
            }
          }
        }
      }
    }
    """

    try:
        totals = {"additions": 0, "deletions": 0, "commits": 0}
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            owner, name = repo["full_name"].split("/", 1)
            cursor = None
            while True:
                data = graphql(query, {"owner": owner, "name": name, "cursor": cursor})
                branch = data["repository"]["defaultBranchRef"]
                if not branch:
                    break
                history = branch["target"]["history"]
                for edge in history["edges"]:
                    node = edge["node"]
                    author = node.get("author") or {}
                    user = author.get("user") or {}
                    if user.get("id") == owner_id or user.get("login") == username:
                        totals["additions"] += int(node["additions"])
                        totals["deletions"] += int(node["deletions"])
                        totals["commits"] += 1
                if not history["pageInfo"]["hasNextPage"]:
                    break
                cursor = history["pageInfo"]["endCursor"]
        return totals
    except Exception as exc:
        print(f"Line count unavailable: {exc}")
        return None


def github_stats(username: str) -> dict[str, str]:
    try:
        user = request_json(f"https://api.github.com/users/{username}")
        repos = public_repositories(username)
        commits = commit_count(username)
    except Exception as exc:
        print(f"GitHub API unavailable: {exc}")
        return {
            "repos": "n/a",
            "stars": "n/a",
            "followers": "n/a",
            "commits": "n/a",
            "contributed": "n/a",
            "loc": "n/a",
            "loc_add": "n/a",
            "loc_del": "n/a",
        }

    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos)
    repo_count = int(user.get("public_repos") or len(repos))
    followers = int(user.get("followers", 0))
    contributed = contributed_repo_count(username, repo_count)
    lines = line_totals(username, user["node_id"], repos)
    if lines:
        loc_add = lines["additions"]
        loc_del = lines["deletions"]
        loc = loc_add - loc_del
    else:
        loc_add = loc_del = loc = None

    return {
        "repos": f"{repo_count:,}",
        "stars": f"{stars:,}",
        "followers": f"{followers:,}",
        "commits": f"{commits:,}" if commits is not None else "n/a",
        "contributed": f"{contributed:,}",
        "loc": f"{loc:,}" if loc is not None else "n/a",
        "loc_add": f"{loc_add:,}" if loc_add is not None else "n/a",
        "loc_del": f"{loc_del:,}" if loc_del is not None else "n/a",
    }


def profile_rows(now: datetime) -> list[tuple[str, str]]:
    today = now.date()
    return [
        ("OS", "Debian, iOS"),
        ("Uptime", age_string(BIRTHDAY, today)),
        ("Host", "AISC"),
        ("Kernel", "Student / developer / security"),
        ("IDE", "VSCode"),
        ("Languages.Programming", "Python, JavaScript, C"),
        ("Languages.Computer", "Markdown, JSON, React"),
        ("Languages.Real", "English, Hindi, Malayalam"),
        ("Hobbies.Software", "Pentesting, software builds, DevOps"),
        ("Hobbies.Hardware", "Homelabs, hardware mods, 3D printing"),
    ]


def contact_rows() -> list[tuple[str, str, str | None]]:
    return [
        ("Email.Primary", "rylen.anil@gmail.com", "mailto:rylen.anil@gmail.com"),
        ("Email.Personal", "me@rylenanil.xyz", "mailto:me@rylenanil.xyz"),
        ("X", "@DarthKermi72747", "https://x.com/DarthKermi72747"),
        (
            "LinkedIn",
            "@rylen-anil-perumkannaril",
            "https://www.linkedin.com/in/rylen-anil-perumkannaril/",
        ),
        ("Discord", "@darth_kermit1", None),
    ]


def row_svg(key: str, value: str, y: int, theme: Theme, href: str | None = None) -> str:
    safe_key = html.escape(key)
    safe_value = html.escape(value)
    value_svg = f'<tspan x="800" class="value">{safe_value}</tspan>'
    if href:
        value_svg = f'<a href="{html.escape(href)}" target="_blank">{value_svg}</a>'
    return (
        f'<tspan x="535" y="{y}" class="muted">. </tspan>'
        f'<tspan class="key">{safe_key}</tspan>'
        f'<tspan class="muted">:</tspan>'
        f"{value_svg}"
    )


def github_stats_svg(stats: dict[str, str], y: int) -> list[str]:
    return [
        (
            f'<tspan x="535" y="{y}" class="muted">. </tspan>'
            f'<tspan class="key">Repos</tspan><tspan class="muted">:</tspan> '
            f'<tspan class="value">{stats["repos"]}</tspan> '
            f'<tspan class="muted">{{</tspan><tspan class="key">Contributed</tspan>'
            f'<tspan class="muted">: </tspan><tspan class="value">{stats["contributed"]}</tspan>'
            f'<tspan class="muted">}} | </tspan><tspan class="key">Stars</tspan>'
            f'<tspan class="muted">:</tspan> <tspan class="value">{stats["stars"]}</tspan>'
        ),
        (
            f'<tspan x="535" y="{y + 22}" class="muted">. </tspan>'
            f'<tspan class="key">Commits</tspan><tspan class="muted">:</tspan> '
            f'<tspan class="value">{stats["commits"]}</tspan>'
            f'<tspan class="muted"> | </tspan><tspan class="key">Followers</tspan>'
            f'<tspan class="muted">:</tspan> <tspan class="value">{stats["followers"]}</tspan>'
        ),
        (
            f'<tspan x="535" y="{y + 44}" class="muted">. </tspan>'
            f'<tspan class="key">Lines of Code on GitHub</tspan><tspan class="muted">:</tspan> '
            f'<tspan class="value">{stats["loc"]}</tspan>'
            f'<tspan class="muted"> ( </tspan><tspan class="addColor">{stats["loc_add"]}</tspan>'
            f'<tspan class="addColor">++</tspan><tspan class="muted">, </tspan>'
            f'<tspan class="delColor">{stats["loc_del"]}</tspan><tspan class="delColor">--</tspan>'
            f'<tspan class="muted"> )</tspan>'
        ),
    ]


def render_svg(theme: Theme, stats: dict[str, str], now: datetime) -> str:
    portrait_data = base64.b64encode(
        (ROOT / theme.portrait_filename).read_bytes()
    ).decode("ascii")

    row_lines: list[str] = [
        '<tspan x="535" y="34" class="accent">rylen@anil</tspan>',
        '<tspan x="535" y="54" class="muted">----------------------------------------------</tspan>',
    ]

    y = 82
    for key, value in profile_rows(now):
        row_lines.append(row_svg(key, value, y, theme))
        y += 22

    y += 20
    row_lines.append(
        f'<tspan x="535" y="{y}" class="muted">- Contact -------------------------------------</tspan>'
    )
    y += 24
    for key, value, href in contact_rows():
        row_lines.append(row_svg(key, value, y, theme, href))
        y += 22

    y += 20
    row_lines.append(
        f'<tspan x="535" y="{y}" class="muted">- GitHub Stats --------------------------------</tspan>'
    )
    y += 24
    row_lines.extend(github_stats_svg(stats, y))
    y += 72
    row_lines.append(row_svg("Updated", now.strftime("%Y-%m-%d %H:%M %Z"), y, theme))

    rows_markup = "\n".join(row_lines)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1175" height="620" viewBox="0 0 1175 620" font-family="ConsolasFallback, Consolas, Monaco, monospace" font-size="16">
  <style>
    @font-face {{
      src: local("Consolas"), local("Monaco");
      font-family: "ConsolasFallback";
      font-display: swap;
      -webkit-size-adjust: 109%;
      size-adjust: 109%;
    }}
    .foreground {{ fill: {theme.foreground}; }}
    .muted {{ fill: {theme.muted}; }}
    .key {{ fill: {theme.key}; }}
    .value {{ fill: {theme.value}; }}
    .accent {{ fill: {theme.accent}; }}
    .addColor {{ fill: #3fb950; }}
    .delColor {{ fill: #f85149; }}
    a {{ text-decoration: none; }}
    text, tspan {{ white-space: pre; }}
  </style>
  <rect width="1175" height="620" fill="{theme.background}" rx="30"/>
  <image x="18" y="5" width="462" height="610" preserveAspectRatio="none" href="data:image/png;base64,{portrait_data}"/>
  <text class="foreground">
{rows_markup}
  </text>
</svg>
"""


def main() -> None:
    now = datetime.now(ZoneInfo(TIMEZONE))
    stats = github_stats(USERNAME)
    for theme in THEMES:
        (ROOT / theme.filename).write_text(render_svg(theme, stats, now), encoding="utf-8")
        print(f"Updated {theme.filename}")


if __name__ == "__main__":
    main()
