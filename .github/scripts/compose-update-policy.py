#!/usr/bin/env python3
"""Validate and merge eligible generated compose update pull requests."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PolicyHold(Exception):
    """The pull request is not eligible for automatic merging."""


class CommandError(Exception):
    """A required external command failed."""


@dataclass(frozen=True)
class Environment:
    repository: str
    event_path: str
    event_name: str
    token: str
    download_node: str | None


def required_environment() -> Environment:
    values = {
        "GITHUB_REPOSITORY": os.environ.get("GITHUB_REPOSITORY"),
        "GITHUB_EVENT_PATH": os.environ.get("GITHUB_EVENT_PATH"),
        "GITHUB_EVENT_NAME": os.environ.get("GITHUB_EVENT_NAME"),
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CommandError(f"Required environment variables are missing: {', '.join(missing)}")

    return Environment(
        repository=values["GITHUB_REPOSITORY"],
        event_path=values["GITHUB_EVENT_PATH"],
        event_name=values["GITHUB_EVENT_NAME"],
        token=values["GITHUB_TOKEN"],
        download_node=os.environ.get("DOWNLOAD_NODE"),
    )


def run_gh(environment: Environment, *arguments: str) -> str:
    command = ["gh", *arguments]
    command_environment = os.environ.copy()
    command_environment["GH_TOKEN"] = environment.token
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=command_environment,
    )
    if result.returncode:
        details = result.stderr.strip() or result.stdout.strip()
        raise CommandError(f"{' '.join(command)} failed: {details}")
    return result.stdout


def run_gh_json(environment: Environment, *arguments: str):
    output = run_gh(environment, *arguments)
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise CommandError(f"gh returned invalid JSON: {error}") from error


def pull_request_number(environment: Environment, event: dict) -> int | None:
    if environment.event_name == "status":
        pulls = run_gh_json(
            environment,
            "api",
            f"repos/{environment.repository}/commits/{event['sha']}/pulls",
        )
        return pulls[0]["number"] if pulls else None

    action = event.get("action", "")
    if action in {"opened", "reopened", "synchronize"}:
        return event["number"]
    if action == "completed":
        pulls = event.get("check_suite", {}).get("pull_requests", [])
        return pulls[0]["number"] if pulls else None

    pull_request = event.get("pull_request")
    if pull_request:
        return pull_request.get("number")
    pulls = event.get("check_suite", {}).get("pull_requests", [])
    return pulls[0]["number"] if pulls else None


def policy_check_already_passed(environment: Environment, event: dict) -> bool:
    if event.get("action") != "completed":
        return False

    head_sha = event["check_suite"]["head_sha"]
    check_runs = run_gh_json(
        environment,
        "api",
        f"repos/{environment.repository}/commits/{head_sha}/check-runs?per_page=100",
    )
    return any(
        "Compose update policy" in check_run["name"]
        and check_run.get("conclusion") == "success"
        for check_run in check_runs.get("check_runs", [])
    )


def eligible_pull_request(environment: Environment, number: int) -> dict:
    pull_request = run_gh_json(
        environment,
        "pr",
        "view",
        str(number),
        "--repo",
        environment.repository,
        "--json",
        "author,baseRefName,body,headRefOid,isDraft,labels,state,title",
    )
    author = pull_request["author"].get("login")
    labels = {label["name"] for label in pull_request["labels"]}
    if (
        pull_request["state"] != "OPEN"
        or pull_request["isDraft"]
        or pull_request["baseRefName"] != "main"
        or author != "cloudkitebot"
    ):
        raise PolicyHold
    if not {"automated-pr", "auto-merge"}.intersection(labels):
        raise PolicyHold
    if labels.intersection({"needs-review", "WIP", "DO_NOT_MERGE"}):
        raise PolicyHold
    return pull_request


def changed_compose_file(environment: Environment, number: int) -> str:
    files = run_gh_json(
        environment,
        "api",
        f"repos/{environment.repository}/pulls/{number}/files?per_page=100",
    )
    if len(files) != 1:
        raise PolicyHold(f"expected exactly one changed file, found {len(files)}")

    changed_file = files[0]
    filename = changed_file["filename"]
    if (
        not re.fullmatch(r"compose/compose\.[A-Za-z0-9._-]+", filename)
        or changed_file["additions"] != 1
        or changed_file["deletions"] != 0
    ):
        raise PolicyHold("the PR is not an append-only compose update")
    return filename


def compose_id_from_pull_request(pull_request: dict) -> str:
    title = pull_request["title"]
    compose_id = re.sub(r"^(.+)\s-\s[0-9]{4}-[0-9]{2}-[0-9]{2}$", r"\1", title)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", compose_id):
        raise PolicyHold("the title is not a valid compose ID")
    if compose_id not in (pull_request.get("body") or ""):
        raise PolicyHold("the PR body does not identify the compose")
    return compose_id


def repository_file(environment: Environment, path: str, ref: str) -> str:
    response = run_gh_json(
        environment,
        "api",
        f"repos/{environment.repository}/contents/{path}?ref={ref}",
    )
    try:
        return base64.b64decode(response["content"].replace("\n", "")).decode()
    except (KeyError, ValueError, UnicodeDecodeError) as error:
        raise CommandError(f"Could not decode repository file {path}: {error}") from error


def validate_append(environment: Environment, filename: str, head_sha: str, compose_id: str) -> None:
    base_content = repository_file(environment, filename, "main")
    head_content = repository_file(environment, filename, head_sha)
    expected = f"{base_content}{compose_id}\n" if base_content.endswith("\n") else f"{base_content}\n{compose_id}\n"
    if head_content != expected:
        raise PolicyHold("the head file is not the base file plus one appended compose ID")


def current_compose_id(environment: Environment, filename: str) -> str:
    if filename.startswith("compose/compose.9") or filename == "compose/compose.810":
        if not environment.download_node:
            raise CommandError("DOWNLOAD_NODE is required")

    urls = {
        "compose/compose.f43": "https://dl.fedoraproject.org/pub/fedora/linux/development/43/COMPOSE_ID",
        "compose/compose.f44-iot": "https://kojipkgs.fedoraproject.org/compose/iot/latest-Fedora-IoT-44/COMPOSE_ID",
        "compose/compose.f45-iot": "https://kojipkgs.fedoraproject.org/compose/iot/latest-Fedora-IoT-45/COMPOSE_ID",
        "compose/compose.f46-iot": "https://kojipkgs.fedoraproject.org/compose/iot/latest-Fedora-IoT-46/COMPOSE_ID",
        "compose/compose.cs9": "https://odcs.stream.centos.org/production/",
    }
    for stream in ("92", "94", "95", "96", "98"):
        urls[f"compose/compose.{stream}"] = (
            f"http://{environment.download_node}/rhel-9/nightly/updates/"
            f"RHEL-9/latest-RHEL-{stream}.0/COMPOSE_ID"
        )
    urls["compose/compose.810"] = (
        f"http://{environment.download_node}/rhel-8/nightly/updates/"
        "RHEL-8/latest-RHEL-8.10.0/COMPOSE_ID"
    )
    if filename not in urls:
        raise PolicyHold("compose stream is not allowlisted")

    request = Request(urls[filename])
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read().decode().strip()
    except (HTTPError, URLError, TimeoutError) as error:
        raise CommandError(f"Could not fetch current compose ID: {error}") from error

    if filename == "compose/compose.cs9":
        matches = re.findall(r"CentOS-Stream-9-[0-9.]+/", content)
        if not matches:
            raise CommandError("Could not find the current CentOS Stream compose ID")
        return matches[-1].rstrip("/")
    return content


STREAM_CHECKS = {
    "compose/compose.f43": ("iot-f43-x86",),
    "compose/compose.f44-iot": ("iot-f44-x86",),
    "compose/compose.f45-iot": ("iot-f45-x86",),
    "compose/compose.f46-iot": ("iot-f46-x86",),
    "compose/compose.92": ("edge-rhel-9.2-x86", "edge-rhel-9.2-arm"),
    "compose/compose.94": ("edge-rhel-9.4-x86",),
    "compose/compose.95": ("edge-rhel-9.5-x86", "edge-rhel-9.5-arm"),
    "compose/compose.96": ("edge-rhel-9.6-x86", "edge-rhel-9.6-arm"),
    "compose/compose.98": ("edge-rhel-9.8-x86", "edge-rhel-9.8-arm"),
    "compose/compose.810": ("edge-rhel-8.10-x86",),
    "compose/compose.cs9": ("edge-cs-9-x86", "edge-cs-9-arm"),
}


def required_checks(environment: Environment, number: int, stream_checks: tuple[str, ...]) -> None:
    checks = run_gh_json(
        environment,
        "pr",
        "checks",
        str(number),
        "--repo",
        environment.repository,
        "--json",
        "name,state,bucket",
    )
    for lint_check in ("commitlint", "codespell", "shellcheck", "yamllint"):
        passed = any(
            lint_check in check["name"].lower() and check["bucket"] == "pass"
            for check in checks
        )
        if not passed:
            raise PolicyHold(f"lint check {lint_check} has not passed")
    for stream_check in stream_checks:
        if not any(
            check["name"] == stream_check and check["bucket"] == "pass"
            for check in checks
        ):
            raise PolicyHold(f"stream check {stream_check} has not passed")


def main() -> int:
    environment = required_environment()
    with open(environment.event_path, encoding="utf-8") as event_file:
        event = json.load(event_file)

    number = pull_request_number(environment, event)
    if number is None:
        return 0
    if policy_check_already_passed(environment, event):
        return 0

    pull_request = eligible_pull_request(environment, number)
    filename = changed_compose_file(environment, number)
    compose_id = compose_id_from_pull_request(pull_request)
    validate_append(environment, filename, pull_request["headRefOid"], compose_id)
    if current_compose_id(environment, filename) != compose_id:
        raise PolicyHold(
            f"compose {compose_id} is superseded or could not be verified"
        )
    required_checks(environment, number, STREAM_CHECKS[filename])

    run_gh(
        environment,
        "pr",
        "review",
        str(number),
        "--repo",
        environment.repository,
        "--approve",
        "--body",
        f"Compose update policy passed for {compose_id}.",
    )
    run_gh(
        environment,
        "pr",
        "merge",
        str(number),
        "--repo",
        environment.repository,
        "--auto",
        "--rebase",
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PolicyHold as error:
        print(f"Policy hold: {error}")
        sys.exit(1)
    except (CommandError, KeyError, json.JSONDecodeError) as error:
        print(f"Policy error: {error}", file=sys.stderr)
        sys.exit(1)
