#!/usr/bin/env python3

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
USER = os.environ.get("GITHUB_USER", "ArtemyStudio")

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
GRAPHQL = "https://api.github.com/graphql"

EXCLUDE_LANGS = {"HTML", "CSS", "Makefile", "Roff", "Batchfile"}
EXCLUDE_REPOS = set()

TOP_N = 5

BG = "#0d0d0d"
BORDER = "#262626"
PROMPT_USER = "#9ca3af"
PROMPT_DIM = "#565656"
CMD = "#e5e5e5"
LABEL = "#737373"
VALUE = "#e5e5e5"
NAME = "#d4d4d4"
MUTED = "#9ca3af"
TRACK = "#1a1a1a"
BAR_COLORS = ["#e5e5e5", "#b3b3b3", "#8a8a8a", "#5f5f5f", "#3d3d3d"]

W, H = 495, 195
PAD_X = 34
CHAR_W = 8.4
ROW_START = 82
ROW_STEP = 22.5

REPOS_QUERY = """
query($login:String!, $after:String) {
  user(login:$login) {
    repositories(
      first:100, after:$after,
      ownerAffiliations:OWNER, isFork:false,
      orderBy:{field:STARGAZERS, direction:DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        isPrivate
        stargazerCount
        languages(first:20, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login:String!, $from:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from) {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
    }
    repositoriesContributedTo(
      first:1,
      contributionTypes:[COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
    ) { totalCount }
  }
}
"""


