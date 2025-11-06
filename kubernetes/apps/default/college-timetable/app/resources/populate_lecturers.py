#!/usr/bin/env python3
"""
Helper script to populate lecturers.json with all lecturer acronyms found in the schedule.
Run this once to get a template with all acronyms, then manually fill in the full names.
"""

import json
import sys
from pathlib import Path

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
            print("Warning: Could not parse existing lecturers.json")

    # Merge: keep existing mappings, add new acronyms with placeholder
    output = {}
    output["_comment"] = "Fill in the full names for each lecturer acronym"
    output["_instructions"] = "Format: 'Acronym': 'Full Name (Title if applicable)'"

    new_count = 0
    for acronym in sorted(lecturers):
        if acronym in existing_mappings:
            output[acronym] = existing_mappings[acronym]
        else:
            output[acronym] = f"TODO: Fill in full name for {acronym}"
            new_count += 1

    # Write to file
    with open(lecturers_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Updated {lecturers_path}")
    print(f"  - Existing mappings: {len(existing_mappings)}")
    print(f"  - New acronyms to fill: {new_count}")
    print(f"  - Total entries: {len(output) - 2}")  # -2 for comment fields

    if new_count > 0:
        print(f"\n⚠ Please edit {lecturers_path} and fill in the full names")
        print("   Look for entries starting with 'TODO:'")
    else:
        print("\n✓ All lecturer acronyms already have mappings!")


def validate_lecturers_file():
    """Validate lecturers.json file"""

    config = Config.from_env()
    lecturers_path = Path(config.lecturers_json_path)

    if not lecturers_path.exists():
        print(f"❌ File not found: {lecturers_path}")
        return False

    try:
        with open(lecturers_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False

    # Check for TODO entries
    todo_entries = [
        k for k, v in data.items() if isinstance(v, str) and v.startswith("TODO:")
    ]

    if todo_entries:
        print(f"⚠ Found {len(todo_entries)} incomplete entries:")
        for entry in todo_entries[:5]:  # Show first 5
            print(f"  - {entry}: {data[entry]}")
        if len(todo_entries) > 5:
            print(f"  ... and {len(todo_entries) - 5} more")
        return False

    valid_entries = [k for k in data.keys() if not k.startswith("_")]
    print(f"✓ Valid lecturers.json with {len(valid_entries)} mappings")
    return True


def main():
    """Main entry point"""

    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        validate_lecturers_file()
    else:
        print("=" * 60)
        print("Lecturer Mapping Helper")
        print("=" * 60)
        populate_lecturers_template()
        print("\n" + "=" * 60)
        print("Next steps:")
        print("1. Open lecturers.json")
        print("2. Replace 'TODO: ...' entries with actual full names")
        print("3. Run: python populate_lecturers.py validate")
        print("4. Run your sync script")
        print("=" * 60)


if __name__ == "__main__":
    main()
