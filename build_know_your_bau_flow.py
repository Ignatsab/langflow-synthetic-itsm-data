import json
import sys
import uuid
from pathlib import Path
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def encoded_handle(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False).replace('"', "œ")


def build_node(source_path: str, component_type: str, x: int, y: int = 100) -> dict[str, Any]:
    code = Path(source_path).read_text(encoding="utf-8")
    template, instance = build_custom_component_template(Component(_code=code))
    node_id = f"{component_type}-{uuid.uuid4()}"
    template["id"] = node_id
    template["type"] = component_type
    return {
        "data": {
            "description": instance.description,
            "display_name": instance.display_name,
            "id": node_id,
            "node": template,
            "selected_output": template["outputs"][0]["name"],
            "type": component_type,
        },
        "dragging": False,
        "id": node_id,
        "measured": {"height": 760, "width": 320},
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "selected": False,
        "type": "genericNode",
    }


def build_edge(
    source: dict[str, Any],
    source_output: str,
    target: dict[str, Any],
    target_input: str,
) -> dict[str, Any]:
    source_id = source["id"]
    target_id = target["id"]
    source_type = source["data"]["type"]
    source_template = source["data"]["node"]
    target_template = target["data"]["node"]["template"]
    output = next(item for item in source_template["outputs"] if item["name"] == source_output)
    target_field = target_template[target_input]
    source_types = output.get("types") or output.get("output_types") or ["DataFrame"]
    input_types = target_field.get("input_types") or ["DataFrame", "Table"]
    source_handle = {
        "dataType": source_type,
        "id": source_id,
        "name": source_output,
        "output_types": source_types,
    }
    target_handle = {
        "fieldName": target_input,
        "id": target_id,
        "inputTypes": input_types,
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
    if len(sys.argv) != 7:
        raise SystemExit(
            "Usage: build_know_your_bau_flow.py GENERATOR SPLITTER AGENT EVALUATOR DASHBOARD OUTPUT"
        )
    generator = build_node(sys.argv[1], "SyntheticDatasetGenerator", 80, 1100)
    splitter = build_node(sys.argv[2], "HoldoutDatasetBuilder", 480, 0)
    agent = build_node(sys.argv[3], "KnowYourBAUAgent", 880, 0)
    evaluator = build_node(sys.argv[4], "BAUEvaluator", 1280, 1100)
    dashboard = build_node(sys.argv[5], "BAUEvaluationDashboard", 1680, 1100)
    edges = [
        build_edge(generator, "dataset", splitter, "dataset"),
        build_edge(splitter, "tickets", agent, "tickets"),
        build_edge(generator, "dataset", evaluator, "ground_truth"),
        build_edge(agent, "predictions", evaluator, "predictions"),
        build_edge(evaluator, "scored_tickets", dashboard, "scored_tickets"),
    ]
    artifact = {
        "name": "Know Your BAU - Synthetic Ticket Evaluation",
        "description": (
            "Generates ServiceNow-style tickets, creates a label-free holdout, classifies and routes tickets, "
            "then scores predictions against hidden ground truth."
        ),
        "icon": None,
        "icon_bg_color": None,
        "gradient": None,
        "data": {
            "nodes": [generator, splitter, agent, evaluator, dashboard],
            "edges": edges,
            "viewport": {"x": 0, "y": 0, "zoom": 0.58},
        },
        "is_component": False,
        "webhook": False,
        "endpoint_name": None,
        "tags": ["synthetic-data", "servicenow", "classification", "evaluation", "bau"],
        "locked": False,
        "mcp_enabled": False,
        "access_type": "PRIVATE",
        "flow_type": "workflow",
    }
    Path(sys.argv[6]).write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
