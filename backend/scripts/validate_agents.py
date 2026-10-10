"""Check repository custom agents/skills structurally without invoking any agents."""
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    agents = list((ROOT / ".codex" / "agents").glob("*.toml"))
    skills = list((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    if len(agents) < 3 or len(skills) < 3:
        raise SystemExit("Expected three developer agents and at least three project skills.")
    for agent in agents:
        config = tomllib.loads(agent.read_text(encoding="utf-8"))
        for key in ["name", "description", "developer_instructions"]:
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise SystemExit(f"{agent.name}: required {key} missing")
        if "model" in config:
            raise SystemExit(f"{agent.name}: model must inherit the user's selection")
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            raise SystemExit(f"{skill}: invalid YAML frontmatter")
        metadata = yaml.safe_load(parts[1])
        name = metadata.get("name", "")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or name != skill.parent.name:
            raise SystemExit(f"{skill}: invalid name")
        if not metadata.get("description") or not parts[2].strip():
            raise SystemExit(f"{skill}: missing description/instructions")
    print(f"Validated {len(agents)} Codex agent definitions and {len(skills)} repo skills.")


if __name__ == "__main__":
    main()
