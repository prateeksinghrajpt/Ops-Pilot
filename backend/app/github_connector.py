from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


class GitHubConnectorError(RuntimeError):
    pass


def parse_github_repo(repo: str) -> tuple[str, str]:
    parts = [part.strip() for part in repo.strip().split("/") if part.strip()]
    if len(parts) != 2:
        raise GitHubConnectorError("GITHUB_REPO must use owner/repo format")
    return parts[0], parts[1]


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def event_in_window(value: str | None, since: datetime, until: datetime) -> bool:
    parsed = parse_github_time(value)
    return bool(parsed and since <= parsed <= until)


def parse_commit_events(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for item in commits:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        message = str(commit.get("message") or "").splitlines()[0][:180]
        sha = str(item.get("sha") or "")
        short_sha = sha[:7] if sha else "unknown"
        events.append({
            "source": "github",
            "level": "info",
            "message": f"Commit {short_sha} was merged near the incident window: {message}",
            "details": {
                "event_type": "commit",
                "sha": sha,
                "author": (author.get("name") or "unknown"),
                "url": item.get("html_url"),
                "timestamp": author.get("date"),
                "message": commit.get("message"),
            },
            "timestamp": parse_github_time(author.get("date")),
        })
    return events


def parse_release_events(releases: list[dict[str, Any]], since: datetime, until: datetime) -> list[dict[str, Any]]:
    events = []
    for item in releases:
        published_at = item.get("published_at") or item.get("created_at")
        if not event_in_window(published_at, since, until):
            continue
        tag = item.get("tag_name") or item.get("name") or "untagged"
        events.append({
            "source": "github",
            "level": "warning",
            "message": f"Release {tag} was published near the incident window.",
            "details": {
                "event_type": "release",
                "tag": tag,
                "author": (item.get("author") or {}).get("login"),
                "url": item.get("html_url"),
                "timestamp": published_at,
                "message": item.get("name") or item.get("body") or "",
            },
            "timestamp": parse_github_time(published_at),
        })
    return events


def parse_workflow_events(runs: list[dict[str, Any]], since: datetime, until: datetime) -> list[dict[str, Any]]:
    events = []
    for item in runs:
        created_at = item.get("created_at")
        if not event_in_window(created_at, since, until):
            continue
        status = item.get("conclusion") or item.get("status") or "unknown"
        workflow = item.get("name") or "GitHub Actions workflow"
        level = "warning" if status in {"failure", "cancelled", "timed_out"} else "info"
        events.append({
            "source": "github",
            "level": level,
            "message": f"{workflow} workflow run completed with status {status} near the incident window.",
            "details": {
                "event_type": "workflow_run",
                "workflow": workflow,
                "status": status,
                "sha": item.get("head_sha"),
                "author": (item.get("actor") or {}).get("login"),
                "url": item.get("html_url"),
                "timestamp": created_at,
                "message": item.get("display_title") or workflow,
            },
            "timestamp": parse_github_time(created_at),
        })
    return events


def collect_github_events(
    repo: str,
    token: str,
    incident_time: datetime,
    lookback_hours: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    owner, name = parse_github_repo(repo)
    until = incident_time.astimezone(timezone.utc)
    since = until - timedelta(hours=max(1, lookback_hours))
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OpsPilot-RCA",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base = f"https://api.github.com/repos/{owner}/{name}"
    try:
        with httpx.Client(headers=headers, timeout=15.0) as client:
            commits_response = client.get(
                f"{base}/commits",
                params={"since": isoformat(since), "until": isoformat(until), "per_page": limit},
            )
            commits_response.raise_for_status()
            events = parse_commit_events(commits_response.json())

            for path, parser in (
                ("releases", lambda payload: parse_release_events(payload, since, until)),
                ("actions/runs", lambda payload: parse_workflow_events(payload.get("workflow_runs", []), since, until)),
            ):
                response = client.get(f"{base}/{path}", params={"per_page": limit})
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                events.extend(parser(response.json()))
    except httpx.HTTPStatusError as exc:
        raise GitHubConnectorError(f"GitHub API returned {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise GitHubConnectorError("Unable to reach GitHub API") from exc

    events.sort(key=lambda event: event.get("timestamp") or since, reverse=True)
    return events[:limit]
