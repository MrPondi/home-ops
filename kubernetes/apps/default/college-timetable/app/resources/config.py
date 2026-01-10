"""
Configuration management for CalDAV sync.
"""

import os
from dataclasses import dataclass, field
from typing import List, Set
from zoneinfo import ZoneInfo


@dataclass
class Config:
    """Configuration for CalDAV sync"""

    # CalDAV server settings
    caldav_url: str
    username: str
    password: str

    # Calendar settings
    calendar_names: List[str]

    # Course settings
    course_id: int

    # Lecturers data
    lecturers_json_path: str = "/data/lecturers.json"

    # Default location for events
    default_location: str = "Zygmunta Krasińskiego 8, 40-019 Katowice, Polska"

    # Timezone for events
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Warsaw"))

    # Events to skip
    skip_holidays: Set[str] = field(
        default_factory=lambda: {"ŚWIĘTA", "Wakacje zimowe", "DNI WOLNE"}
    )

    # CalDAV specific settings
    calendar_fields_to_pop: Set[str] = field(
        default_factory=lambda: {
            "PRODID",
            "DTSTAMP",
            "SEQUENCE",
            "LAST-MODIFIED",
            "X-APPLE-STRUCTURED-LOCATION",
        }
    )

    # Sync settings
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables"""
        calendar_names = [
            os.getenv("CALENDAR_NAME_1", "Studia Wykłady"),
            os.getenv("CALENDAR_NAME_2", "Studia Obowiązkowe"),
        ]

        return cls(
            caldav_url=os.getenv("CALDAV_URL", ""),
            username=os.getenv("USERNAME", ""),
            password=os.getenv("PASSWORD", ""),
            calendar_names=calendar_names,
            course_id=int(os.getenv("COURSE_ID", "")),
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
        )

    def validate(self) -> bool:
        """Validate configuration"""
        if not self.caldav_url:
            raise ValueError("CALDAV_URL is required")
        if not self.username:
            raise ValueError("USERNAME is required")
        if not self.password:
            raise ValueError("PASSWORD is required")
        if not self.calendar_names:
            raise ValueError("At least one calendar name is required")
        return True
