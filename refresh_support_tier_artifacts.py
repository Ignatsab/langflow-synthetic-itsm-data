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


def harden_batch_node(node: dict[str, Any]) -> None:
    frontend = node["data"]["node"]
    template = frontend["template"]
    code = template["code"]["value"]
    if "name=\"max_concurrency\"" not in code:
        code = code.replace("    DropdownInput,\n", "    DropdownInput,\n    IntInput,\n", 1)
        code = code.replace(
            "        BoolInput(\n            name=\"enable_metadata\",",
            "        IntInput(\n"
            "            name=\"max_concurrency\",\n"
            "            display_name=\"Max Concurrent Requests\",\n"
            "            info=\"Limits simultaneous model calls so larger tables do not overload the endpoint.\",\n"
            "            value=2,\n"
            "            advanced=True,\n"
            "        ),\n"
            "        BoolInput(\n            name=\"enable_metadata\",",
            1,
        )
        code = code.replace(
            "await model.abatch(list(conversations))",
            "await model.with_retry(stop_after_attempt=3).abatch(\n"
            "                        list(conversations),\n"
            "                        config={\"max_concurrency\": min(max(int(self.max_concurrency), 1), 32)},\n"
            "                    )",
            1,
        )
        template["code"]["value"] = code
    template.setdefault(
        "max_concurrency",
        {
            "_input_type": "IntInput",
            "advanced": True,
            "display_name": "Max Concurrent Requests",
            "dynamic": False,
            "info": "Limits simultaneous model calls so larger tables do not overload the endpoint.",
            "input_types": [],
            "list": False,
            "list_add_label": "Add More",
            "load_from_db": False,
            "name": "max_concurrency",
            "override_skip": False,
            "placeholder": "",
            "required": False,
            "show": True,
            "title_case": False,
            "tool_mode": False,
            "trace_as_metadata": True,
            "track_in_telemetry": True,
            "type": "int",
            "value": 2,
        },
    )
    if "max_concurrency" not in frontend.get("field_order", []):
        frontend.setdefault("field_order", []).append("max_concurrency")


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
        harden_batch_node(node)
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
