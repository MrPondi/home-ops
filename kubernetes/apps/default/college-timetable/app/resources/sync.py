#!/usr/bin/env python3
"""
Sync ICS file events to a CalDAV server efficiently and safely.
Handles event creation, updates, and deletions with proper error handling.
"""

import difflib
import hashlib
import logging
import re
from typing import Dict, Tuple

import caldav
from icalendar import Calendar
from rich.progress import track

from config import Config
from fetcher import PlanFetcher
from parser import EventParser

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
        self.principal = self.client.principal()
        self.calendars = None
        self.fetcher = PlanFetcher(config.course_id)
        self.parser = EventParser(config.lecturers_json_path)

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

    def parse_ics_file(
        self, server_events: Dict[int, Dict[str, Tuple[caldav.Event, str]]]
    ) -> Dict[int, Dict[str, Tuple[str, str, str]]]:
        """
        Parse ICS file and extract events.

        Returns:
            Dict mapping calendar_index -> {UID: (event_data, content_hash)}
        """
        events = {i: {} for i in range(len(self.config.calendar_names))}

        logger.info("Fetching ICS file")
        ical_content = self.fetcher.fetch_ics()
        cal = Calendar.from_ical(ical_content)

        logger.info("Getting timetable HTML")
        timetable_html = self.fetcher.fetch_timetable_html()

        logger.debug("Parsing short names")
        shortnames = self.fetcher.get_all_short_names(
            timetable_html, self.config.skip_holidays
        )

        logger.debug("Parsing lecturers")
        lecturers = self.fetcher.get_all_lecturers(timetable_html)

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            # Parse the event
            parsed_event = self.parser.parse_event(
                component, shortnames, lecturers, self.config.skip_holidays
            )

            if not parsed_event:
                continue  # Event was skipped

            # Determine which calendar this event belongs to
            if len(self.config.calendar_names) > 1 and parsed_event["type"] != "wyk":
                calendar_idx = 1
            else:
                calendar_idx = 0

            # Update component with parsed data
            component["summary"] = parsed_event["summary"]
            component.add("description", parsed_event["description"])
            component.add("location", self.config.default_location)

            uid = str(component.get("uid"))

            component_hash = component.copy()
            if uid in set(server_events[calendar_idx].keys()):
                for server_component in Calendar.from_ical(
                    server_events[calendar_idx][uid][0].data.strip("\n")
                ).walk():
                    if server_component.name == "VEVENT":
                        component_hash["dtstamp"] = server_component.get(
                            "dtstamp", component["dtstart"]
                        )
                        component_hash["sequence"] = server_component.get("sequence", 1)
                        component["sequence"] = server_component.get("sequence", 0) + 1
                        break
            else:
                component_hash["dtstamp"] = component["dtstart"]

            event_str = component.to_ical().decode("utf-8")
            event_str_hash = component_hash.to_ical().decode("utf-8")

            # Wrap in VCALENDAR if not already
            if not event_str.startswith("BEGIN:VCALENDAR"):
                vcal = Calendar()
                vcal.add("prodid", "-//ATS4 Sync//PL")
                vcal.add("version", "2.0")
                vcal_hash = vcal.copy()
                vcal.add_component(component)
                vcal_hash.add_component(component_hash)
                event_str = vcal.to_ical().decode("utf-8")
                event_str_hash = vcal_hash.to_ical().decode("utf-8")

            event_str = re.sub(r"\r\n?", "\n", event_str).strip()
            # Canonicalize the event string for hashing
            event_str_hash = re.sub(r"(?:\r?\n)[ \t]", "", event_str_hash)
            event_str_hash = re.sub(r"\r\n?", "\n", event_str_hash).strip()

            # Create hash for change detection
            content_hash = hashlib.md5(event_str_hash.encode()).hexdigest()

            events[calendar_idx][uid] = (
                event_str.strip(),
                event_str_hash.strip(),
                content_hash,
            )

        total_events = sum(len(e) for e in events.values())
        logger.info(f"Parsed {total_events} events from ICS file")
        return events

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
        local_events = self.parse_ics_file(server_events)

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
                    event_data, event_diff_data, _ = local_cal_events[uid]
                    if summary := next(
                        (
                            line.split("SUMMARY:")[1]
                            for line in event_diff_data.splitlines()
                            if line.startswith("SUMMARY:")
                        ),
                        "<not found>",
                    ):
                        logger.debug(f"Creating event: {summary}")
                    if self.config.dry_run:
                        logger.debug(f"[DRY RUN] Would create event: {uid}")
                    else:
                        self.calendars[i].save_event(event_data)
                        logger.debug(f"✓ Created event: {uid}")
                    stats["created"] += 1
                except Exception as e:
                    logger.error(f"✗ Error creating event {uid}: {e}")
                    stats["errors"] += 1

            # Check and update existing events
            for uid in track(
                list(to_check),
                description=f"Checking updates in {self.config.calendar_names[i]}",
            ):
                try:
                    local_data, local_diff_data, local_hash = local_cal_events[uid]
                    server_event, server_hash = server_cal_events[uid]

                    if local_hash != server_hash:
                        diff = "\n".join(
                            difflib.unified_diff(
                                server_event.data.splitlines(),
                                local_diff_data.splitlines(),
                                fromfile="server_event",
                                tofile="local_event",
                                lineterm="",
                            )
                        )
                        logger.debug(f"Event update diff: {diff}")
                        if self.config.dry_run:
                            logger.info(f"[DRY RUN] Would update event: {uid}")
                        else:
                            server_event.data = local_data
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
                    if summary := next(
                        (
                            line.split("SUMMARY:")[1]
                            for line in server_event.data.splitlines()
                            if line.startswith("SUMMARY:")
                        ),
                        "<not found>",
                    ):
                        logger.debug(f"Deleting event: {summary}")
                    if self.config.dry_run:
                        logger.info(f"[DRY RUN] Would delete event: {uid}")
                    else:
                        server_event.delete()
                        logger.debug(f"✓ Deleted event: {uid}")
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
