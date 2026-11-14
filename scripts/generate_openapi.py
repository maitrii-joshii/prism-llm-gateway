"""Generate OpenAPI schema files (JSON and YAML) for Prism LLM Gateway."""

import json
from pathlib import Path

# Set dummy environment variables to allow clean import
import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-schema")
os.environ.setdefault("GROQ_API_KEY", "dummy-key-for-schema")

from prism.main import app

def main() -> None:
    schema = app.openapi()
    
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = docs_dir / "openapi.json"
    json_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Generated: {json_path}")

    # Generate basic YAML representation
    try:
        import yaml
        yaml_path = docs_dir / "openapi.yaml"
        yaml_path.write_text(yaml.dump(schema, sort_keys=False), encoding="utf-8")
        print(f"Generated: {yaml_path}")
    except ImportError:
        # Fallback to json if pyyaml not installed
        pass

if __name__ == "__main__":
    main()

