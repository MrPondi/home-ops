#!/usr/bin/env python3
"""
Helper script to populate lecturers.json with all lecturer acronyms found in the schedule.
"""

import json
from pathlib import Path

from bs4 import BeautifulSoup
from rich.progress import track

from config import Config
from fetcher import PlanFetcher


def populate_lecturers_template():
    """Create lecturers.json template with all found acronyms"""

    config = Config.from_env()
    fetcher = PlanFetcher(config.course_id)

    print("Fetching lecturer acronyms from schedule...")
    lecturers = fetcher.get_all_lecturers()

    if not lecturers:
        print("No lecturers found!")
        return

    print(f"Found {len(lecturers)} lecturer acronyms")

    # Load existing mappings if file exists
    lecturers_path = Path(config.lecturers_json_path)
    existing_mappings = {}

    if lecturers_path.exists():
        try:
            with open(lecturers_path, "r", encoding="utf-8") as f:
                existing_mappings = json.load(f)
                # Remove comment fields
                existing_mappings = {
                    k: v for k, v in existing_mappings.items() if not k.startswith("_")
                }
            print(f"Loaded {len(existing_mappings)} existing mappings")
        except json.JSONDecodeError:
            print(f"Warning: Could not parse existing file {lecturers_path}")

    # Merge: keep existing mappings
    output = {}

    new_count, update_count = 0, 0
    for acronym, lecturer_id in track(
        sorted(lecturers.items()), description="Processing acronyms ..."
    ):
        full_name = get_lecturer_full_name(lecturer_id, fetcher)
        if acronym in existing_mappings:
            if existing_mappings[acronym] != full_name:
                print(
                    f"Replacing existing mapping for {acronym}: {existing_mappings[acronym]} -> {full_name}"
                )
                update_count += 1
        else:
            print(f"Adding new mapping: {acronym} -> {full_name}")
            new_count += 1
        output[acronym] = full_name
        existing_mappings.pop(acronym, None)

    output.update(existing_mappings)  # Add unchanged mappings at the end
    # Write to file
    with open(lecturers_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Updated {lecturers_path}")
    print(f"  - Unchanged mappings: {len(existing_mappings) - update_count}")
    print(f"  - Updated acronyms: {update_count}")
    print(f"  - New acronyms: {new_count}")
    print(f"  - Total entries: {len(output)}")


def get_lecturer_full_name(id: int, fetcher: PlanFetcher) -> str:
    """
    Fetch and parse the legend to get the full name of a lecturer by their ID.

    Args:
        id (int): The ID of the lecturer.
        fetcher (PlanFetcher): The PlanFetcher instance to use for fetching data.

    Returns:
        str: The full name of the lecturer, or "Unknown" if not found.
    """
    ics_file = fetcher.fetch_plan(
        id, 10, {"winW": 2544, "winH": 1263, "loadBG": 000000}
    ).decode("iso-8859-2")

    soup = BeautifulSoup(ics_file, "html.parser")
    fullname = (
        soup.select("html body div div.title")[1]
        .text.strip()
        .split(" - ")[1]
        .rsplit(", ", 2)[0]
    )
    if ", prof." in fullname:
        fullname = f"prof. {fullname.split(', prof. ', 1)[1]}"

    return fullname if fullname else "Unknown"


def main():
    """Main entry point"""

    print("=" * 60)
    print("Lecturer Mapper")
    print("=" * 60)

    populate_lecturers_template()


if __name__ == "__main__":
    main()
