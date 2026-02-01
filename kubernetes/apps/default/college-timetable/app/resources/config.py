"""
Configuration management for CalDAV sync.
"""

import os
from dataclasses import dataclass, field
from typing import List, Literal, Set, cast
from zoneinfo import ZoneInfo

ICS_SELECTOR = Literal[1, 2, 3, 4, 5, 6, 7, 8]


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
    course_ics_id: int
    course_ics_selector: ICS_SELECTOR = 1

    # Lecturers data
    lecturers_json_path: str = "/data/lecturers.json"

    # Default location for events
    default_location: str = "Zygmunta Krasińskiego 8, 40-019 Katowice, Polska"

    # Timezone for events
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Warsaw"))

    # Events to skip
    skip_holidays: Set[str] = field(
        default_factory=lambda: {"ŚWIĘTA", "DNI WOLNE", "Dni rektorskie", "Dni świąteczne", "Semestr Start", "Początek semestru", "Wakacje zimowe", "Wakacje wiosenne"}
    )

    # Sync settings
    dry_run: bool = False

    # Apple CalDAV specific settings
    calendar_fields_to_pop: Set[str] = field(
        default_factory=lambda: {
            "PRODID",
            "DTSTAMP",
            "SEQUENCE",
            "LAST-MODIFIED",
            "X-APPLE-STRUCTURED-LOCATION",
        }
    )

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
            course_ics_id=int(os.getenv("COURSE_ICS_ID", "")),
            course_ics_selector=cast(
                ICS_SELECTOR,
                int(os.getenv("COURSE_ICS_SELECTOR", "1")),
            ),
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
