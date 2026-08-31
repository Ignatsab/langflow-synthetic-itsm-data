import json
import sys
import uuid
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def main() -> None:
    source_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    code = source_path.read_text(encoding="utf-8")
    template, instance = build_custom_component_template(Component(_code=code))
    node_id = f"SyntheticDatasetGenerator-{uuid.uuid4()}"
    template["id"] = node_id
    template["type"] = "SyntheticDatasetGenerator"
    node = {
        "data": {
            "description": instance.description,
            "display_name": instance.display_name,
            "id": node_id,
            "node": template,
            "selected_output": "dataset",
            "type": "SyntheticDatasetGenerator",
        },
        "dragging": False,
        "id": node_id,
        "measured": {"height": 760, "width": 320},
        "position": {"x": 160, "y": 80},
        "positionAbsolute": {"x": 160, "y": 80},
        "selected": False,
        "type": "genericNode",
    }
    artifact = {
        "name": "Synthetic ITSM Dataset Generator",
        "description": "Portable schema-driven synthetic dataset generator for ServiceNow-style AI agent testing.",
        "icon": None,
        "icon_bg_color": None,
        "gradient": None,
        "data": {"nodes": [node], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}},
        "is_component": False,
        "webhook": False,
        "endpoint_name": None,
        "tags": ["synthetic-data", "servicenow", "testing"],
        "locked": False,
        "mcp_enabled": False,
        "access_type": "PRIVATE",
        "flow_type": "workflow",
    }
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
