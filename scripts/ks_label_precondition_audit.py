#!/usr/bin/env python
"""Audit Kustomization label preconditions against the root registry.

Registry-driven: derives from the root ``kubernetes/flux/cluster/ks.yaml``
``spec.patches`` which ``labelSelector`` pairs with a JSON6902 ``add`` to
``/spec/components``. The registry currently has 2 strategic-merge labelSelector entries (cnpg=init, non-cluster) plus 3 JSON6902 append entries (plus 1 unqualified defaults entry); strategic-merge labels need NO precondition.

Rules:
  A. If a KS (``kubernetes/apps/**/ks.yaml``) matches a selector that needs
     ``spec.components`` (JSON6902 append), it must carry ``spec.components``
     as a list (empty ``[]`` allowed).
  B. If a KS carries any label starting ``components.`` that matches NO root
     selector key, it is an undefined label (typo or removed machinery).

Scope is per-consumer (option 2): only KSs that ADOPT a components-appending
label need ``spec.components``.

Usage:
    uv run scripts/ks_label_precondition_audit.py [--path kubernetes/] [--quiet]
Exit code 0 = conformant, 1 = violations or parse errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def parse_registry(root_ks: Path) -> tuple[list[tuple[str, bool]], set[str], list[str]]:
    """Parse root ks.yaml patches for labelSelector registry.

    Returns (selectors, selector_keys, errors) where selectors is list of
    (selector_string, needs_components).
    """
    errors: list[str] = []
    selectors: list[tuple[str, bool]] = []
    try:
        text = root_ks.read_text()
    except FileNotFoundError:
        return selectors, set(), [f"{root_ks}: not found"]
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return selectors, set(), [f"{root_ks}: unparseable YAML ({exc})"]
    if not isinstance(doc, dict):
        return selectors, set(), [f"{root_ks}: no document"]
    patches = (doc.get("spec") or {}).get("patches") or []
    if not isinstance(patches, list):
        return selectors, set(), [f"{root_ks}: spec.patches not a list"]
    for entry in patches:
        if not isinstance(entry, dict):
            continue
        target = entry.get("target") or {}
        selector = target.get("labelSelector")
        if not selector:
            continue
        # selector may be string like "components.postgres/cnpg=init"
        selector_str = str(selector).strip()
        if not selector_str:
            continue
        patch_text = entry.get("patch") or ""
        # Detect JSON6902 append to /spec/components by YAML-parsing the patch
        # body. needs=True only if some list operation is a dict with
        # op=="add" and path startswith "/spec/components" (valid paths are
        # exactly "/spec/components" or "/spec/components/-").
        # Strategic-merge mapping bodies (dict) evaluate False.
        needs = False
        if isinstance(patch_text, str) and patch_text.strip():
            try:
                parsed = yaml.safe_load(patch_text)
            except yaml.YAMLError as exc:
                errors.append(f"{root_ks}: unparseable YAML, not audited ({exc})")
                parsed = None
            if isinstance(parsed, list):
                for op in parsed:
                    if not isinstance(op, dict):
                        continue
                    if op.get("op") != "add":
                        continue
                    op_path = op.get("path")
                    if isinstance(op_path, str) and op_path in ("/spec/components", "/spec/components/-"):
                        needs = True
                        break
        selectors.append((selector_str, needs))
    selector_keys = {s.split("=", 1)[0] for s, _ in selectors}
    return selectors, selector_keys, errors


def audit_file(
    path: Path,
    selectors: list[tuple[str, bool]],
    selector_keys: set[str],
    selector_keys_by_value: dict[str, str],
) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    errors: list[str] = []
    try:
        with open(path) as f:
            docs = list(yaml.safe_load_all(f))
    except yaml.YAMLError as exc:
        return violations, [f"{path}: unparseable YAML, not audited ({exc})"]
    for idx, doc in enumerate(docs):
        if not isinstance(doc, dict):
            continue
        # Only Flux Kustomization docs (but also allow any doc with metadata.labels)
        metadata = doc.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        labels = metadata.get("labels") or {}
        if not isinstance(labels, dict):
            labels = {}
        # Filter to KS docs that have labels; skip docs without labels for rule checks
        # Still need name for reporting
        name = metadata.get("name", f"doc#{idx+1}")
        # Normalize labels to str->str
        str_labels = {str(k): str(v) for k, v in labels.items()}

        # Rule B: any components.* label key not in registry
        for key, value in str_labels.items():
            if key.startswith("components."):
                if key not in selector_keys:
                    violations.append(
                        f"{path}: Kustomization/{name} has undefined label '{key}={value}' "
                        f"(no matching root selector; typo or removed machinery)"
                    )

        # Rule A: if matches a selector that needs components
        for selector, needs in selectors:
            if not needs:
                continue
            # selector match: exact key=value
            if "=" in selector:
                k, v = selector.split("=", 1)
                if str_labels.get(k) == v:
                    spec = doc.get("spec") or {}
                    if not isinstance(spec, dict):
                        spec = {}
                    components = spec.get("components")
                    if not isinstance(components, list):
                        violations.append(
                            f"{path}: Kustomization/{name} label '{selector}' requires spec.components as a list "
                            f"(empty [] allowed) — JSON6902 append will fail without it"
                        )
            else:
                # selector without value — match key presence (defensive)
                if selector in str_labels:
                    spec = doc.get("spec") or {}
                    if not isinstance(spec, dict):
                        spec = {}
                    components = spec.get("components")
                    if not isinstance(components, list):
                        violations.append(
                            f"{path}: Kustomization/{name} label '{selector}' requires spec.components as a list "
                            f"(empty [] allowed) — JSON6902 append will fail without it"
                        )
    return violations, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("kubernetes"),
        help="Root directory to scan (default: %(default)s)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the success message")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    scan_root = args.path if args.path.is_absolute() else repo_root / args.path

    root_ks = scan_root / "flux/cluster/ks.yaml"
    selectors, selector_keys, registry_errors = parse_registry(root_ks)

    violations: list[str] = []
    errors: list[str] = []
    errors.extend(registry_errors)

    # Find consumer ks.yaml files: kubernetes/apps/**/ks.yaml
    # Use rglob but filter to apps/
    ks_files: list[Path] = []
    if scan_root.exists():
        # Prefer apps/**/ks.yaml pattern
        apps_root = scan_root / "apps"
        if apps_root.exists():
            ks_files = sorted(apps_root.rglob("ks.yaml"))
        else:
            # Fallback: any ks.yaml under scan_root that is under an "apps" parent
            ks_files = sorted(p for p in scan_root.rglob("ks.yaml") if "apps" in p.parts)
    else:
        errors.append(f"{scan_root}: scan root does not exist")

    audited = 0
    for path in ks_files:
        audited += 1
        file_violations, file_errors = audit_file(path, selectors, selector_keys, {})
        violations.extend(file_violations)
        errors.extend(file_errors)

    if violations:
        print(f"{len(violations)} violation(s):")
        for v in violations:
            print("  " + v)
    if errors:
        print(f"{len(errors)} error(s):")
        for e in errors:
            print("  " + e)
    if violations or errors:
        print(f"\n{audited} ks.yaml files audited, {len(violations)} violations, {len(errors)} errors", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"All {audited} ks.yaml files satisfy label preconditions ({len(selectors)} registry selectors).")
    else:
        print(f"{audited} ks.yaml files audited, 0 violations", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
