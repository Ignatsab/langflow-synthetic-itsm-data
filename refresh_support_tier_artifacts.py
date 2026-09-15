from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def assignment_value(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            value = node.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            return ast.literal_eval(value)
    raise KeyError(f"Assignment {name!r} not found in {path}")


def named_input_default(path: Path, input_name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        name_node = keywords.get("name")
        if isinstance(name_node, ast.Constant) and name_node.value == input_name and "value" in keywords:
            return ast.literal_eval(keywords["value"])
    raise KeyError(f"Input {input_name!r} not found in {path}")


def approach_prompts() -> dict[str, str]:
    approaches = assignment_value(ROOT / "build_support_tier_experiments.py", "APPROACHES")
    return {key: value["instructions"] for key, value in approaches.items()}


def sync_node(node: dict[str, Any], prompts: dict[str, str], flow_name: str) -> None:
    node_type = node.get("data", {}).get("type")
    template = node.get("data", {}).get("node", {}).get("template", {})
    if node_type == "SyntheticDatasetGenerator":
        source = ROOT / "synthetic_dataset_generator_component.py"
        template["code"]["value"] = source.read_text(encoding="utf-8")
        template["field_definitions"]["value"] = json.dumps(
            assignment_value(source, "DEFAULT_INCIDENT_FIELDS"), indent=2
        )
        template["test_goal"]["value"] = assignment_value(source, "SERVICENOW_GOALS")["Incident"]
        template["dataset_context"]["value"] = assignment_value(source, "SERVICENOW_CONTEXTS")["Incident"]
        template["scenario_guidance"]["value"] = assignment_value(source, "SERVICENOW_SCENARIOS")["Incident"]
    elif node_type == "KnowYourBAUAgent":
        source = ROOT / "know_your_bau_agent_component.py"
        template["code"]["value"] = source.read_text(encoding="utf-8")
        template["prediction_fields"]["value"] = json.dumps(
            assignment_value(source, "DEFAULT_PREDICTION_FIELDS"), indent=2
        )
        template["classification_instructions"]["value"] = named_input_default(
            source, "classification_instructions"
        )
    elif node_type == "BAUEvaluator":
        template["code"]["value"] = (ROOT / "bau_evaluator_component.py").read_text(encoding="utf-8")
        outputs = node["data"]["node"]["outputs"]
        if not any(output.get("name") == "resolution_decisions" for output in outputs):
            outputs.insert(
                1,
                {
                    "types": ["Table"],
                    "selected": "Table",
                    "name": "resolution_decisions",
                    "display_name": "Resolution Decisions",
                    "method": "build_resolution_decisions",
                    "value": "__UNDEFINED__",
                    "cache": True,
                    "allows_loop": False,
                    "group_outputs": False,
                    "tool_mode": True,
                },
            )
    elif node_type == "BatchRunComponent":
        title = node.get("data", {}).get("display_name", "").casefold()
        if "model comparison" in flow_name.casefold() or "identical rubric" in title:
            key = "rubric"
        elif "zero-shot" in title:
            key = "zero_shot"
        elif "few-shot" in title:
            key = "few_shot"
        else:
            key = "rubric"
        template["system_message"]["value"] = prompts[key]


def main() -> None:
    prompts = approach_prompts()
    artifacts = [
        ROOT / "servicenow_synthetic_dataset_generator.json",
        ROOT / "know_your_bau_flow.json",
        *sorted(ROOT.glob("servicenow_support_tier_*_flow.json")),
    ]
    for path in dict.fromkeys(artifacts):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for node in payload.get("data", {}).get("nodes", []):
            sync_node(node, prompts, payload.get("name", ""))
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"refreshed {path.name}")


if __name__ == "__main__":
    main()
