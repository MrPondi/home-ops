#!/usr/bin/env python
"""Sync Jellyfin primary images for persons that are missing one.

Jellyfin downloads actor images only during a metadata refresh of the person
item. Issuing a GET on `/Users/{user_id}/Items/{id}` is the cheapest way to
make Jellyfin fetch the primary image for every person that currently has none.

Steps:
1. GET `/emby/Persons` and collect every person whose `ImageTags.Primary`
   is null.
2. GET `/Users/{user_id}/Items/{id}` for each of them concurrently -- Jellyfin
   refreshes the item's images as a side effect of the request.
3. Print a summary; failed persons are listed with their status or error.

Configuration (environment):
    JELLYFIN_API_KEY   required, Jellyfin API token
    JELLYFIN_USER_ID   required, user id used for the item refresh requests
    JELLYFIN_SERVER    optional, Jellyfin base URL (default: see --server)

Usage:
    uv run scripts/jellyfin_actor_images.py
    uv run scripts/jellyfin_actor_images.py --server https://jf.example.org --concurrency 4

Exit code 0 = all refreshed, 1 = any failure or missing configuration.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

import httpx2
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn
from rich.progress import MofNCompleteColumn
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TaskProgressColumn
from rich.progress import TextColumn

DEFAULT_SERVER = "https://jellyfin.pondi.dev"
DEFAULT_CONCURRENCY = 8
REQUEST_TIMEOUT = 30
ATTEMPTS = 2

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger Jellyfin's image refresh for persons missing a primary image.",
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("JELLYFIN_SERVER", DEFAULT_SERVER),
        help="Jellyfin base URL (default: $JELLYFIN_SERVER or %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.environ.get("JELLYFIN_CONCURRENCY", str(DEFAULT_CONCURRENCY))),
        help="parallel refresh workers (default: $JELLYFIN_CONCURRENCY or %(default)s)",
    )
    return parser.parse_args()


def list_persons_missing_image(client: httpx2.Client) -> list[tuple[str, str]]:
    resp = client.get("/emby/Persons")
    resp.raise_for_status()
    items = resp.json().get("Items") or []
    return [
        (item["Id"], item.get("Name") or item["Id"])
        for item in items
        if (item.get("ImageTags") or {}).get("Primary") is None
    ]


def refresh_item(client: httpx2.Client, path: str, person_id: str, person_name: str) -> tuple[str, str, str] | None:
    reason = "unreachable"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            resp = client.get(path)
        except httpx2.RequestError as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if attempt == ATTEMPTS:
                break
            continue
        if resp.is_success:
            return None
        reason = f"HTTP {resp.status_code}"
        if resp.status_code < 500 or attempt == ATTEMPTS:
            break
    return person_id, person_name, reason


def main() -> int:
    args = parse_args()

    missing = [
        name
        for name in ("JELLYFIN_API_KEY", "JELLYFIN_USER_ID")
        if not os.environ.get(name)
    ]
    if missing:
        console.print(
            Panel(
                f"Missing required environment variable(s): {', '.join(missing)}",
                border_style="red",
            )
        )
        return 1

    console.print(
        Panel(
            "Jellyfin Missing Actor Image Sync",
            border_style="magenta",
            padding=(0, 2),
        )
    )

    headers = {"X-Emby-Token": os.environ["JELLYFIN_API_KEY"]}
    user_id = os.environ["JELLYFIN_USER_ID"]

    with httpx2.Client(base_url=args.server, headers=headers, timeout=REQUEST_TIMEOUT) as client:
        with console.status("Querying Jellyfin for persons without images..."):
            try:
                persons = list_persons_missing_image(client)
            except (httpx2.HTTPError, ValueError) as exc:
                console.print(Panel(f"Querying persons failed: {exc}", border_style="red"))
                return 1

    if not persons:
        console.print(Panel("All persons already have images! Nothing to do.", border_style="green"))
        return 0

    total = len(persons)
    console.print(f"Found {total} persons missing images. Syncing ({args.concurrency} parallel workers)...")
    console.print()

    failures: list[tuple[str, str, str]] = []
    success = 0

    with httpx2.Client(base_url=args.server, headers=headers, timeout=REQUEST_TIMEOUT) as client:
        with Progress(
            TextColumn("[magenta][progress.percentage]{task.percentage:>3.0f}%[/magenta]"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("sync", total=total)
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(
                        refresh_item,
                        client,
                        f"/Users/{user_id}/Items/{person_id}",
                        person_id,
                        person_name,
                    ): (person_id, person_name)
                    for person_id, person_name in persons
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result is None:
                        success += 1
                    else:
                        failures.append(result)
                    progress.advance(task)

    console.print()
    if not failures:
        console.print(
            Panel(
                f"Finished! Successfully updated all {success} persons.",
                border_style="green",
                padding=(0, 2),
            )
        )
        return 0

    details = "\n".join(f"  {name} ({person_id}): {reason}" for person_id, name, reason in failures)
    console.print(
        Panel(
            f"Finished with issues: {success} updated, {len(failures)} failed.\n{details}",
            border_style="dark_orange",
            padding=(0, 2),
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
