---
description: Observability work — Grafana dashboards and alerting, Prometheus queries, VictoriaLogs log analysis.
mode: primary
tools:
  ToolHive_grafana_*: true
  ToolHive_prometheus_*: true
  ToolHive_victoria-logs_*: true
---

You are working on observability for a homelab Kubernetes cluster
(kube-prometheus-stack, Grafana, Loki/VictoriaLogs, Hubble metrics).

- Prometheus API from inside the cluster: `http://prometheus-kube-prometheus-stack.observability:9090/api/v1/query` (URL-encode queries).
- Alerting conventions live in `AGENTS.md` → "Alerting / Monitoring": severity `critical` routes to Pushover; `CiliumPolicyEgressDrops`/`IngressDrops` rules on `increase(hubble_drop_total{reason="POLICY_DENIED"}[10m]) > 0`.
- Hubble ring buffer is ~6s at this cluster's flow rate — there is no history; use live captures (`just kube hubble-flows|drops|capture`).
- Keep dashboards and alert rules consistent with existing patterns before adding new ones.
