#!/usr/bin/env python
"""Audit Cilium CNP/CCNP selectors against the repo prefix guidelines.

Rules (AGENTS.md, "Networking & Policy (Cilium)" -> Selectors):
1. CNP endpointSelector: plain keys (namespace-bound).
2. CCNP endpointSelector: k8s:-prefixed pod-label keys (cluster-wide).
3. fromEndpoints/toEndpoints/fromRequires/toRequires:
   - selector containing k8s:io.kubernetes.pod.namespace (mixed / cross-ns):
      every other key MUST be k8s:-prefixed or io.cilium.k8s.namespace.labels.*
   - same-namespace selector: plain keys preferred (any: union, no false negatives)

Both `spec` and the multi-policy `specs` list are audited. Files that fail to
parse are reported and fail the audit (an unparseable file is unaudited).Usage:
    uv run scripts/cnp_prefix_audit.py [--path kubernetes/] [--quiet]
Exit code 0 = conformant, 1 = violations or parse errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from yaml.composer import ComposerError
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent
from yaml.events import MappingStartEvent
from yaml.events import ScalarEvent
from yaml.events import SequenceStartEvent

K8S_PREFIX = "k8s:"
NS_LABELS_PREFIX = "io.cilium.k8s.namespace.labels."
K8S_NS_KEY = "k8s:io.kubernetes.pod.namespace"
NEGATION_PREFIX = "!"
RULE_SELECTOR_FIELDS = ("fromEndpoints", "toEndpoints", "fromRequires", "toRequires")


class TolerantLoader(yaml.SafeLoader):
    """SafeLoader tolerating renderer-swallowed YAML quirks in repo manifests.

    - duplicate anchors (last one wins, like kustomize/Helm when re-anchoring)
    - the plain "=" scalar (resolves to tag:yaml.org,2002:value; used by
      alertmanagerconfig matchType), constructed as its raw string
    """

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            event = self.get_event()
            anchor = event.anchor
            if anchor not in self.anchors:
                raise ComposerError(
                    None, None, f"found undefined alias {anchor!r}", event.start_mark
                )
            return self.anchors[anchor]
        event = self.peek_event()
        anchor = event.anchor
        self.descend_resolver(parent, index)
        if self.check_event(ScalarEvent):
            node = self.compose_scalar_node(anchor)
        elif self.check_event(SequenceStartEvent):
            node = self.compose_sequence_node(anchor)
        elif self.check_event(MappingStartEvent):
            node = self.compose_mapping_node(anchor)
        else:
            raise ComposerError(
                None, None, "found unexpected event", event.start_mark
            )
        self.ascend_resolver()
        return node


def construct_value_tag(loader, node):
    if not isinstance(node, yaml.ScalarNode):
        raise ConstructorError(
            None, None, "expected a scalar for tag:yaml.org,2002:value", node.start_mark
        )
    return loader.construct_scalar(node)


TolerantLoader.add_constructor("tag:yaml.org,2002:value", construct_value_tag)


def selector_keys(sel: dict) -> list[str]:
    labels = sel.get("matchLabels") or {}
    exprs = sel.get("matchExpressions") or []
    return [str(k) for k in labels] + [
        str(e.get("key", "")) for e in exprs if isinstance(e, dict)
    ]


def is_prefixed(key: str) -> bool:
    bare = key.removeprefix(NEGATION_PREFIX)
    return bare.startswith(K8S_PREFIX) or bare.startswith(NS_LABELS_PREFIX)


def check_selector(
    where: str,
    sel: object,
    policy_kind: str,
    policy_name: str,
    path: Path,
    violations: list[str],
    plain_required: bool = False,
) -> None:
    if not isinstance(sel, dict):
        return
    keys = selector_keys(sel)
    cross_ns = K8S_NS_KEY in keys
    ns_label_key = any(k.startswith(NS_LABELS_PREFIX) for k in keys)
    for key in keys:
        if plain_required:
            if is_prefixed(key):
                violations.append(
                    f"{path}: {policy_kind}/{policy_name} {where}: PREFIXED '{key}' (should be plain)"
                )
        elif cross_ns or ns_label_key:
            if not is_prefixed(key):
                violations.append(
                    f"{path}: {policy_kind}/{policy_name} {where}: PLAIN '{key}' in mixed/namespace-label selector"
                )
        elif policy_kind == "CiliumClusterwideNetworkPolicy" and not is_prefixed(key):
            violations.append(
                f"{path}: CCNP/{policy_name} {where}: PLAIN '{key}' (cluster-wide policy)"
            )


def check_policy_spec(spec: dict, policy_kind: str, policy_name: str, path: Path, violations: list[str]) -> None:
    endpoint_selector = spec.get("endpointSelector")
    if endpoint_selector and policy_kind == "CiliumNetworkPolicy":
        check_selector(
            "endpointSelector",
            endpoint_selector,
            policy_kind,
            policy_name,
            path,
            violations,
            plain_required=True,
        )
    elif endpoint_selector:
        check_selector("endpointSelector", endpoint_selector, policy_kind, policy_name, path, violations)

    for direction in ("ingress", "egress"):
        for i, rule in enumerate(spec.get(direction) or []):
            if not isinstance(rule, dict):
                continue
            for sel_field in RULE_SELECTOR_FIELDS:
                for j, sel in enumerate(rule.get(sel_field) or []):
                    check_selector(f"{direction}[{i}].{sel_field}[{j}]", sel, policy_kind, policy_name, path, violations)


def iter_policy_specs(doc: dict) -> list[dict]:
    specs = []
    if isinstance(doc.get("spec"), dict):
        specs.append(doc["spec"])
    if isinstance(doc.get("specs"), list):
        specs.extend(s for s in doc["specs"] if isinstance(s, dict))
    return specs


def audit_file(path: Path) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    errors: list[str] = []
    try:
        with open(path) as f:
            docs = list(yaml.load_all(f, Loader=TolerantLoader))
    except yaml.YAMLError as exc:
        return violations, [f"{path}: unparseable YAML, not audited ({exc})"]
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "")
        if kind not in ("CiliumNetworkPolicy", "CiliumClusterwideNetworkPolicy"):
            continue
        name = (doc.get("metadata") or {}).get("name", "?")
        for spec in iter_policy_specs(doc):
            check_policy_spec(spec, kind, name, path, violations)
    return violations, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Cilium CNP/CCNP selectors against the repo prefix guidelines.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("kubernetes"),
        help="directory to scan recursively (default: %(default)s)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the success message")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    scan_root = args.path if args.path.is_absolute() else repo_root / args.path

    violations: list[str] = []
    errors: list[str] = []
    for path in sorted(scan_root.rglob("*.yaml")):
        file_violations, file_errors = audit_file(path)
        violations.extend(file_violations)
        errors.extend(file_errors)

    if violations:
        print(f"{len(violations)} violation(s):")
        for v in violations:
            print("  " + v)
    if errors:
        print(f"{len(errors)} file(s) could not be audited:")
        for e in errors:
            print("  " + e)
    if violations or errors:
        return 1
    if not args.quiet:
        print("All CNP/CCNP selectors conform to the prefix guidelines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
