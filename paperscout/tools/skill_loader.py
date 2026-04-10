from __future__ import annotations

import logging
import re
import os
from pathlib import Path

from . import register

logger = logging.getLogger("paperscout.skill_loader")

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _verbose() -> bool:
    return os.environ.get("PAPERSCOUT_VERBOSE", "") in ("1", "true", "yes")


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills_metadata: dict[str, dict] = {}   # Phase 1: 启动时只加载 metadata
        self.loaded_skills: dict[str, dict] = {}       # Phase 2: 按需加载完整 skill
        self.resource_cache: dict[str, str] = {}        # Phase 3: 懒加载资源
        self._load_metadata_only()

    def _load_metadata_only(self) -> None:
        """Phase 1: 启动时只解析 frontmatter，不读取 body"""
        import sys
        if not self.skills_dir.exists():
            return
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text(encoding="utf-8")
            meta, _ = self._parse_frontmatter(text)
            name = meta.get("name", f.parent.name)
            self.skills_metadata[name] = meta
        if _verbose():
            for name, meta in self.skills_metadata.items():
                print(f"[skill] phase1 metadata: {name} (summary={meta.get('summary', '')[:50]!r})", file=sys.stderr)

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        meta = {}
        for line in match.group(1).strip().splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip()
        return meta, match.group(2).strip()

    def get_summary(self, name: str) -> str:
        """Phase 1: 返回 skill 的简短 summary"""
        return self.skills_metadata.get(name, {}).get("summary", "")

    def get_resource(self, skill_name: str, resource_path: str) -> str:
        """Phase 3: 懒加载资源文件"""
        import sys
        cache_key = f"{skill_name}/{resource_path}"
        if cache_key not in self.resource_cache:
            path = self.skills_dir / skill_name / "resources" / f"{resource_path}.md"
            self.resource_cache[cache_key] = path.read_text(encoding="utf-8")
            if _verbose():
                print(f"[skill] phase3 resource loaded: {cache_key} ({len(self.resource_cache[cache_key])} chars)", file=sys.stderr)
        return self.resource_cache[cache_key]

    def _resolve_resource_placeholders(self, skill_name: str, body: str) -> str:
        """将 body 中的 {RESOURCE:path} 占位符替换为懒加载的资源内容"""
        def replacer(m: re.Match) -> str:
            resource_path = m.group(1)
            return self.get_resource(skill_name, resource_path)
        return re.sub(r"\{RESOURCE:([^}]+)\}", replacer, body)

    def get_content(self, name: str) -> str:
        """Phase 2: 按需加载完整 skill body（解析时替换资源占位符）"""
        import sys
        if name not in self.loaded_skills:
            skill_path = self.skills_dir / name / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            _, body = self._parse_frontmatter(text)
            body = self._resolve_resource_placeholders(name, body)
            self.loaded_skills[name] = {"body": body}
            if _verbose():
                print(f"[skill] phase2 loaded: {name} ({len(body)} chars, resources={len(self.resource_cache)})", file=sys.stderr)
        return self.loaded_skills[name]["body"]

    def get_descriptions(self) -> str:
        """Phase 1: 用 summary 构建工具 description"""
        if not self.skills_metadata:
            return "  (no skills available)"
        lines = []
        for name, meta in self.skills_metadata.items():
            summary = meta.get("summary", meta.get("description", "No description"))
            lines.append(f"  - {name}: {summary}")
        return "\n".join(lines)


_loader = SkillLoader(_SKILLS_DIR)


def _build_schema() -> dict:
    """动态构建 load_skill schema，description 使用 summary"""
    descriptions = _loader.get_descriptions()
    return {
        "name": "load_skill",
        "description": (
            "Load the full instructions for a named skill. "
            "Call this before performing a specialized task to get detailed guidance.\n\n"
            f"Available skills:\n{descriptions}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "The skill name to load.\n"
                        f"Available: {', '.join(_loader.skills_metadata.keys()) or 'none'}"
                    ),
                }
            },
            "required": ["name"],
        },
    }


_SCHEMA = _build_schema()


def _execute(tool_input: dict) -> str:
    return _loader.get_content(tool_input["name"])


register(_SCHEMA, _execute)
