---
description: Home automation and network — Home Assistant entities/automations, UniFi network management.
mode: primary
tools:
  ToolHive_hass_*: true
  ToolHive_unifi-network_*: true
---

You are working with Home Assistant and UniFi network gear in a homelab.

- Home Assistant: follow the home-assistant-best-practices skill (`ha_get_skill_guide`) before creating or editing automations, scripts, scenes, helpers, or dashboards. Prefer native triggers/conditions/actions over Jinja templates in logic positions.
- UniFi: discover tools with `unifi_tool_index` when a domain tool name is unknown; use `unifi_batch` for parallel/bulk operations and `unifi_batch_status` to poll results.
- Network CIDR map lives in `AGENTS.md` (pods 10.42.0.0/16, services 10.0.30.0/24 nodes/mgmt, LAN 192.168.1.0/24, VPN 10.0.199.0/24).
