#!/usr/bin/env python
"""Audit kustomization list ordering against AGENTS.md conventions.

Rules checked per file (`resources:` lists in kustomization.yaml and ks.yaml
manifests, `spec.dependsOn` / `spec.components` / `spec.*` key order in
Flux Kustomizations):

1. `resources:` lists are divided into sections, each sorted internally
   (case-insensitive byte order, `./` prefix ignored), in this fixed order:
   1. files in the kustomization's own directory (`./<name>.yaml`)
   2. files in subdirectories (`./<subdir>/<name>.yaml`); comment-delimited
      groups are sub-sections, with the groups themselves sorted
   3. Flux Kustomizations (`./<path>/ks.yaml`, namespace overlays only)
   4. directory references (`./<folder>/`)
2. Flux Kustomization top-level keys alphabetized (apiVersion/kind/metadata/spec)
   and `spec.*` keys alphabetized, except `patches` which must be last (it is
   exempt from the alphabetization check).
3. `spec.dependsOn` follows the dependency-chain convention (NOT alphabetized):
   same-namespace deps first (by name), then `external-secrets-store`
   (ns `external-secrets`), then remaining cross-namespace deps (by name).
4. `spec.components` sorted plain path-alphabetical.

Usage:
    uv run scripts/kustomization_order_audit.py [--path kubernetes/] [--quiet]
Exit code 0 = conformant, 1 = violations or parse errors.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LIST_KEY_RE = re.compile(r"^([a-zA-Z][\w-]*):\s*(?:#.*)?$")
ITEM_RE = re.compile(r"^\s+-\s?(.*)$")

# relation of one path entry to the section it belongs in
def sort_key(path: str) -> str:
    s = path.lower().lstrip("./")
    return re.sub(r"(\d+)", lambda m: f"{int(m.group(1)):08d}", s)


def classify(path: str) -> int:
    """Section number for a resources entry path."""
    stripped = path[2:] if path.startswith("./") else path
    if "/" in stripped:
        if stripped.endswith("/"):
            return 4  # directory reference
        if stripped.endswith("/ks.yaml"):
            return 3  # Flux Kustomization
        return 2  # file in a subdirectory
    return 1  # file in the kustomization's own directory


def extract_list(lines: list[str], start: int) -> list[tuple[int, str, str]]:
    """Collect (line_no, kind_comment, raw) items of a list starting after `start`.

    Returns items as (line_no, comment_or_empty, path) where path is the
    logical entry (stripped of inline comments and quotes). Comment-only lines
    are yielded as (line_no, comment, "") to detect sub-section boundaries.
    """
    items = []
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if not (line.startswith("  ") or line.startswith("\t")):
            break
        m = ITEM_RE.match(line)
        if not m:
            i += 1
            continue
        raw = m.group(1).strip()
        if raw.startswith("#"):
            items.append((i + 1, raw, ""))
        else:
            path = raw.split("#")[0].strip().strip("'\"")
            pm = re.match(r"path:\s*(\S+)", path)
            if pm:
                path = pm.group(1)
            if ":" in path and not pm:
                i += 1
                continue  # inline object entry — not a path reference
            if path:
                items.append((i + 1, "", path))
        i += 1
    return items


def audit_resources(f: Path, lines: list[str], problems: list[str]) -> None:
    start = None
    for i, l in enumerate(lines):
        if re.match(r"^resources:\s*$", l):
            start = i
            break
    if start is None:
        return
    items = extract_list(lines, start)
    paths = [p for _, _, p in items if p]
    # compare against section-ordered, per-section sorted expectation
    expected: list[str] = []
    section: list[str] = []
    sections_seen = 0
    for p in paths:
        s = classify(p)
        if s < sections_seen:
            problems.append(f"{f}:{'section order'} section {s} after section {sections_seen} ({p!r})")
        if s != sections_seen and s > sections_seen:
            expected.extend(sorted(section, key=sort_key))
            section = []
            sections_seen = s
        section.append(p)
    expected.extend(sorted(section, key=sort_key))
    if paths != expected:
        problems.append(f"{f}: resources section ordering")
        for lineno, _, p in extract_list(lines, start):
            if p:
                problems.append(f"    {lineno:>{5}}: {p}")


def audit_comment_groups(f: Path, lines: list[str], problems: list[str]) -> None:
    """Comment-delimited sub-sections in section 2 must themselves be sorted.

    Groups are keyed by their last non-empty comment header; each group is
    sorted internally (already enforced by audit_resources grouping reset? no —
    group resets split sections). Here we check group ordering only.
    """
    start = None
    for i, l in enumerate(lines):
        if re.match(r"^resources:\s*$", l):
            start = i
            break
    if start is None:
        return
    items = extract_list(lines, start)
    groups: list[tuple[str, list[str]]] = []  # (comment, paths)
    current_comment = "_root_"
    for _, comment, path in items:
        if comment:
            if path == "":
                current_comment = comment.lstrip("# ").strip()
            continue
        if path and classify(path) == 2:
            if current_comment != "_root_":
                groups_single = [g for g in groups if g[0] == current_comment]
                if not groups_single:
                    groups.append((current_comment, [path]))
                else:
                    groups_single[0][1].append(path)
    names = [c for c, _ in groups]
    if names != sorted(names, key=sort_key):
        problems.append(f"{f}: comment-group ordering in subdirectory files section: {names}")


FLUX_SCHEMA_RE = re.compile(r"kustomize\.toolkit\.fluxcd\.io/kustomization")


def audit_flux(f: Path, text: str, problems: list[str]) -> None:
    # only flux Kustomization manifests (schema header or apiVersion present)
    if "kustomize.toolkit.fluxcd.io/v1" not in text and not FLUX_SCHEMA_RE.search(text):
        return
    docs = re.split(r"^---\s*$", text, flags=re.M)
    for doc in docs:
        doc_lines = doc.splitlines()
        in_spec = False
        top_keys: list[str] = []
        spec_keys: list[str] = []
        patches_seen = False
        patches_violated = False
        for l in doc_lines:
            if not l.strip() or l.lstrip().startswith("#"):
                continue
            indent = len(l) - len(l.lstrip(" "))
            m_top = re.match(r"^([a-zA-Z][\w-]*):", l) if indent == 0 else None
            if indent == 0 and m_top:
                key = m_top.group(1)
                if key == "spec":
                    in_spec = True
                    top_keys.append(key)
                    continue
                if in_spec:
                    # new top-level key: spec block ended
                    if top_keys != sorted(top_keys):
                        problems.append(f"{f}: top-level keys not alphabetized: {top_keys}")
                    if spec_keys != sorted(spec_keys):
                        problems.append(f"{f}: spec keys not alphabetized: {spec_keys}")
                    if patches_violated:
                        problems.append(f"{f}: spec.patches must be last: {spec_keys}")
                    in_spec = False
                top_keys.append(key)
                continue
            if in_spec and indent == 2:
                m2 = re.match(r"^  ([\w-]+):", l)
                if m2:
                    key = m2.group(1)
                    if key == "patches":
                        patches_seen = True
                    else:
                        if patches_seen:
                            patches_violated = True
                        spec_keys.append(key)
        if in_spec:
            if top_keys != sorted(top_keys):
                problems.append(f"{f}: top-level keys not alphabetized: {top_keys}")
            if spec_keys != sorted(spec_keys):
                problems.append(f"{f}: spec keys not alphabetized: {spec_keys}")
            if patches_violated:
                problems.append(f"{f}: spec.patches must be last: {spec_keys}")


def audit_depends_on(f: Path, text: str, problems: list[str]) -> None:
    if "kustomize.toolkit.fluxcd.io/v1" not in text:
        return
    docs = re.split(r"^---\s*$", text, flags=re.M)
    for doc in docs:
        lines = doc.splitlines()
        for i, l in enumerate(lines):
            if re.match(r"^  dependsOn:\s*$", l):
                entries = []
                j = i + 1
                while j < len(lines) and (lines[j].startswith("    ") or lines[j].strip() == ""):
                    nm = re.match(r"^\s*-\sname:\s*(\S+)$", lines[j])
                    if nm:
                        ns = None
                        if j + 1 < len(lines):
                            nsm = re.match(r"^\s+namespace:\s*(\S+)\s*$", lines[j + 1])
                            if nsm:
                                ns = nsm.group(1)
                        entries.append((nm.group(1), ns))
                        j += 2 if ns else 1
                        continue
                    nm2 = re.match(r"^\s{4}-\sname:\s*(\S+)$", lines[j])
                    if nm2:
                        entries.append((nm2.group(1), None))
                    j += 1
                groups = []
                for name, ns in entries:
                    if ns is None:
                        groups.append(0)
                    elif ns == "external-secrets":
                        groups.append(1)
                    else:
                        groups.append(2)
                if groups != sorted(groups):
                    problems.append(f"{f}: dependsOn violates dependency-chain order: {entries}")


def audit_components(f: Path, text: str, problems: list[str]) -> None:
    if "kustomize.toolkit.fluxcd.io/v1" not in text:
        return
    docs = re.split(r"^---\s*$", text, flags=re.M)
    for doc in docs:
        lines = doc.splitlines()
        for i, l in enumerate(lines):
            if re.match(r"^  components:\s*$", l):
                items = extract_list(lines, i)
                paths = [p for _, _, p in items if p]
                if [sort_key(p) for p in paths] != sorted(map(sort_key, paths)):
                    problems.append(f"{f}: components not path-alphabetical: {paths}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default="kubernetes/",
        help="Root directory to scan (default: kubernetes/)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the summary",
    )
    args = parser.parse_args()

    root = Path(args.path)
    problems: list[str] = []
    audited = 0

    files = sorted(root.rglob("kustomization.yaml")) + sorted(root.rglob("ks.yaml"))
    for f in files:
        text = f.read_text()
        lines = text.splitlines()
        audited += 1
        if f.name == "kustomization.yaml":
            audit_resources(f, lines, problems)
            audit_comment_groups(f, lines, problems)
        else:
            audit_flux(f, text, problems)
            audit_depends_on(f, text, problems)
            audit_components(f, text, problems)

    if not args.quiet:
        if problems:
            print("kustomization order violations:\n")
            for p in problems:
                print(p)
    print(f"\n{audited} files audited, {len(problems)} problems", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
