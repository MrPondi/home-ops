"""
Handles fetching data from the plan.polsl.pl website.
"""

import logging
import re
import ssl
import time
from functools import wraps
from typing import Dict, Optional, Set

import httpx
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

logger = logging.getLogger(__name__)


class PlanFetcher:
    """Fetches schedule data from plan.polsl.pl"""

    BASE_URL = "https://plan.polsl.pl/plan.php"

    def __init__(self, course_ics_id: int, course_ics_selector: int):
        self.course_ics_id = course_ics_id
        self.course_ics_selector = course_ics_selector
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")
        self.max_retries: int = 3
        self.base_delay: float = 1.0

    def _retry_with_backoff(self, func):
        """Decorator that implements exponential backoff retry logic"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
                except (
                    httpx.ReadTimeout,
                    httpx.ConnectTimeout,
                    httpx.TimeoutException,
                ) as e:
                    last_exception = e
                    if attempt < self.max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s, etc.
                        delay = self.base_delay * (2**attempt)
                        logger.warning(
                            f"Timeout on attempt {attempt + 1}/{self.max_retries}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {self.max_retries} attempts failed.")
                except httpx.HTTPStatusError:
                    # Don't retry on HTTP errors (4xx, 5xx)
                    raise

            # If we get here, all retries failed
            if last_exception is not None:
                raise last_exception

        return wrapper

    def fetch_plan(
        self,
        id: Optional[int] = None,
        type: int = 0,
        additional_params: dict = {},
    ) -> bytes:
        """
        Fetch plan data from the server with automatic retries.

        Args:
            id: Course or lecturer ID (defaults to course_ics_id)
            type: Plan type (0=course, 10=lecturer)
            additional_params: Additional query parameters

        Returns:
            Raw response content as bytes

        Raises:
            httpx.TimeoutException: If all retry attempts fail
            httpx.HTTPStatusError: If server returns error status
        """
        if id is None:
            id = self.course_ics_id

        @self._retry_with_backoff
        def _fetch():
            params = {
                "type": type,
                "id": id,
            }
            if additional_params:
                params.update(additional_params)

            with httpx.Client(verify=self.ssl_context, timeout=60.0) as client:
                response = client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                return response.content

        return _fetch()

    def fetch_ics(self) -> str:
        """Fetch the ICS file for the course"""
        content = self.fetch_plan(
            self.course_ics_id, 0, {"cvsfile": "true", "wd": self.course_ics_selector}
        )

        return content.decode("utf-8")

    def fetch_timetable_html(self) -> str:
        """Fetch the HTML timetable for the course"""
        content = self.fetch_plan(
            self.course_ics_id, 0, {"wd": self.course_ics_selector, "winW": 2544, "winH": 1263, "loadBG": "000000"}
        ).decode("iso-8859-2")
        return content

    def get_all_short_names(
        self, content: Optional[str] = None, skip_holidays: Set[str] = set()
    ) -> Dict[str, str]:
        """
        Fetch and parse the legend to get all subject short names.

        Returns:
            Dict mapping subject short names to full names
        """
        if content is None:
            content = self.fetch_timetable_html()

        soup = BeautifulSoup(content, "html.parser")
        legend = soup.select_one("html body div#legend.dataBox div.data")

        if not legend:
            logger.warning("Legend not found")
            return {}

        return self._parse_legend_subjects(legend, skip_holidays)

    def _parse_legend_subjects(
        self, legend: Tag, skip_holidays: Set[str]
    ) -> Dict[str, str]:
        """
        Parse legend content to extract subject mappings.

        Args:
            legend: BeautifulSoup Tag containing the legend data

        Returns:
            Dict mapping subject short names to full names
        """
        subjects = {}
        hr_found = False
        current_short_name = None

        for element in legend.contents:
            # Skip everything before the <hr> separator
            if not hr_found:
                if isinstance(element, Tag) and element.name == "hr":
                    hr_found = True
                continue

            # Extract short name from <strong> tags
            if isinstance(element, Tag) and element.name == "strong":
                current_short_name = element.get_text(strip=True)

            # Extract and clean full name from text nodes
            elif isinstance(element, NavigableString) and current_short_name:
                full_name = (
                    element.text.removeprefix(" - ").split(", występowanie")[0].strip()
                )

                if full_name:
                    subjects[current_short_name] = full_name
                    current_short_name = None
                elif current_short_name not in skip_holidays:
                    logger.warning(
                        f"Could not parse full name for subject: {current_short_name}"
                    )
                    subjects[current_short_name] = current_short_name
                    current_short_name = None

        return subjects

    def get_all_lecturers(self, content: Optional[str] = None) -> Dict[str, int]:
        """
        Fetch and parse the HTML to get all lecturers.
        Returns short names (acronyms) only.

        Returns:
            List of lecturer acronyms
        """
        if content is None:
            content = self.fetch_timetable_html()

        lecturers = {}
        soup = BeautifulSoup(content, "html.parser")
        hyperlinks = soup.find_all("a", href=True)

        for link in hyperlinks:
            href = link["href"]
            if isinstance(href, str) and href.startswith("plan.php?type=10"):
                lecturer_acronym = link.text.strip()
                # The full name will be resolved by EventParser using lecturers.json
                lecturer_id = href.split("id=")[1]
                lecturers[lecturer_acronym] = lecturer_id
        return lecturers

    def get_all_lecture_halls(self, content: Optional[str] = None) -> Dict[str, int]:
        """
        Fetch and parse the HTML to get all lecture halls.
        Returns short names (acronyms) only.

        Returns:
            List of lecture hall acronyms
        """
        if content is None:
            content = self.fetch_timetable_html()

        lecture_halls = {}
        soup = BeautifulSoup(content, "html.parser")
        hyperlinks = soup.find_all("a", href=True)

        for link in hyperlinks:
            href = link["href"]
            if isinstance(href, str) and href.startswith("plan.php?type=20"):
                hall_name = link.text.strip()
                if type1 := re.fullmatch(
                    r"([0-9]{4}) - ([0-9]{3}) - [A-Za-z]+", hall_name
                ):
                    lecture_halls[hall_name] = f"{type1.group(1)} ({type1.group(2)})"
                    continue
                elif type2 := re.fullmatch(r"([A-Z]+) ([A-Z]) - ([0-9]{4})", hall_name):
                    lecture_halls[hall_name] = (
                        f"{type2.group(3)} ({type2.group(1)} {type2.group(2)})"
                    )
                    continue
                elif type3 := re.fullmatch(
                    r"([0-9]+) - s\.lab\. ([0-9]{3})", hall_name
                ):
                    lecture_halls[hall_name] = (
                        f"{type3.group(1)} (s.lab {type3.group(2)})"
                    )
                    continue
                lecture_halls[hall_name] = hall_name

        return lecture_halls

    def get_all_lecture_types(self, content: Optional[str] = None) -> Set[str]:
        """
        Fetch and parse the HTML to get all lecture types.

        Returns:
            Dict mapping lecture types to their full names
        """
        if content is None:
            content = self.fetch_timetable_html()

        lecture_types = set()
        soup = BeautifulSoup(content, "html.parser")
        coursedivs = soup.find_all("div", class_="coursediv")
        for coursediv in coursedivs:
            if coursediv.get("name") != "course":
                continue
            for child in coursediv.contents:
                if isinstance(child, NavigableString):
                    name = child.strip().split(", ")
                    if len(name) == 2:
                        lecture_types.add(name[1])
                    break

        return lecture_types