def graphql(query, **variables):
    if not TOKEN:
        sys.exit(
            "error: no token. The GraphQL API requires one.\n"
            "  set GH_TOKEN (personal access token, sees private repos)\n"
            "  or GITHUB_TOKEN (Actions token, public repos only)"
        )
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(GRAPHQL, data=body, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": USER,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            payload = json.loads(res.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"error: GitHub returned {e.code}: {e.read().decode()[:300]}")

    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
        sys.exit(f"error: GraphQL: {msgs}")
    return payload["data"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fetch_repos():
    """Every repo the user owns, forks excluded, following pagination."""
    repos, after = [], None
    while True:
        page = graphql(REPOS_QUERY, login=USER, after=after)["user"]["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        after = page["pageInfo"]["endCursor"]


def collect():
    year = datetime.now(timezone.utc).year
    since = f"{year}-01-01T00:00:00Z"

    repos = [r for r in fetch_repos() if r["name"] not in EXCLUDE_REPOS]

    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in EXCLUDE_LANGS:
                continue
            langs[name] = langs.get(name, 0) + edge["size"]

    c = graphql(CONTRIB_QUERY, login=USER, **{"from": since})["user"]
    contrib = c["contributionsCollection"]

    data = {
        "year": year,
        "repos": len(repos),
        "private_repos": sum(1 for r in repos if r["isPrivate"]),
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": (contrib["totalCommitContributions"]
                    + contrib["restrictedContributionsCount"]),
        "prs": contrib["totalPullRequestContributions"],
        "issues": contrib["totalIssueContributions"],
        "contributed": c["repositoriesContributedTo"]["totalCount"],
    }

    total = sum(langs.values())
    ranking = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)
    if total and len(ranking) > TOP_N:
        rest = total - sum(size for _, size in ranking[:TOP_N - 1])
        ranking = ranking[:TOP_N - 1] + [("other", rest)]
    data["languages"] = (
        [(name, 100.0 * size / total) for name, size in ranking] if total else []
    )
    return data

def b64_font(weight):
    p = REPO_ROOT / "scripts" / "fonts" / f"JetBrainsMono-{weight}.subset.woff2"
    return base64.b64encode(p.read_bytes()).decode()


def card_shell(header_cmd, cursor=True):
    header = f'<text x="{PAD_X}" y="46" font-size="14">' \
             f'<tspan fill="{PROMPT_USER}">artemy@dewos</tspan>' \
             f'<tspan fill="{PROMPT_DIM}">:~$ </tspan>' \
             f'<tspan fill="{CMD}">{header_cmd}</tspan></text>'
    cursor_svg = ""
    if cursor:
        cx = PAD_X + (len("artemy@dewos:~$ ") + len(header_cmd)) * CHAR_W + 8
        cursor_svg = (f'<rect x="{cx:.1f}" y="33" width="9" height="17" rx="2" fill="{PROMPT_DIM}">'
                      f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" '
                      f'dur="1.2s" repeatCount="indefinite"/></rect>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">
<style>
@font-face {{ font-family: 'JetBrains Mono'; src: url(data:font/woff2;base64,{b64_font('Regular')}) format('woff2'); font-weight: 400; }}
@font-face {{ font-family: 'JetBrains Mono'; src: url(data:font/woff2;base64,{b64_font('Bold')}) format('woff2'); font-weight: 700; }}
text {{ font-family: 'JetBrains Mono', ui-monospace, 'Cascadia Code', Menlo, Consolas, monospace; }}
</style>
<defs>
<linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#ffffff" stop-opacity="0.05"/>
<stop offset="0.4" stop-color="#ffffff" stop-opacity="0"/>
</linearGradient>
</defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="28" fill="{BG}" stroke="{BORDER}"/>
<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" rx="27" fill="url(#sheen)" stroke="#ffffff" stroke-opacity="0.05"/>
{header}{cursor_svg}
"""


def stats_card(d):
    rows = [
        ("commits", str(d["commits"])),
        ("pull requests", str(d["prs"])),
        ("issues", str(d["issues"])),
        ("stars earned", str(d["stars"])),
        ("contributed to", str(d["contributed"])),
    ]
    body = ""
    y = ROW_START
    for label, value in rows:
        body += (f'<text x="{PAD_X}" y="{y:.1f}" font-size="13" fill="{LABEL}">{label}</text>'
                 f'<text x="230" y="{y:.1f}" font-size="13" font-weight="700" fill="{VALUE}">{value}</text>')
        y += ROW_STEP
    return card_shell(f"gh stats --year {d['year']}") + body + "</svg>"


def languages_card(d):
    if not d["languages"]:
        body = (f'<text x="{PAD_X}" y="{ROW_START:.1f}" font-size="13" fill="{LABEL}">'
                f'// no languages detected yet</text>'
                f'<text x="{PAD_X}" y="{ROW_START + ROW_STEP:.1f}" font-size="13" fill="{PROMPT_DIM}">'
                f'// push some code and it will fill in</text>')
    else:
        body = ""
        y = ROW_START
        for i, (name, pct) in enumerate(d["languages"]):
            label = esc(name if len(name) <= 11 else name[:10] + "..")
            bar_fill_w = round(190 * pct / 100.0)
            color = BAR_COLORS[min(i, len(BAR_COLORS) - 1)]
            body += (f'<text x="{PAD_X}" y="{y:.1f}" font-size="13" fill="{NAME}">{label}</text>'
                     f'<rect x="150" y="{y - 9:.1f}" width="190" height="8" rx="4" fill="{TRACK}"/>'
                     f'<rect x="150" y="{y - 9:.1f}" width="{max(bar_fill_w, 8)}" height="8" rx="4" fill="{color}"/>'
                     f'<text x="461" y="{y:.1f}" font-size="12" fill="{MUTED}" text-anchor="end">{pct:.1f}%</text>')
            y += ROW_STEP
    return card_shell("gh langs --top") + body + "</svg>"


def main():
    out_dir = REPO_ROOT / (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "assets")
    out_dir.mkdir(parents=True, exist_ok=True)
    data = collect()
    (out_dir / "stats-card.svg").write_text(stats_card(data))
    (out_dir / "languages-card.svg").write_text(languages_card(data))

    scope = "public + private" if os.environ.get("GH_TOKEN") else "public only"
    print(f"scanned {data['repos']} repos ({data['private_repos']} private) - {scope}")
    print(f"languages: {[(n, round(p, 1)) for n, p in data['languages']]}")
    print(f"written: {out_dir}/stats-card.svg, {out_dir}/languages-card.svg")


if __name__ == "__main__":
    main()
