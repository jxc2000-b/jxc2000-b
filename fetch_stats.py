#!/usr/bin/env python3
"""Fetch GitHub stats via the GraphQL v4 API into cache.json.

Collected: owned repo count, contributed-to count, total stars, total forks,
followers, following, open+closed PR / issue counts, total commits authored
on default branches, total lines of code added/deleted/net, top languages,
and account age.

Auth (first match wins):
  ACCESS_TOKEN or GITHUB_TOKEN env var, else `gh auth token` if the GitHub
  CLI is logged in. Needs repo + read:user scopes.

User: USER_NAME env var or --user LOGIN; defaults to the token's owner.

The expensive part - walking every repo's commit history for LOC - is cached
per repo keyed on `pushedAt`, so unchanged repos are never re-fetched.
Use --refresh to ignore the cache and re-walk everything.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

API = "https://api.github.com/graphql"
CACHE = "cache.json"

USER_Q = """
query($login: String!) {
  user(login: $login) {
    id name login createdAt
    followers { totalCount }
    following { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]
    ) { totalCount }
  }
}"""

REPOS_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner isFork isArchived
        stargazerCount forkCount pushedAt
        primaryLanguage { name }
        defaultBranchRef { name }
      }
    }
  }
}"""

LOC_Q = """
query($owner: String!, $name: String!, $id: ID, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor, author: {id: $id}) {
            totalCount
            pageInfo { hasNextPage endCursor }
            nodes { additions deletions }
          }
        }
      }
    }
  }
}"""


def get_token():
    for var in ("ACCESS_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, check=True).stdout.strip()
        if tok:
            return tok
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    sys.exit("no token: set ACCESS_TOKEN / GITHUB_TOKEN or log in with `gh auth login`")


def gql(token, query, variables, tries=4):
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "fetch_stats.py",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = 2 ** attempt
            print(f"  retry in {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)


def repo_loc(token, owner, name, user_id):
    """Walk a repo's default-branch history: (commits, additions, deletions)."""
    commits = add = rm = 0
    cursor = None
    while True:
        data = gql(token, LOC_Q, {"owner": owner, "name": name,
                                  "id": user_id, "cursor": cursor})
        ref = data["repository"]["defaultBranchRef"]
        if ref is None or ref["target"] is None:      # empty repo
            return 0, 0, 0
        hist = ref["target"]["history"]
        commits = hist["totalCount"]
        for c in hist["nodes"]:
            add += c["additions"]
            rm += c["deletions"]
        if not hist["pageInfo"]["hasNextPage"]:
            return commits, add, rm
        cursor = hist["pageInfo"]["endCursor"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="GitHub login (default: token owner)")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore cached per-repo LOC and re-walk everything")
    args = ap.parse_args()

    token = get_token()
    login = args.user or os.environ.get("USER_NAME") \
        or gql(token, "{ viewer { login } }", {})["viewer"]["login"]

    old = {}
    if os.path.exists(CACHE) and not args.refresh:
        try:
            old = json.load(open(CACHE, encoding="utf-8")).get("repos", {})
        except (json.JSONDecodeError, OSError):
            pass

    print(f"user: {login}")
    u = gql(token, USER_Q, {"login": login})["user"]
    if u is None:
        sys.exit(f"user {login!r} not found")

    # ---- owned repos (paginated) ----
    repos, cursor = [], None
    while True:
        r = gql(token, REPOS_Q, {"login": login, "cursor": cursor})["user"]["repositories"]
        repos += r["nodes"]
        if not r["pageInfo"]["hasNextPage"]:
            break
        cursor = r["pageInfo"]["endCursor"]
    print(f"repos: {len(repos)} owned")

    # ---- per-repo commit/LOC walk, cached on pushedAt ----
    repo_cache = {}
    langs = {}
    for repo in repos:
        full = repo["nameWithOwner"]
        if repo["primaryLanguage"]:
            langs[repo["primaryLanguage"]["name"]] = \
                langs.get(repo["primaryLanguage"]["name"], 0) + 1
        cached = old.get(full)
        if cached and cached.get("pushed_at") == repo["pushedAt"]:
            repo_cache[full] = cached
            continue
        if repo["defaultBranchRef"] is None:          # empty repo
            repo_cache[full] = {"pushed_at": repo["pushedAt"],
                                "commits": 0, "add": 0, "del": 0}
            continue
        print(f"  walking {full} ...")
        owner, name = full.split("/")
        commits, add, rm = repo_loc(token, owner, name, u["id"])
        repo_cache[full] = {"pushed_at": repo["pushedAt"],
                            "commits": commits, "add": add, "del": rm}

    loc_add = sum(r["add"] for r in repo_cache.values())
    loc_del = sum(r["del"] for r in repo_cache.values())
    cache = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": {"login": u["login"], "name": u["name"], "id": u["id"],
                 "created_at": u["createdAt"]},
        "stats": {
            "repos": len(repos),
            "contributed": u["repositoriesContributedTo"]["totalCount"],
            "stars": sum(r["stargazerCount"] for r in repos),
            "forks": sum(r["forkCount"] for r in repos),
            "followers": u["followers"]["totalCount"],
            "following": u["following"]["totalCount"],
            "pull_requests": u["pullRequests"]["totalCount"],
            "issues": u["issues"]["totalCount"],
            "commits": sum(r["commits"] for r in repo_cache.values()),
            "loc_add": loc_add,
            "loc_del": loc_del,
            "loc_net": loc_add - loc_del,
            "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        },
        "repos": repo_cache,
    }
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

    s = cache["stats"]
    print(f"\nwrote {CACHE}:")
    for k in ("repos", "contributed", "stars", "forks", "followers",
              "commits", "loc_add", "loc_del", "loc_net"):
        print(f"  {k}: {s[k]:,}")


if __name__ == "__main__":
    main()
