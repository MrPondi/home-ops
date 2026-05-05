#!/usr/bin/env python3
"""
Sync ICS file events to a CalDAV server efficiently and safely.
Handles event creation, updates, and deletions with proper error handling.
"""

import asyncio
import difflib
import hashlib
import logging
from typing import Dict

from caldav.async_davclient import AsyncDAVClient, get_davclient
from caldav.collection import Calendar
from icalendar import Calendar as Cal
from rich.progress import track

from config import Config
from parser import EventParser, ParsedServerEvent

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
        self.parser = EventParser(config)

    async def get_or_create_calendars(self, client: AsyncDAVClient) -> list[Calendar]:
        """Get existing calendars or create new ones."""
        principal = await client.get_principal()
        all_calendars = await client.get_calendars(principal)
        found_calendars = []

        for calendar_name in self.config.calendar_names:
            for cal in all_calendars:
                calname = await cal.get_display_name()  # type: ignore
                if calname == calendar_name:
                    logger.info(f"Found existing calendar: {calendar_name}")
                    found_calendars.append(cal)
                    break

            else:
                logger.warning(f"Calendar '{calendar_name}' not found. Creating one.")
                new_cal = principal.make_calendar(name=calendar_name)
                logger.info(f"Created new calendar: {calendar_name}")
                found_calendars.append(new_cal)

        return found_calendars

    async def get_server_events(
        self, calendars: list[Calendar]
    ) -> Dict[int, Dict[str, ParsedServerEvent]]:
        """
        Get all events from CalDAV server.

        Returns:
            Dict mapping calendar_index -> {UID: ParsedServerEvent}
        """

        server_events = {i: {} for i in range(len(calendars))}

        for idx, calendar in enumerate(calendars):
            events = await calendar.get_events()  # type: ignore

            for event in events:
                try:
                    cal = Cal.from_ical(event.data)

                    clean_cal = Cal()
                    for key in cal.keys():
                        if key.upper() not in self.config.calendar_fields_to_pop:
                            clean_cal.add(key, cal[key])

                    for component in cal.walk():
                        if component.name == "VEVENT":
                            for field in self.config.calendar_fields_to_pop:
                                component.pop(field, None)

                            # Add the cleaned event to our clean calendar container
                            clean_cal.add_component(component)

                            # Generate the Hash
                            event_str_for_hash = self.parser.canonicalize_for_hashing(
                                clean_cal.to_ical().decode("utf-8")
                            )
                            content_hash = hashlib.md5(
                                event_str_for_hash.encode()
                            ).hexdigest()

                            uid = str(component.get("uid"))
                            server_events[idx][uid] = ParsedServerEvent(
                                event=event,
                                event_str=event.data,
                                event_str_hash=event_str_for_hash,
                                content_hash=content_hash,
                            )
                            break
                except Exception as e:
                    logger.error(f"Error reading server event: {e}")
                    continue

        total_events = sum(len(e) for e in server_events.values())
        logger.info(f"Found {total_events} events on server")
        return server_events

    async def sync(self) -> Dict[str, int]:
        """
        Sync ICS file to CalDAV server.

        Args:
            dry_run: If True, only show what would be done without making changes

        Returns:
            Dict with counts of created, updated, deleted, unchanged events
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0, "errors": 0}

        async with await get_davclient(
            url=self.config.caldav_url,
            username=self.config.username,
            password=self.config.password,
        ) as client:
            # Get or create calendars
            calendars = await self.get_or_create_calendars(client)

            if len(calendars) != len(self.config.calendar_names):
                logger.error("Not all calendars were found. Aborting sync.")
                return stats

            # Get server events
            server_events = await self.get_server_events(calendars)

            # Parse local ICS file
            local_events = self.parser.parse_ics_file(server_events)

            # Sync each calendar
            for i in range(len(calendars)):
                logger.info(f"{'=' * 60}")
                logger.info(f"Syncing calendar: {self.config.calendar_names[i]}")

                local_cal_events = local_events[i]
                server_cal_events = server_events[i]

                local_uids = set(local_cal_events.keys())
                server_uids = set(server_cal_events.keys())

                # Events to create (in local but not on server)
                to_create = local_uids - server_uids

                # Events to update (in both & different hash)
                to_update = local_uids & server_uids
                for uid in list(to_update):
                    local_event = local_cal_events[uid]
                    server_event = server_cal_events[uid]
                    if local_event.content_hash == server_event.content_hash:
                        to_update.remove(uid)
                        stats["unchanged"] += 1

                # Events to delete (on server but not in local)
                to_delete = server_uids - local_uids

                logger.info("Sync Plan:")
                logger.info(f"  To create: {len(to_create)}")
                logger.info(f"  To update: {len(to_update)}")
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
                            logger.debug(
                                f"[DRY RUN] Would create event: {summary} ({uid})"
                            )
                        else:
                            await calendars[i].add_event(event.event_str)
                            logger.debug(f"✓ Created event: {summary} ({uid})")
                        stats["created"] += 1
                    except Exception as e:
                        logger.error(f"✗ Error creating event {uid}: {e}")
                        event_data = local_cal_events[uid].event_str
                        logger.debug(f"Event data:\n{repr(event_data)}")
                        stats["errors"] += 1

                # Check and update existing events
                for uid in track(
                    list(to_update),
                    description=f"Updating events in {self.config.calendar_names[i]}",
                ):
                    try:
                        local_event = local_cal_events[uid]
                        server_event = server_cal_events[uid]

                        diff = "\n".join(
                            difflib.unified_diff(
                                server_event.event_str_hash.splitlines(),
                                local_event.event_str_hash.splitlines(),
                                lineterm="",
                            )
                        )
                        logger.debug(f"Event update diff: {diff}")
                        if self.config.dry_run:
                            logger.info(f"[DRY RUN] Would update event: {uid}")
                        else:
                            server_event.event.data = local_event.event_str
                            await server_event.event.save()
                            logger.debug(f"✓ Updated event: {uid}")
                        stats["updated"] += 1
                    except Exception as e:
                        logger.error(f"✗ Error updating event {uid}: {e}")
                        stats["errors"] += 1

                # Delete events not in local file
                for uid in track(
                    list(to_delete),
                    description=f"Deleting events from {self.config.calendar_names[i]}",
                ):
                    try:
                        server_event = server_cal_events[uid]
                        summary = next(
                            (
                                line.split("SUMMARY:")[1]
                                for line in server_event.event_str_hash.splitlines()
                                if line.startswith("SUMMARY:")
                            ),
                            "",
                        )
                        if self.config.dry_run:
                            logger.info(
                                f"[DRY RUN] Would delete event: {summary} ({uid})"
                            )
                        else:
                            await server_event.event.delete()
                            logger.debug(f"✓ Deleted event: {summary} ({uid})")
                        stats["deleted"] += 1
                    except Exception as e:
                        logger.error(f"✗ Error deleting event {uid}: {e}")
                        event_data = server_cal_events[uid].event_str
                        logger.debug(f"Event data:\n{repr(event_data)}")
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


async def main():
    """Main entry point"""
    config = Config.from_env()
    syncer = ICSCalDAVSync(config)

    # Perform sync
    dry_run = config.dry_run
    if dry_run:
        logger.info("Performing dry run...")
    else:
        logger.info("Performing actual sync...")

    await syncer.sync()


if __name__ == "__main__":
    asyncio.run(main())