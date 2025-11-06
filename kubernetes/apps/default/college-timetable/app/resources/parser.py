"""
Parses calendar events from ICS format.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from icalendar import Component

logger = logging.getLogger(__name__)


class EventParser:
    """Parses and enriches calendar events"""

    def __init__(self, lecturers_json_path: str = "lecturers.json"):
        """
        Initialize parser with lecturer data.

        Args:
            lecturers_json_path: Path to JSON file with lecturer full names
        """
        self.lecturers_map = self._load_lecturers(lecturers_json_path)

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
        shortnames: Dict[str, str],
        lecturers: List[str],
        skip_holidays: Set[str],
    ) -> Optional[Dict[str, str]]:
        """
        Parse event summary and extract structured data.

        Args:
            component: iCalendar VEVENT component
            shortnames: Dict of subject short names to full names
            lecturers: Dict of lecturer acronyms (from fetcher)
            skip_holidays: Set of holiday/break names to skip

        Returns:
            Dict with parsed data or None if event should be skipped
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
            "location": "",
        }

        # 1️⃣ Extract short name at the beginning
        # Sort by length (longest first) to avoid partial matches
        for short in sorted(shortnames.keys(), key=len, reverse=True):
            if line.startswith(short):
                result["short"] = shortnames[short] or short
                line = line[len(short) :].strip()
                break

        # If no short name matched, skip this event
        if not result["short"]:
            logger.warning(f"Skipping event with unmatched short name: {summary}")
            return None

        # 2️⃣ Extract event type (wyk, ćw, lab)
        type_match = re.match(r"^(wyk|ćw|lab)\b", line)
        if type_match:
            result["type"] = type_match.group(1)
            line = line[type_match.end() :].strip()

        # 3️⃣ Extract all lecturers
        # Keep extracting while we find matches
        while line:
            # Sort by length to avoid partial matches
            for lecturer_acronym in sorted(lecturers, key=len, reverse=True):
                if line.startswith(lecturer_acronym):
                    # Get full name from our JSON mapping, fallback to acronym
                    full_name = self.lecturers_map.get(
                        lecturer_acronym, lecturer_acronym
                    )
                    result["lecturer"].append(full_name)
                    line = line[len(lecturer_acronym) :].strip()
                    break

            else:
                break  # No more lecturers found

        # 4️⃣ The rest is location
        if line:
            location = line.strip()
            # Format location nicely
            if "s.lab." not in location and len(location.split(" - ")) >= 2:
                parts = location.split(" - ")
                result["location"] = f"{parts[0].strip()} ({parts[1].strip()})"
            else:
                result["location"] = location

        # Build description
        description_parts = []
        if result["location"]:
            description_parts.append(f"Sala: {result['location']}")
        if result["lecturer"]:
            description_parts.append(f"Prowadzący: {', '.join(result['lecturer'])}")

        # Build summary
        summary_parts = []
        if result["type"]:
            summary_parts.append(result["type"].upper())
        if result["short"]:
            summary_parts.append(result["short"])

        return {
            "summary": " - ".join(summary_parts),
            "description": "\n".join(description_parts),
            "type": result["type"],
            "location": result["location"],
            "lecturers": result["lecturer"],
        }
