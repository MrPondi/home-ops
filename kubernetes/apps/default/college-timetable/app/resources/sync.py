#!/usr/bin/env python3
"""
Sync ICS file events to a CalDAV server efficiently and safely.
Handles event creation, updates, and deletions with proper error handling.
"""

import difflib
import hashlib
import logging
import re
import sys
from parser import EventParser
from typing import Dict, Tuple

import caldav
from caldav.lib.error import AuthorizationError
from icalendar import Calendar
from rich.progress import track

from config import Config

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ICSCalDAVSync:
    def __init__(self, config: Config):
        """
        Initialize the sync client.

        Args:
            config: Configuration object with CalDAV and calendar settings
        """
        self.config = config
        self.client = caldav.DAVClient(
            url=config.caldav_url, username=config.username, password=config.password
        )
        try:
            self.principal = self.client.principal()
        except AuthorizationError as e:
            logger.error(f"Failed access caldav server: {str(e).split(', reason ')[1]}")
            sys.exit(1)
        self.calendars = None
        self.parser = EventParser(config)

    def get_or_create_calendars(self) -> list[caldav.Calendar]:
        """Get existing calendars or create new ones."""
        all_calendars = self.principal.calendars()
        found_calendars = []

        for calendar_name in self.config.calendar_names:
            found = False
            for cal in all_calendars:
                if cal.name == calendar_name:
                    logger.info(f"Found existing calendar: {calendar_name}")
                    found_calendars.append(cal)
                    found = True
                    break

            if not found:
                logger.warning(f"Calendar '{calendar_name}' not found. Creating one.")
                if self.config.dry_run:
                    logger.info(f"[DRY RUN] Would create calendar: {calendar_name}")
                else:
                    new_cal = self.principal.make_calendar(name=calendar_name)
                    logger.info(f"Created new calendar: {calendar_name}")
                    found_calendars.append(new_cal)

        return found_calendars

    def get_server_events(self) -> Dict[int, Dict[str, Tuple[caldav.Event, str]]]:
        """
        Get all events from CalDAV server.

        Returns:
            Dict mapping calendar_index -> {UID: (event_object, content_hash)}
        """
        if not self.calendars:
            raise ValueError("Calendars not initialized")

        server_events = {i: {} for i in range(len(self.calendars))}

        for idx, calendar in enumerate(self.calendars):
            events = calendar.events()

            for event in events:
                try:
                    ical_data = event.data.strip("\n")
                    cal = Calendar.from_ical(ical_data)

                    for component in cal.walk():
                        if component.name == "VEVENT":
                            # Canonicalize the event string for hashing
                            ical_data = re.sub(r"(?:\r?\n)[ \t]", "", ical_data)
                            ical_data = re.sub(r"\r\n?", "\n", ical_data).strip()

                            content_hash = hashlib.md5(ical_data.encode()).hexdigest()
                            uid = str(component.get("uid"))
                            server_events[idx][uid] = (event, content_hash)
                            break
                except Exception as e:
                    logger.error(f"Error reading server event: {e}")
                    continue

        total_events = sum(len(e) for e in server_events.values())
        logger.info(f"Found {total_events} events on server")
        return server_events

    def sync(self) -> Dict[str, int]:
        """
        Sync ICS file to CalDAV server.

        Args:
            dry_run: If True, only show what would be done without making changes

        Returns:
            Dict with counts of created, updated, deleted, unchanged events
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0, "errors": 0}

        # Get or create calendars
        self.calendars = self.get_or_create_calendars()

        if len(self.calendars) != len(self.config.calendar_names):
            logger.error("Not all calendars were found. Aborting sync.")
            return stats

        # Get server events
        server_events = self.get_server_events()

        # Parse local ICS file
        local_events = self.parser.parse_ics_file(server_events)

        # Sync each calendar
        for i in range(len(self.calendars)):
            logger.info(f"{'=' * 60}")
            logger.info(f"Syncing calendar: {self.config.calendar_names[i]}")

            local_cal_events = local_events[i]
            server_cal_events = server_events[i]

            local_uids = set(local_cal_events.keys())
            server_uids = set(server_cal_events.keys())

            # Events to create (in local but not on server)
            to_create = local_uids - server_uids

            # Events to potentially update (in both)
            to_check = local_uids & server_uids

            # Events to delete (on server but not in local)
            to_delete = server_uids - local_uids

            logger.info("Sync Plan:")
            logger.info(f"  To create: {len(to_create)}")
            logger.info(f"  To check for updates: {len(to_check)}")
            logger.info(f"  To delete: {len(to_delete)}")
            logger.info(f"{'=' * 60}")

            if self.config.dry_run:
                logger.info("DRY RUN MODE - No changes will be made")

            # Create new events
            for uid in track(
                list(to_create),
                description=f"Creating events in {self.config.calendar_names[i]}",
            ):
                try:
                    event = local_cal_events[uid]
                    summary = next(
                        (
                            line.split("SUMMARY:")[1]
                            for line in event.event_str_hash.splitlines()
                            if line.startswith("SUMMARY:")
                        ),
                        "",
                    )
                    if self.config.dry_run:
                        logger.debug(f"[DRY RUN] Would create event: {summary} ({uid})")
                    else:
                        self.calendars[i].save_event(event.event_str)
                        logger.debug(f"✓ Created event: {summary} ({uid})")
                    stats["created"] += 1
                except Exception as e:
                    logger.error(f"✗ Error creating event {uid}: {e}")
                    event_data = local_cal_events[uid].event_str
                    logger.debug(f"Event data:\n{event_data}")
                    stats["errors"] += 1

            # Check and update existing events
            for uid in track(
                list(to_check),
                description=f"Checking updates in {self.config.calendar_names[i]}",
            ):
                try:
                    local_event = local_cal_events[uid]
                    server_event, server_hash = server_cal_events[uid]

                    if local_event.event_str_hash != server_hash:
                        diff = "\n".join(
                            difflib.unified_diff(
                                server_event.data.splitlines(),
                                local_event.event_str_hash.splitlines(),
                                lineterm="",
                            )
                        )
                        logger.debug(f"Event update diff: {diff}")
                        if self.config.dry_run:
                            logger.info(f"[DRY RUN] Would update event: {uid}")
                        else:
                            server_event.data = local_event.event_str
                            server_event.save()
                            logger.debug(f"✓ Updated event: {uid}")
                        stats["updated"] += 1
                    else:
                        stats["unchanged"] += 1
                except Exception as e:
                    logger.error(f"✗ Error updating event {uid}: {e}")
                    stats["errors"] += 1

            # Delete events not in local file
            for uid in track(
                list(to_delete),
                description=f"Deleting events from {self.config.calendar_names[i]}",
            ):
                try:
                    server_event, _ = server_cal_events[uid]
                    summary = next(
                        (
                            line.split("SUMMARY:")[1]
                            for line in server_event.data.splitlines()
                            if line.startswith("SUMMARY:")
                        ),
                        "",
                    )
                    if self.config.dry_run:
                        logger.info(f"[DRY RUN] Would delete event: {summary} ({uid})")
                    else:
                        server_event.delete()
                        logger.debug(f"✓ Deleted event: {summary} ({uid})")
                    stats["deleted"] += 1
                except Exception as e:
                    logger.error(f"✗ Error deleting event {uid}: {e}")
                    stats["errors"] += 1

        # Print summary
        logger.info(f"{'=' * 60}")
        logger.info("Sync Summary:")
        logger.info(f"  Created: {stats['created']}")
        logger.info(f"  Updated: {stats['updated']}")
        logger.info(f"  Deleted: {stats['deleted']}")
        logger.info(f"  Unchanged: {stats['unchanged']}")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"{'=' * 60}")

        return stats


def main():
    """Main entry point"""
    config = Config.from_env()
    syncer = ICSCalDAVSync(config)

    # Perform sync
    dry_run = config.dry_run
    if dry_run:
        logger.info("Performing dry run...")
    else:
        logger.info("Performing actual sync...")

    syncer.sync()


if __name__ == "__main__":
    main()
