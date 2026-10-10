#!/usr/bin/env python
"""Render per-tool agent adapters from the tool-agnostic `.agents/` sources.

Sources (edit these):
    .agents/config.yaml                       default agent, MCP servers, MCP tool denies,
                                              protected paths
    .agents/agents/<role>.md                  role definitions (neutral frontmatter + prompt)
    .agents/skills/<name>/SKILL.md            skills (Agent Skills format, shared as-is)
    .agents/adapters/opencode.base.json       opencode-only settings (lsp, ...)
    .agents/adapters/claude.settings.base.json  Claude Code-only settings (permissions, ...)

Generated (never edit by hand):
    Claude Code: .mcp.json, .claude/settings.json, .claude/agents/<role>.md,
                 .claude/skills/<name> -> ../../.agents/skills/<name> (symlinks)
    opencode:    .opencode/opencode.json, .opencode/agent/<role>.md
                 (skills are read directly from .agents/skills/)

Role frontmatter (neutral):
    name, description          required
    mode: primary|subagent     primary = selectable main agent, subagent = delegated lane
    access: read|write         read = no file edits
    bash: true|false           shell access
    mcp: all|none|[server...]  MCP tool access (a list allows only those servers)
    mcpDeny: {server: [glob]}  extra MCP tool denies when mcp: all
    models: {claude: ..., opencode: ...}  per-tool model (claude: haiku|sonnet|opus|inherit)

Adding another tool = add a `render_<tool>()` returning {path: content} and register it
in RENDERERS; adding a role/skill/server = edit `.agents/` and re-run.

Generated text is passed through oxfmt (repo .oxfmtrc.json) when available so the
pre-commit formatter never fights the generator.

Usage:
    uv run scripts/sync_agents.py           # write adapters
    uv run scripts/sync_agents.py --check   # exit 1 if adapters are stale
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".agents"
MARKER = "<!-- Generated from .agents/agents/{name}.md by scripts/sync_agents.py — edit the source, not this file. -->"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_roles() -> list[dict]:
    roles = []
    for path in sorted((AGENTS_DIR / "agents").glob("*.md")):
        match = FRONTMATTER.match(path.read_text())
        if not match:
            sys.exit(f"{path}: missing YAML frontmatter")
        meta = yaml.safe_load(match.group(1)) or {}
        for key in ("name", "description", "mode", "models"):
            if key not in meta:
                sys.exit(f"{path}: frontmatter lacks `{key}`")
        if meta["name"] != path.stem:
            sys.exit(f"{path}: name `{meta['name']}` must match the file name")
        meta.setdefault("access", "read")
        meta.setdefault("bash", True)
        meta.setdefault("mcp", "none")
        meta.setdefault("mcpDeny", {})
        meta["body"] = match.group(2).strip() + "\n"
        roles.append(meta)
    return roles


def load_skills() -> list[str]:
    return sorted(p.parent.name for p in (AGENTS_DIR / "skills").glob("*/SKILL.md"))


def enabled_servers(config: dict) -> dict:
    return {k: v for k, v in config.get("mcpServers", {}).items() if v.get("enabled", True)}


def denied_servers(config: dict, role: dict) -> list[str]:
    """Servers a role may not use when `mcp` is an allow-list."""
    if not isinstance(role["mcp"], list):
        return []
    unknown = set(role["mcp"]) - set(config.get("mcpServers", {}))
    if unknown:
        sys.exit(f"role {role['name']}: unknown MCP servers {sorted(unknown)}")
    return [s for s in enabled_servers(config) if s not in role["mcp"]]


def frontmatter(meta: dict) -> str:
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n"


def to_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- Claude Code -------------------------------------------------------------


def render_claude(config: dict, roles: list[dict], skills: list[str]) -> tuple[dict, dict]:
    files: dict[str, str] = {}

    servers = {}
    for name, srv in enabled_servers(config).items():
        if "url" in srv:
            entry = {"type": "http", "url": srv["url"]}
            if srv.get("headers"):
                entry["headers"] = srv["headers"]  # ${VAR} is native .mcp.json syntax
        else:
            entry = {"type": "stdio", "command": srv["command"], "args": srv.get("args", [])}
        servers[name] = entry
    files[".mcp.json"] = to_json({"mcpServers": servers})

    settings = json.loads((AGENTS_DIR / "adapters" / "claude.settings.base.json").read_text())
    perms = settings.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    deny += [f"Read(./{p})" for p in config.get("protectedPaths", [])]
    for server, globs in config.get("mcpToolDeny", {}).items():
        deny += [f"mcp__{server}__{g}" for g in globs]
    settings["agent"] = config["defaultAgent"]
    settings["enabledMcpjsonServers"] = list(servers)
    files[".claude/settings.json"] = to_json(settings)

    for role in roles:
        disallowed = []
        if role["access"] == "read":
            disallowed += ["Edit", "Write", "NotebookEdit"]
        if not role["bash"]:
            disallowed.append("Bash")
        if role["mcp"] == "none":
            disallowed.append("mcp__*")
        else:
            disallowed += [f"mcp__{s}" for s in denied_servers(config, role)]
            for server, globs in role["mcpDeny"].items():
                disallowed += [f"mcp__{server}__{g}" for g in globs]
        meta = {"name": role["name"], "description": role["description"]}
        meta["model"] = role["models"].get("claude", "inherit")
        if disallowed:
            meta["disallowedTools"] = ", ".join(disallowed)
        files[f".claude/agents/{role['name']}.md"] = (
            frontmatter(meta) + "\n" + MARKER.format(name=role["name"]) + "\n\n" + role["body"]
        )

    links = {f".claude/skills/{s}": f"../../.agents/skills/{s}" for s in skills}
    return files, links


# --- opencode ----------------------------------------------------------------


def render_opencode(config: dict, roles: list[dict], skills: list[str]) -> tuple[dict, dict]:
    files: dict[str, str] = {}

    base = json.loads((AGENTS_DIR / "adapters" / "opencode.base.json").read_text())
    out = {"$schema": base.pop("$schema", "https://opencode.ai/config.json")}
    out["default_agent"] = config["defaultAgent"]
    tool_deny = {
        f"{server}_{g}": False for server, globs in config.get("mcpToolDeny", {}).items() for g in globs
    }
    if tool_deny:
        out["tools"] = tool_deny
    mcp = {}
    for name, srv in config.get("mcpServers", {}).items():
        enabled = srv.get("enabled", True)
        if "url" in srv:
            entry = {"type": "remote", "url": srv["url"], "enabled": enabled}
            if srv.get("headers"):
                entry["headers"] = {
                    k: ENV_REF.sub(r"{env:\1}", v) for k, v in srv["headers"].items()
                }
            if srv.get("oauth"):
                entry["oauth"] = {}
        else:
            entry = {
                "type": "local",
                "command": [srv["command"], *srv.get("args", [])],
                "enabled": enabled,
            }
        mcp[name] = entry
    out["mcp"] = mcp
    out.update(base)
    files[".opencode/opencode.json"] = to_json(out)

    for role in roles:
        tools: dict[str, bool] = {}
        if role["access"] == "read":
            tools["write"] = False
            tools["edit"] = False
        if not role["bash"]:
            tools["bash"] = False
        if role["mcp"] == "none":
            tools.update({f"{s}_*": False for s in enabled_servers(config)})
        else:
            tools.update({f"{s}_*": False for s in denied_servers(config, role)})
            for server, globs in role["mcpDeny"].items():
                tools.update({f"{server}_{g}": False for g in globs})
        meta = {
            "description": role["description"],
            "mode": role["mode"],
            "model": role["models"]["opencode"],
        }
        if tools:
            meta["tools"] = tools
        files[f".opencode/agent/{role['name']}.md"] = (
            frontmatter(meta) + "\n" + MARKER.format(name=role["name"]) + "\n\n" + role["body"]
        )
    return files, {}


RENDERERS = (render_claude, render_opencode)
# Directories whose generated *.md files are pruned when the source role disappears.
GENERATED_DIRS = (".claude/agents", ".opencode/agent")
SKILL_LINK_DIRS = (".claude/skills",)


def oxfmt(path: str, content: str) -> str:
    exe = shutil.which("oxfmt")
    if not exe:
        return content
    res = subprocess.run(
        [exe, f"--stdin-filepath={path}"],
        input=content,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return res.stdout if res.returncode == 0 and res.stdout else content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if adapters are stale")
    args = parser.parse_args()

    config = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())
    roles = load_roles()
    skills = load_skills()
    if config["defaultAgent"] not in {r["name"] for r in roles}:
        sys.exit(f"defaultAgent `{config['defaultAgent']}` has no .agents/agents/ role")

    files: dict[str, str] = {}
    links: dict[str, str] = {}
    for render in RENDERERS:
        f, l = render(config, roles, skills)
        files.update(f)
        links.update(l)
    files = {p: oxfmt(p, c) for p, c in files.items()}

    stale: list[str] = []
    for rel, content in files.items():
        path = ROOT / rel
        if not path.is_file() or path.read_text() != content:
            stale.append(rel)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    for rel, target in links.items():
        path = ROOT / rel
        if not (path.is_symlink() and os.readlink(path) == target):
            stale.append(rel)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
                path.symlink_to(target)
    for d in GENERATED_DIRS:
        for path in (ROOT / d).glob("*.md"):
            rel = str(path.relative_to(ROOT))
            if rel not in files and "scripts/sync_agents.py" in path.read_text():
                stale.append(f"{rel} (orphan)")
                if not args.check:
                    path.unlink()
    for d in SKILL_LINK_DIRS:
        for path in (ROOT / d).glob("*"):
            rel = str(path.relative_to(ROOT))
            if path.is_symlink() and rel not in links:
                stale.append(f"{rel} (orphan)")
                if not args.check:
                    path.unlink()

    if args.check:
        if stale:
            print("agent adapters are stale — run `just agents-sync`:")
            print("\n".join(f"  {s}" for s in stale))
            return 1
        print("agent adapters are up to date")
        return 0
    print("\n".join(f"updated {s}" for s in stale) if stale else "agent adapters are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
