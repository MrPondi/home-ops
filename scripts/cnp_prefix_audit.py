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

LIMITATIONS:
(a) Fail-closed namespace inference relies on `apps/<ns>/` path layout; custom
    --path layouts that do not contain an `apps` segment silently skip
    duplicated-inherited-rule checks (inferred namespace is None).
(b) Scope-trap warnings (Check 3, warnings-only) are narrowed: only a CNP
    (not CCNP) fromEndpoints/toEndpoints/fromRequires/toRequires selector that
    contains >=1 `k8s:`-prefixed pod-label key but neither
    `k8s:io.kubernetes.pod.namespace` nor any
    `io.cilium.k8s.namespace.labels.*` key warns — a prefixed-without-
    namespace selector is still clamped to its own namespace and is genuinely
    suspicious (redundant prefix or missing namespace key). Plain-only
    selectors are the correct same-namespace convention and stay silent;
    selectors with `io.cilium.k8s.namespace.labels.*` are valid cross-namespace
    groupings and never warn. Current-tree baseline is ~0 warnings. Warnings
    never affect exit code. Skips: endpointSelector, empty selectors, CCNPs.
""" 

from __future__ import annotations

import argparse
import re
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
# All rule keys that can appear as "- <key>:" entries in ingress/egress lists
ALL_RULE_KEYS = (
    "fromEndpoints",
    "toEndpoints",
    "fromRequires",
    "toRequires",
    "toCIDRSet",
    "toCIDR",
    "toEntities",
    "toFQDNs",
    "fromEntities",
    "fromCIDR",
    "fromCIDRSet",
    "fromGroups",
    "fromNodes",
    "icmps",
    "toGroups",
    "toNodes",
    "toPorts",
    "toServices",
)
# For comment check we use same set
COMMENT_RULE_KEYS = ALL_RULE_KEYS


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


# ---------------------------------------------------------------------------
# Fail-closed namespace derivation
# ---------------------------------------------------------------------------

def derive_fail_closed_namespaces(repo_root: Path) -> set[str]:
    """Scan kubernetes/apps/*/namespace.yaml for CNP default-deny."""
    apps_dir = repo_root / "kubernetes" / "apps"
    result: set[str] = set()
    if not apps_dir.is_dir():
        return result
    for ns_dir in apps_dir.iterdir():
        if not ns_dir.is_dir():
            continue
        ns_yaml = ns_dir / "namespace.yaml"
        if not ns_yaml.is_file():
            continue
        try:
            with open(ns_yaml) as f:
                docs = list(yaml.load_all(f, Loader=TolerantLoader))
        except yaml.YAMLError:
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if doc.get("kind") != "CiliumNetworkPolicy":
                continue
            if (doc.get("metadata") or {}).get("name") != "default-deny":
                continue
            result.add(ns_dir.name)
            break
    return result


def infer_namespace_for_path(path: Path, scan_root: Path, repo_root: Path) -> str | None:
    """Infer the K8s namespace for a file via its path."""
    parts = path.parts
    # Primary: look for "apps" segment
    for i, part in enumerate(parts):
        if part == "apps" and i + 1 < len(parts):
            return parts[i + 1]
    # Fallback: relative to scan_root, first directory component
    try:
        rel = path.relative_to(scan_root)
        if len(rel.parts) >= 2:
            return rel.parts[0]
        # If file is directly under a namespace-like dir under scan_root
        # e.g. scan_root=/tmp/testdir and path=/tmp/testdir/ai/policy.yaml
        # rel.parts[0] == "ai"
        if len(rel.parts) >= 1:
            # If the parent directory name might be the namespace but file is at top level,
            # we can't be sure; check if scan_root name itself is not relevant
            # For single-component relative path, we don't infer
            return None
    except ValueError:
        pass
    # Additional fallback: check if parent dir name is a known fail-closed candidate
    # Use immediate parent directory name as namespace hint
    # This helps when scanning /tmp/testdir where files are directly inside a ns-named dir
    try:
        rel = path.relative_to(scan_root)
        if len(rel.parts) >= 1:
            # If path is /tmp/testdir/ai/networkpolicy.yaml, rel.parts[0] is ai
            # already handled above with len>=2, but for /tmp/testdir/networkpolicy.yaml we have len==1 -> no ns
            pass
    except ValueError:
        pass
    return None


def is_under_components(path: Path, repo_root: Path) -> bool:
    """Check if path is under kubernetes/components/."""
    try:
        # Resolve both to absolute for comparison
        repo_components = (repo_root / "kubernetes" / "components").resolve()
        path_resolved = path.resolve()
        # Use relative_to check
        path_resolved.relative_to(repo_components)
        return True
    except (ValueError, FileNotFoundError, RuntimeError):
        pass
    # Fallback: check parts for "components" after "kubernetes"
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "kubernetes" and i + 1 < len(parts) and parts[i + 1] == "components":
            return True
        if part == "components":
            # Also handle paths like /tmp/testdir/components/... not repo, but treat as components-like
            # Only treat as under components if the original repo's components dir pattern
            # For /tmp tests, "components" standalone should also be considered components
            # to correctly test exclusion? The brief says NOT files under kubernetes/components/
            # So only if path contains "kubernetes/components" we exclude, plain "components" outside that not needed
            pass
    return False


# ---------------------------------------------------------------------------
# Check 1: missing rule comments (raw-text scan)
# ---------------------------------------------------------------------------

_COMMENT_RULE_PATTERN = re.compile(
    r"^\s*-\s+(" + "|".join(map(re.escape, COMMENT_RULE_KEYS)) + r")\s*:"
)


def check_missing_rule_comments(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        # If unreadable, let the YAML parser report it as error; don't double-count
        return []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = _COMMENT_RULE_PATTERN.match(line)
        if not m:
            continue
        key = m.group(1)
        # Walk up past blank lines
        j = idx - 1
        while j >= 0 and lines[j].strip() == "":
            j -= 1
        if j < 0:
            violations.append(f"{path}: missing comment for rule '{key}' at line {idx+1}")
            continue
        prev = lines[j]
        if prev.lstrip().startswith("#"):
            continue
        violations.append(f"{path}: missing comment for rule '{key}' at line {idx+1}")
    return violations


# ---------------------------------------------------------------------------
# Check 2: duplicated inherited rules helpers
# ---------------------------------------------------------------------------

def _is_dns_duplicate_rule(rule: dict) -> bool:
    eps = rule.get("toEndpoints")
    if not isinstance(eps, list) or len(eps) != 1:
        return False
    sel = eps[0]
    if not isinstance(sel, dict):
        return False
    labels = sel.get("matchLabels") or {}
    if not isinstance(labels, dict):
        return False
    expected = {"k8s:io.kubernetes.pod.namespace": "kube-system", "k8s:k8s-app": "kube-dns"}
    if labels != expected:
        return False
    if sel.get("matchExpressions"):
        return False
    to_ports = rule.get("toPorts")
    if not isinstance(to_ports, list):
        return False
    port_set: set[tuple[str, str]] = set()
    has_dns = False
    for tp in to_ports:
        if not isinstance(tp, dict):
            continue
        ports = tp.get("ports") or []
        for p in ports:
            if not isinstance(p, dict):
                continue
            port_val = str(p.get("port", ""))
            proto = str(p.get("protocol", ""))
            port_set.add((port_val, proto))
        rules = tp.get("rules") or {}
        if isinstance(rules, dict):
            dns = rules.get("dns")
            if isinstance(dns, list):
                for d in dns:
                    if isinstance(d, dict) and "matchPattern" in d:
                        has_dns = True
            elif isinstance(dns, dict):
                if "matchPattern" in dns:
                    has_dns = True
            # Some charts use matchPattern at top level of dns entry as string?
        # also check if rules directly contains dns with matchPattern as key
    if ("53", "UDP") not in port_set or ("53", "TCP") not in port_set:
        return False
    if not has_dns:
        return False
    return True


def _is_kube_api_duplicate_rule(rule: dict) -> bool:
    entities = rule.get("toEntities")
    if not isinstance(entities, list):
        return False
    entity_set = set(str(e) for e in entities)
    if entity_set != {"host", "remote-node"}:
        return False
    to_ports = rule.get("toPorts")
    if not isinstance(to_ports, list) or not to_ports:
        return False
    ports_collected: list[tuple[str, str]] = []
    for tp in to_ports:
        if not isinstance(tp, dict):
            continue
        ports = tp.get("ports") or []
        for p in ports:
            if not isinstance(p, dict):
                continue
            port_val = str(p.get("port", ""))
            proto = str(p.get("protocol", ""))
            ports_collected.append((port_val, proto))
    if len(ports_collected) != 1:
        return False
    if ports_collected[0] != ("6443", "TCP"):
        return False
    return True


def _is_prometheus_duplicate_rule(rule: dict) -> bool:
    from_eps = rule.get("fromEndpoints")
    if not isinstance(from_eps, list) or len(from_eps) != 1:
        return False
    sel = from_eps[0]
    if not isinstance(sel, dict):
        return False
    labels = sel.get("matchLabels") or {}
    if not isinstance(labels, dict):
        return False
    expected = {"k8s:io.kubernetes.pod.namespace": "observability", "k8s:app.kubernetes.io/name": "prometheus"}
    if labels != expected:
        return False
    if sel.get("matchExpressions"):
        return False
    # Must have no toPorts (egress-direction rules toward prometheus must NOT match — check direction separately)
    tp = rule.get("toPorts")
    if tp:
        if isinstance(tp, list) and len(tp) > 0:
            # Has explicit ports -> not the namespace-wide scrape allow (which is all ports)
            return False
        # If tp is truthy but not list, also considered having ports
        if tp:
            return False
    # Also check if rule has empty list explicitly? That's falsy, so falls through to violation
    return True


def check_duplicated_inherited(
    spec: dict,
    policy_kind: str,
    policy_name: str,
    path: Path,
    violations: list[str],
    direction: str,
    idx: int,
    rule: dict,
) -> None:
    # Caller ensures this is only invoked for per-app CNPs in fail-closed namespaces
    if direction == "egress":
        if _is_dns_duplicate_rule(rule):
            violations.append(
                f"{path}: {policy_kind}/{policy_name} egress[{idx}] duplicates inherited DNS rule (kube-dns :53 + matchPattern)"
            )
        if _is_kube_api_duplicate_rule(rule):
            violations.append(
                f"{path}: {policy_kind}/{policy_name} egress[{idx}] duplicates inherited kube-API rule (host+remote-node :6443/TCP)"
            )
    elif direction == "ingress":
        if _is_prometheus_duplicate_rule(rule):
            violations.append(
                f"{path}: {policy_kind}/{policy_name} ingress[{idx}] duplicates inherited prometheus scrape rule (observability/prometheus, no toPorts)"
            )


# ---------------------------------------------------------------------------
# Core spec checking (prefix + scope-trap + duplicated)
# ---------------------------------------------------------------------------

def check_policy_spec(
    spec: dict,
    policy_kind: str,
    policy_name: str,
    path: Path,
    violations: list[str],
    warnings: list[str],
    fail_closed_namespaces: set[str],
    inferred_ns: str | None,
    is_under_components: bool,
    is_default_deny: bool,
) -> None:
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

    # Determine if this policy qualifies for duplicated-inherited checks (Check 2)
    qualifies_for_dup_check = (
        policy_kind == "CiliumNetworkPolicy"
        and not is_default_deny
        and not is_under_components
        and inferred_ns is not None
        and inferred_ns in fail_closed_namespaces
    )

    for direction in ("ingress", "egress"):
        for i, rule in enumerate(spec.get(direction) or []):
            if not isinstance(rule, dict):
                continue
            # Check 2: duplicated inherited rules (only for qualifying per-app CNPs)
            if qualifies_for_dup_check:
                check_duplicated_inherited(spec, policy_kind, policy_name, path, violations, direction, i, rule)

            # Iterate full rule dict (Check 4) — visit all rule keys so future checks see toCIDRSet etc.
            # Check 3 and prefix checks only apply to selector fields, but we explicitly walk all keys
            for rule_key in ALL_RULE_KEYS:
                if rule_key not in rule:
                    continue
                if rule_key in RULE_SELECTOR_FIELDS:
                    for j, sel in enumerate(rule.get(rule_key) or []):
                        # Existing prefix validation
                        check_selector(f"{direction}[{i}].{rule_key}[{j}]", sel, policy_kind, policy_name, path, violations)
                        # Check 3: scope-trap warnings (CNP only, not CCNP, not endpointSelector, not empty)
                        # Narrowed: warn only when selector contains >=1 k8s:-prefixed key
                        # but neither k8s:io.kubernetes.pod.namespace nor io.cilium.k8s.namespace.labels.*
                        if policy_kind == "CiliumNetworkPolicy":
                            if not isinstance(sel, dict):
                                continue
                            keys = selector_keys(sel)
                            if not keys:
                                continue
                            has_ns = K8S_NS_KEY in keys or f"{NEGATION_PREFIX}{K8S_NS_KEY}" in keys
                            has_ns_label = any(
                                k.startswith(NS_LABELS_PREFIX) or k.startswith(f"{NEGATION_PREFIX}{NS_LABELS_PREFIX}")
                                for k in keys
                            )
                            has_k8s_prefixed = any(
                                k.removeprefix(NEGATION_PREFIX).startswith(K8S_PREFIX) for k in keys
                            )
                            if has_k8s_prefixed and not has_ns and not has_ns_label:
                                warnings.append(
                                    f"{path}: {policy_kind}/{policy_name} {direction}[{i}].{rule_key}[{j}] scope-trap: k8s:-prefixed selector without k8s:io.kubernetes.pod.namespace or io.cilium.k8s.namespace.labels.* (still namespace-clamped, keys={keys})"
                                )
                else:
                    # Non-selector rule keys (toCIDRSet, toEntities, etc.) — no selector validation,
                    # but walker visits them for future checks (Check 4 / Check 1 covers comment presence via raw scan)
                    pass


def iter_policy_specs(doc: dict) -> list[dict]:
    specs = []
    if isinstance(doc.get("spec"), dict):
        specs.append(doc["spec"])
    if isinstance(doc.get("specs"), list):
        specs.extend(s for s in doc["specs"] if isinstance(s, dict))
    return specs


def audit_file(
    path: Path,
    fail_closed_namespaces: set[str],
    scan_root: Path,
    repo_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Return (violations, warnings, errors) for a file."""
    violations: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    # Check 1: raw-text scan for missing rule comments (per file)
    violations.extend(check_missing_rule_comments(path))

    try:
        with open(path) as f:
            docs = list(yaml.load_all(f, Loader=TolerantLoader))
    except yaml.YAMLError as exc:
        return violations, warnings, [f"{path}: unparseable YAML, not audited ({exc})"]
    inferred_ns = infer_namespace_for_path(path, scan_root, repo_root)
    under_components = is_under_components(path, repo_root)
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "")
        if kind not in ("CiliumNetworkPolicy", "CiliumClusterwideNetworkPolicy"):
            continue
        name = (doc.get("metadata") or {}).get("name", "?")
        is_default_deny = kind == "CiliumNetworkPolicy" and name == "default-deny"
        for spec in iter_policy_specs(doc):
            check_policy_spec(spec, kind, name, path, violations, warnings, fail_closed_namespaces, inferred_ns, under_components, is_default_deny)
    return violations, warnings, errors


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

    fail_closed_namespaces = derive_fail_closed_namespaces(repo_root)

    violations: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    for path in sorted(scan_root.rglob("*.yaml")):
        file_violations, file_warnings, file_errors = audit_file(path, fail_closed_namespaces, scan_root, repo_root)
        violations.extend(file_violations)
        warnings.extend(file_warnings)
        errors.extend(file_errors)

    if violations:
        print(f"{len(violations)} violation(s):")
        for v in violations:
            print("  " + v)
    if errors:
        print(f"{len(errors)} file(s) could not be audited:")
        for e in errors:
            print("  " + e)
    if warnings:
        print(f"{len(warnings)} warning(s):")
        for w in warnings:
            print("  " + w)
    if violations or errors:
        return 1
    if not args.quiet and not warnings:
        print("All CNP/CCNP selectors conform to the prefix guidelines.")
    elif not args.quiet and warnings:
        # Still success, but mention warnings
        print("All CNP/CCNP selectors conform to the prefix guidelines (warnings present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
