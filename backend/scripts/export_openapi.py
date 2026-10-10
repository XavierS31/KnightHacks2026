import argparse
import json
from pathlib import Path

from backend.app.main import app

TARGET = Path(__file__).resolve().parents[2] / "shared" / "openapi.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != output:
            raise SystemExit("OpenAPI drift: run python -m backend.scripts.export_openapi")
        print("OpenAPI matches canonical backend schemas.")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(output, encoding="utf-8")
        print(f"Exported {TARGET}")


if __name__ == "__main__":
    main()
