#!/usr/bin/env python3
"""Emit a JSON map of {gradle_module_path: [plugin_ids]} for a Gradle project.

Resolves aliases via gradle/libs.versions.toml, recognises:
  - id("foo.bar.baz")
  - id "foo.bar.baz"
  - kotlin("multiplatform")  → org.jetbrains.kotlin.multiplatform
  - alias(libs.plugins.foo)  → resolved via libs.versions.toml [plugins]
  - apply(plugin = "foo.bar.baz")

Usage:
    python3 analyze_plugins.py <project-root>

Output (stdout, JSON):
    {
      "<gradle-path>": ["plugin.id.1", "plugin.id.2"],
      ...
    }

Module gradle paths are derived from settings.gradle.kts include(...) lines.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


PLUGIN_ID_RE = re.compile(r'''id\s*[("\s]+([a-zA-Z][\w.\-]+)["\s)]''')
APPLY_PLUGIN_RE = re.compile(r'''apply\s*\(\s*plugin\s*=\s*"([^"]+)"''')
KOTLIN_SHORTCUT_RE = re.compile(r'''kotlin\s*\(\s*"([^"]+)"\s*\)''')
ALIAS_RE = re.compile(r'''alias\s*\(\s*libs\.plugins\.([\w.]+)\s*\)''')


def _camel_path(dot_path: str) -> str:
    """Normalize libs.plugins access like 'androidKmpLibrary' or 'android.kmp.library'.

    The libs.versions.toml [plugins] section uses dashes/dots in keys; build files
    access them in either form. We canonicalise to lowercase dot-separated.
    """
    # Convert camelCase → kebab-case style
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", dot_path).lower()
    # Then normalise dashes/dots to single token
    return s.replace("-", "").replace(".", "")


def load_plugin_aliases(project_root: Path) -> dict[str, str]:
    """Map alias name → plugin id from gradle/libs.versions.toml [plugins]."""
    catalog = project_root / "gradle" / "libs.versions.toml"
    if not catalog.exists():
        return {}
    try:
        with catalog.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}

    plugins = data.get("plugins", {})
    out: dict[str, str] = {}
    for alias, spec in plugins.items():
        plugin_id = ""
        if isinstance(spec, str):
            # "com.foo:bar:1.0" form → take first segment
            plugin_id = spec.split(":")[0]
        elif isinstance(spec, dict):
            plugin_id = spec.get("id", "")
        if plugin_id:
            # Store under both raw alias and normalized form
            out[alias] = plugin_id
            out[_camel_path(alias)] = plugin_id
    return out


def parse_module_plugins(build_file: Path, aliases: dict[str, str]) -> set[str]:
    """Extract plugin IDs applied by a single build.gradle.kts (or .gradle)."""
    try:
        text = build_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    # Strip line/block comments to avoid false positives
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)

    plugin_ids: set[str] = set()

    for m in PLUGIN_ID_RE.finditer(text):
        plugin_ids.add(m.group(1))

    for m in APPLY_PLUGIN_RE.finditer(text):
        plugin_ids.add(m.group(1))

    for m in KOTLIN_SHORTCUT_RE.finditer(text):
        # kotlin("multiplatform") → org.jetbrains.kotlin.multiplatform
        plugin_ids.add(f"org.jetbrains.kotlin.{m.group(1)}")

    for m in ALIAS_RE.finditer(text):
        alias = m.group(1)
        # Resolve via aliases table; try both the raw form and a normalised lookup
        plugin_id = aliases.get(alias) or aliases.get(_camel_path(alias))
        if plugin_id:
            plugin_ids.add(plugin_id)

    return plugin_ids


def discover_modules(project_root: Path) -> dict[str, Path]:
    """Map gradle module path (e.g. ':sharedLogic:data') → filesystem dir.

    Reads settings.gradle.kts include(...) entries; falls back to any build.gradle.kts
    we can find if settings is unparseable.
    """
    settings = project_root / "settings.gradle.kts"
    if not settings.exists():
        settings = project_root / "settings.gradle"
    modules: dict[str, Path] = {":": project_root}

    if settings.exists():
        text = settings.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
        for m in re.finditer(r'"(:[\w:\-]+)"', text):
            gradle_path = m.group(1)
            rel = gradle_path.lstrip(":").replace(":", "/")
            fs = project_root / rel
            if (fs / "build.gradle.kts").exists() or (fs / "build.gradle").exists():
                modules[gradle_path] = fs

    if len(modules) == 1:  # settings empty or unparseable
        for build_file in project_root.rglob("build.gradle.kts"):
            if "build/" in str(build_file) or ".gradle/" in str(build_file):
                continue
            rel_path = build_file.parent.relative_to(project_root)
            gradle_path = ":" + str(rel_path).replace("/", ":") if str(rel_path) != "." else ":"
            modules[gradle_path] = build_file.parent

    return modules


def find_module(plugins_by_module: dict[str, list[str]], kind: str) -> str:
    """Return the first gradle module path matching `kind`, or empty string.

    kind:
      'android-app' — applies com.android.application and NOT kotlin.multiplatform
      'desktop-app' — JVM-targeted Compose app (jvm + compose, no android/kmp app),
                      or any module whose path contains 'desktop'/'jvmApp'
      'web-app'     — module whose path contains 'web', 'wasm', or 'jsApp'
    """
    KMP = "org.jetbrains.kotlin.multiplatform"
    APP = "com.android.application"
    JVM = "org.jetbrains.kotlin.jvm"
    COMPOSE = "org.jetbrains.compose"

    candidates: list[str] = []
    for module, plugins in plugins_by_module.items():
        if module == ":":
            continue
        if kind == "android-app":
            if APP in plugins and KMP not in plugins:
                candidates.append(module)
        elif kind == "desktop-app":
            lower = module.lower()
            is_path_match = any(tok in lower for tok in ("desktop", "jvmapp"))
            is_compose_jvm = JVM in plugins and COMPOSE in plugins and APP not in plugins
            if is_path_match or is_compose_jvm:
                candidates.append(module)
        elif kind == "web-app":
            lower = module.lower()
            if any(tok in lower for tok in ("web", "wasm", "jsapp")):
                candidates.append(module)

    # Prefer shortest path (most likely the actual "app" module, not a nested helper)
    candidates.sort(key=lambda m: (m.count(":"), len(m)))
    return candidates[0] if candidates else ""


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: analyze_plugins.py <project-root> [--find android-app|desktop-app|web-app]",
              file=sys.stderr)
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    if not project_root.is_dir():
        print(f"Not a directory: {project_root}", file=sys.stderr)
        sys.exit(1)

    aliases = load_plugin_aliases(project_root)
    modules = discover_modules(project_root)

    result: dict[str, list[str]] = {}
    for gradle_path, fs_dir in modules.items():
        build_file = fs_dir / "build.gradle.kts"
        if not build_file.exists():
            build_file = fs_dir / "build.gradle"
        if not build_file.exists():
            continue
        result[gradle_path] = sorted(parse_module_plugins(build_file, aliases))

    if len(sys.argv) >= 4 and sys.argv[2] == "--find":
        kind = sys.argv[3]
        print(find_module(result, kind))
        return

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
