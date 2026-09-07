#!/usr/bin/env python
"""Audit Cilium CNP/CCNP selectors against the repo prefix guidelines.

Rules (AGENTS.md, "Networking & Policy (Cilium)" -> Selectors):
1. CNP endpointSelector: plain keys (namespace-bound).
2. CCNP endpointSelector: k8s:-prefixed pod-label keys (cluster-wide).
3. fromEndpoints/toEndpoints:
   - selector containing k8s:io.kubernetes.pod.namespace (mixed / cross-ns):
     every other key MUST be k8s:-prefixed or io.cilium.k8s.namespace.labels.*
   - same-namespace selector: plain keys preferred (any: union, no false negatives)

Usage (repo .venv, needs pyyaml):
    .venv/bin/python scripts/cnp_prefix_audit.py
Exit code 0 = conformant, 1 = violations found.
"""
import glob
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIOLATIONS = []


def check_selector(where, sel, policy_kind, policy_name, path):
    if not isinstance(sel, dict):
        return
    labels = sel.get("matchLabels") or {}
    exprs = sel.get("matchExpressions") or []
    keys = list(labels.keys()) + [e.get("key", "") for e in exprs if isinstance(e, dict)]
    cross_ns = "k8s:io.kubernetes.pod.namespace" in labels
    ns_label_key = any(k.startswith("io.cilium.k8s.namespace.labels.") for k in keys)
    for k in keys:
        prefixed = k.startswith("k8s:") or k.startswith("io.cilium.k8s.namespace.labels.")
        if cross_ns or ns_label_key:
            if not prefixed:
                VIOLATIONS.append(f"{path}: {policy_kind}/{policy_name} {where}: PLAIN '{k}' in mixed/namespace-label selector")
        elif policy_kind == "CiliumClusterwideNetworkPolicy":
            if not prefixed:
                VIOLATIONS.append(f"{path}: CCNP/{policy_name} {where}: PLAIN '{k}' (cluster-wide policy)")


for path in sorted(glob.glob(os.path.join(REPO_ROOT, "kubernetes", "**", "*.yaml"), recursive=True)):
    with open(path) as f:
        try:
            docs = list(yaml.safe_load_all(f))
        except yaml.YAMLError:
            continue
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "")
        if kind not in ("CiliumNetworkPolicy", "CiliumClusterwideNetworkPolicy"):
            continue
        name = (doc.get("metadata") or {}).get("name", "?")
        spec = doc.get("spec") or {}

        es = spec.get("endpointSelector")
        if es and kind == "CiliumNetworkPolicy":
            for k in (list((es.get("matchLabels") or {}).keys())
                      + [e.get("key", "") for e in es.get("matchExpressions") or [] if isinstance(e, dict)]):
                if k.startswith("k8s:") or k.startswith("io.cilium.k8s.namespace.labels."):
                    VIOLATIONS.append(f"{path}: CNP/{name} endpointSelector: PREFIXED '{k}' (should be plain)")
        elif es:
            check_selector("endpointSelector", es, kind, name, path)

        for direction in ("ingress", "egress"):
            for i, rule in enumerate(spec.get(direction) or []):
                for sel_field in ("fromEndpoints", "toEndpoints"):
                    for j, sel in enumerate(rule.get(sel_field) or []):
                        check_selector(f"{direction}[{i}].{sel_field}[{j}]", sel, kind, name, path)

if VIOLATIONS:
    print(f"{len(VIOLATIONS)} violation(s):")
    for v in VIOLATIONS:
        print("  " + v)
    sys.exit(1)
print("All CNP/CCNP selectors conform to the prefix guidelines.")
