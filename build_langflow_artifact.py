import json
import sys
import uuid
from pathlib import Path
from typing import Any

from lfx.components.files_and_knowledge.save_file import SaveToFileComponent
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def encoded_handle(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False).replace('"', "œ")


def build_edge(source: dict[str, Any], source_output: str, target: dict[str, Any], target_input: str) -> dict[str, Any]:
    source_id = source["id"]
    target_id = target["id"]
    source_template = source["data"]["node"]
    target_template = target["data"]["node"]["template"]
    output = next(item for item in source_template["outputs"] if item["name"] == source_output)
    target_field = target_template[target_input]
    source_handle = {
        "dataType": source["data"]["type"],
        "id": source_id,
        "name": source_output,
        "output_types": output.get("types") or output.get("output_types") or ["DataFrame"],
    }
    target_handle = {
        "fieldName": target_input,
        "id": target_id,
        "inputTypes": target_field.get("input_types") or ["DataFrame", "Table"],
        "type": target_field.get("type", "DataFrame"),
    }
    source_encoded = encoded_handle(source_handle)
    target_encoded = encoded_handle(target_handle)
    return {
        "animated": False,
        "className": "",
        "data": {"sourceHandle": source_handle, "targetHandle": target_handle},
        "id": f"reactflow__edge-{source_id}{source_encoded}-{target_id}{target_encoded}",
        "selected": False,
        "source": source_id,
        "sourceHandle": source_encoded,
        "target": target_id,
        "targetHandle": target_encoded,
    }


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
    writer_component = SaveToFileComponent()
    writer_frontend = writer_component.to_frontend_node()
    writer_id = f"SaveToFile-{uuid.uuid4()}"
    writer_template = writer_frontend["data"]["node"]
    writer_template["id"] = writer_id
    writer_template["type"] = "SaveToFile"
    writer_template["template"]["file_name"]["value"] = "synthetic_dataset"
    writer_template["template"]["local_format"]["value"] = "json"
    writer = {
        "data": {
            "description": writer_component.description,
            "display_name": writer_component.display_name,
            "id": writer_id,
            "node": writer_template,
            "selected_output": "message",
            "type": "SaveToFile",
        },
        "dragging": False,
        "id": writer_id,
        "measured": {"height": 420, "width": 320},
        "position": {"x": 600, "y": 80},
        "positionAbsolute": {"x": 600, "y": 80},
        "selected": False,
        "type": "genericNode",
    }
    edge = build_edge(node, "dataset", writer, "input")
    artifact = {
        "name": "Synthetic ITSM Dataset Generator",
        "description": "Synthetic dataset generator with built-in ServiceNow Incident, Change Request, and Service Request schemas.",
        "icon": None,
        "icon_bg_color": None,
        "gradient": None,
        "data": {"nodes": [node, writer], "edges": [edge], "viewport": {"x": 0, "y": 0, "zoom": 0.85}},
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
