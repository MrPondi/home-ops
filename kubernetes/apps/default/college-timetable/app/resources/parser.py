"""
Parses calendar events from ICS format.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import caldav
from icalendar import Calendar, Component

from config import Config
from fetcher import PlanFetcher

logger = logging.getLogger(__name__)


@dataclass
class ParsedEvent:
    summary: str
    description: str
    type: str
    location: str
    lecturers: str


@dataclass
class ParsedIcsEvent:
    """Represents a parsed calendar event with its hash."""

    event_str: str
    event_str_hash: str
    content_hash: str


@dataclass
class TimetableData:
    """Container for all timetable-related data."""

    shortnames: dict
    lecture_types: set
    lecturers: dict
    lecture_halls: dict


class EventParser:
    """Parses and enriches calendar events"""

    UID_PREFIX = "AT4S_"
    LECTURE_TYPE_LECTURE = "wyk"  # "wykład" (lecture in Polish)
    PRIMARY_CALENDAR_IDX = 0
    SECONDARY_CALENDAR_IDX = 1

    def __init__(self, config: Config):
        """
        Initialize parser with lecturer data.

        Args:
            lecturers_json_path: Path to JSON file with lecturer full names
        """
        self.lecturers_map = self._load_lecturers(config.lecturers_json_path)
        self.config = config
        self.fetcher = PlanFetcher(config.course_id)

    def _load_lecturers(self, json_path: str) -> Dict[str, str]:
        """
        Load lecturer full names from JSON file.

        Expected format:
        {
            "JK": "Jan Kowalski",
            "AM": "Anna Nowak"
        }

        Args:
            json_path: Path to JSON file

        Returns:
            Dict mapping acronyms to full names
        """
        path = Path(json_path)

        if not path.exists():
            logger.warning(f"Lecturers file not found: {json_path}")
            logger.info("Creating empty lecturers.json template")

            # Create empty template
            path.write_text(json.dumps({}, indent=2))
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded {len(data)} lecturer mappings from {json_path}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {json_path}: {e}")
            return {}

    def parse_event(
        self,
        component: Component,
        timetable_data: TimetableData,
        skip_holidays: Set[str],
    ) -> Optional[ParsedEvent]:
        """
        Parse event summary and extract structured data.

        Args:
            component: iCalendar VEVENT component
            timetable_data: Contains shortnames, lecturers, lecture_types, lecture_halls
            skip_holidays: Set of holiday/break names to skip

        Returns:
            ParsedEvent with parsed data or None if event should be skipped
        """
        summary = component.get("summary")
        if not summary:
            return None

        # Normalize whitespace
        line = " ".join(summary.split())

        # Skip holidays and breaks
        if line.strip() in skip_holidays:
            return None

        result = {
            "short": "",
            "type": "",
            "lecturer": [],
            "location": [],
        }

        original_line = line  # Keep for logging

        # Extract short name at the beginning
        short_name, line = self._extract_token(
            line, timetable_data.shortnames.keys(), must_match=True
        )

        if short_name:
            result["short"] = timetable_data.shortnames[short_name]
        else:
            logger.warning(f"Skipping event with unmatched short name: {original_line}")
            return None

        # Extract event type
        event_type, line = self._extract_token(
            line, timetable_data.lecture_types, must_match=False
        )

        if event_type:
            result["type"] = event_type

        # Extract all lecturers
        lecturers, line = self._extract_all_tokens(
            line, timetable_data.lecturers.keys()
        )

        for lecturer_acronym in lecturers:
            # Use consistent mapping source
            full_name = self.lecturers_map.get(lecturer_acronym, lecturer_acronym)
            result["lecturer"].append(full_name)

        # Extract all locations
        locations, line = self._extract_all_tokens(
            line, timetable_data.lecture_halls.keys()
        )

        for hall_code in locations:
            result["location"].append(
                timetable_data.lecture_halls.get(hall_code, hall_code)
            )

        # Log any unparsed remainder
        if line.strip():
            logger.debug(f"Unparsed text in '{original_line}': '{line.strip()}'")

        # Build description
        description_parts = []
        if result["location"]:
            description_parts.append(f"Sala: {', '.join(result['location'])}")
        if result["lecturer"]:
            description_parts.append(f"Prowadzący: {', '.join(result['lecturer'])}")

        # Build summary
        summary_parts = []
        if result["type"]:
            summary_parts.append(result["type"].upper())
        if result["short"]:
            summary_parts.append(result["short"])

        return ParsedEvent(
            summary=" - ".join(summary_parts),
            description="\n".join(description_parts),
            type=result["type"],
            location=result["location"],
            lecturers=result["lecturer"],
        )

    def _extract_token(
        self, text: str, candidates: Iterable[str], must_match: bool = False
    ) -> tuple[Optional[str], str]:
        """
        Extract a single token from the beginning of text.

        Args:
            text: Input text to parse
            candidates: List of possible tokens to match
            must_match: If True, log warning when no match found

        Returns:
            Tuple of (matched_token, remaining_text)
        """
        text = text.strip()

        # Sort by length (longest first) to avoid partial matches
        for candidate in sorted(candidates, key=len, reverse=True):
            # Check if text starts with candidate followed by space or end of string
            if text == candidate:
                return candidate, ""
            elif text.startswith(candidate + " "):
                remaining = text[len(candidate) :].strip()
                return candidate, remaining

        if must_match:
            logger.debug(f"No token matched in: {text[:50]}...")

        return None, text

    def _extract_all_tokens(
        self, text: str, candidates: Iterable[str]
    ) -> tuple[List[str], str]:
        """
        Extract all consecutive tokens from the beginning of text.

        Args:
            text: Input text to parse
            candidates: List of possible tokens to match

        Returns:
            Tuple of (list_of_matched_tokens, remaining_text)
        """
        matched = []
        text = text.strip()

        # Sort by length (longest first) to avoid partial matches
        sorted_candidates = sorted(candidates, key=len, reverse=True)

        while text:
            found = False

            for candidate in sorted_candidates:
                # Check if text starts with candidate followed by space or end
                if text == candidate:
                    matched.append(candidate)
                    text = ""
                    found = True
                    break
                elif text.startswith(candidate + " "):
                    matched.append(candidate)
                    text = text[len(candidate) :].strip()
                    found = True
                    break

            if not found:
                break

        return matched, text

    def parse_ics_file(
        self,
        server_events: Dict[int, Dict[str, Tuple[caldav.Event, str]]],
    ) -> Dict[int, Dict[str, ParsedIcsEvent]]:
        """
        Parse ICS file and extract events.

        Args:
            server_events: Existing events on the server for change detection

        Returns:
            Dict mapping calendar_index -> {UID: ParsedEvent}
        """
        try:
            # Initialize result structure
            events = {i: {} for i in range(len(self.config.calendar_names))}

            # Fetch and parse all data sources
            logger.info("Fetching ICS file")
            ical_content = self.fetcher.fetch_ics()
            cal = Calendar.from_ical(ical_content)

            logger.info("Fetching timetable data")
            timetable_data = self._fetch_timetable_data()

            # Process each event in the calendar
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue

                try:
                    self._process_event(
                        component, timetable_data, server_events, events
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to process event {component.get('uid', 'unknown')}: {e}"
                    )
                    continue

            total_events = sum(len(e) for e in events.values())
            logger.info(f"Parsed {total_events} events from ICS file")
            return events

        except Exception as e:
            logger.error(f"Failed to parse ICS file: {e}")
            raise

    def _fetch_timetable_data(self) -> TimetableData:
        """Fetch and parse all timetable-related data."""
        logger.info("Getting timetable HTML")
        timetable_html = self.fetcher.fetch_timetable_html()

        logger.debug("Parsing timetable data")
        return TimetableData(
            shortnames=self.fetcher.get_all_short_names(
                timetable_html, self.config.skip_holidays
            ),
            lecture_types=self.fetcher.get_all_lecture_types(timetable_html),
            lecturers=self.fetcher.get_all_lecturers(timetable_html),
            lecture_halls=self.fetcher.get_all_lecture_halls(timetable_html),
        )

    def _process_event(
        self,
        component,
        timetable_data: TimetableData,
        server_events: Dict[int, Dict[str, Tuple[caldav.Event, str]]],
        events: Dict[int, Dict[str, ParsedIcsEvent]],
    ) -> None:
        """Process a single event component."""
        # Parse the event
        parsed_event = self.parse_event(
            component,
            timetable_data,
            skip_holidays=self.config.skip_holidays,
        )

        if not parsed_event:
            return  # Event was skipped

        # Determine target calendar
        calendar_idx = self._determine_calendar_index(parsed_event)

        # Update component with parsed data
        component["summary"] = parsed_event.summary
        component.add("description", parsed_event.description)
        component.add("location", self.config.default_location)

        # Generate UID
        uid = f"{self.UID_PREFIX}{self.config.course_id}_{component['uid']}"
        component["uid"] = uid

        # Create event with proper versioning
        parsed_event_obj = self._create_parsed_event(
            component, uid, calendar_idx, server_events
        )

        events[calendar_idx][uid] = parsed_event_obj

    def _determine_calendar_index(self, parsed_event: ParsedEvent) -> int:
        """
        Determine which calendar this event belongs to.

        If multiple calendars are configured:
        - Lectures (wyk) go to primary calendar (index 0)
        - Other events (labs, exercises, etc.) go to secondary calendar (index 1)
        """
        if len(self.config.calendar_names) > 1:
            is_lecture = parsed_event.type == self.LECTURE_TYPE_LECTURE
            return (
                self.PRIMARY_CALENDAR_IDX if is_lecture else self.SECONDARY_CALENDAR_IDX
            )
        return self.PRIMARY_CALENDAR_IDX

    def _create_parsed_event(
        self,
        component,
        uid: str,
        calendar_idx: int,
        server_events: Dict[int, Dict[str, Tuple[caldav.Event, str]]],
    ) -> ParsedIcsEvent:
        """
        Create a ParsedEvent with proper versioning and hashing.

        This handles:
        1. Sequence number incrementing for existing events
        2. DTSTAMP handling for change detection
        3. Hash generation for comparing event content
        """
        # Create a copy for hashing (without updated sequence/dtstamp)
        component_hash = component.copy()

        # Handle existing events on server
        if uid in server_events[calendar_idx]:
            self._apply_server_metadata(
                component, component_hash, uid, calendar_idx, server_events
            )
        else:
            # New event - use start time as timestamp
            component_hash["dtstamp"] = component["dtstart"]

        # Convert to iCalendar format
        event_str = self._component_to_ical_string(component)
        event_str_hash = self._component_to_ical_string(component_hash)

        # Normalize for consistent comparison
        event_str = re.sub(r"\r\n?", "\n", event_str).strip()
        event_str_hash = self._canonicalize_for_hashing(event_str_hash)

        # Generate content hash
        content_hash = hashlib.md5(event_str_hash.encode()).hexdigest()

        return ParsedIcsEvent(
            event_str=event_str,
            event_str_hash=event_str_hash,
            content_hash=content_hash,
        )

    def _apply_server_metadata(
        self,
        component,
        component_hash,
        uid: str,
        calendar_idx: int,
        server_events: Dict[int, Dict[str, Tuple[caldav.Event, str]]],
    ) -> None:
        """Apply metadata from existing server event (sequence number, dtstamp)."""
        server_event_data = server_events[calendar_idx][uid][0].data.strip("\n")
        server_cal = Calendar.from_ical(server_event_data)

        for server_component in server_cal.walk():
            if server_component.name == "VEVENT":
                # For hashing, use the old sequence/dtstamp
                current_sequence = server_component.get("sequence", 0)
                component_hash["dtstamp"] = server_component.get(
                    "dtstamp", component["dtstart"]
                )
                component_hash["sequence"] = server_component.get("sequence", 1)

                # For the actual event, increment the sequence
                component["sequence"] = current_sequence + 1
                break

    def _component_to_ical_string(self, component) -> str:
        """Convert component to iCalendar string, wrapping in VCALENDAR if needed."""
        event_str = component.to_ical().decode("utf-8")

        if not event_str.startswith("BEGIN:VCALENDAR"):
            vcal = Calendar()
            vcal.add("prodid", "-//ATS4 Sync//PL")
            vcal.add("version", "2.0")
            vcal.add_component(component)
            event_str = vcal.to_ical().decode("utf-8")

        return event_str

    def _canonicalize_for_hashing(self, ical_str: str) -> str:
        """
        Canonicalize iCalendar string for consistent hashing.

        This removes:
        - Line continuation whitespace (iCal format uses CRLF + space for long lines)
        - Inconsistent line endings
        """
        # Remove line continuation (CRLF/LF followed by space or tab)
        ical_str = re.sub(r"(?:\r?\n)[ \t]", "", ical_str)
        # Normalize remaining line endings
        ical_str = re.sub(r"\r\n?", "\n", ical_str)
        return ical_str.strip()
