import json
import sys
import uuid
from pathlib import Path
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def encoded_handle(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False).replace('"', "œ")


def build_node(source: str, component_type: str, x: int, y: int, height: int = 420) -> dict[str, Any]:
    template, instance = build_custom_component_template(Component(_code=source))
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
        "measured": {"height": height, "width": 360},
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "selected": False,
        "type": "genericNode",
    }


def build_edge(source: dict[str, Any], source_output: str, target: dict[str, Any], target_input: str) -> dict[str, Any]:
    source_id, target_id = source["id"], target["id"]
    output = next(item for item in source["data"]["node"]["outputs"] if item["name"] == source_output)
    target_field = target["data"]["node"]["template"][target_input]
    source_handle = {
        "dataType": source["data"]["type"],
        "id": source_id,
        "name": source_output,
        "output_types": output.get("types") or output.get("output_types") or ["Message"],
    }
    target_handle = {
        "fieldName": target_input,
        "id": target_id,
        "inputTypes": target_field.get("input_types") or ["Message"],
        "type": target_field.get("type", "MessageTextInput"),
    }
    source_encoded, target_encoded = encoded_handle(source_handle), encoded_handle(target_handle)
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


def installed_component_source(module_name: str) -> str:
    module = __import__(module_name, fromlist=["__file__"])
    return Path(module.__file__).read_text(encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_chatbot_flow.py CHATBOT_COMPONENT OUTPUT_JSON")
    chatbot_source = Path(sys.argv[1]).read_text(encoding="utf-8")
    chat_input_source = installed_component_source("lfx.components.input_output.chat")
    chat_output_source = installed_component_source("lfx.components.input_output.chat_output")

    chat_input = build_node(chat_input_source, "ChatInput", 80, 140, 360)
    chatbot = build_node(chatbot_source, "IncidentResolutionChatbot", 520, 0, 900)
    chat_output = build_node(chat_output_source, "ChatOutput", 960, 140, 360)
    edges = [
        build_edge(chat_input, "message", chatbot, "message"),
        build_edge(chatbot, "answer", chat_output, "input_value"),
    ]
    artifact = {
        "name": "L1 L2 Incident Resolution Chatbot",
        "description": "Conversational RAG assistant grounded in prior incident resolutions, KB files, and optional Confluence search.",
        "icon": None,
        "icon_bg_color": None,
        "gradient": None,
        "data": {"nodes": [chat_input, chatbot, chat_output], "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.75}},
        "is_component": False,
        "webhook": False,
        "endpoint_name": None,
        "tags": ["servicenow", "support", "l1", "l2", "chatbot", "rag", "confluence"],
        "locked": False,
        "mcp_enabled": False,
        "access_type": "PRIVATE",
        "flow_type": "workflow",
    }
    Path(sys.argv[2]).write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
