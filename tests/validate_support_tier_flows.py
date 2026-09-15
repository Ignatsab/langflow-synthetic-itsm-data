import json
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLOW_FILES = [
    ROOT / "servicenow_support_tier_comparison_flow.json",
    ROOT / "servicenow_support_tier_model_comparison_flow.json",
    ROOT / "servicenow_support_tier_zero_shot_flow.json",
    ROOT / "servicenow_support_tier_rubric_flow.json",
    ROOT / "servicenow_support_tier_few_shot_flow.json",
]


def validate_flow(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = payload["data"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    node_ids = {node["id"] for node in nodes}
    assert len(node_ids) == len(nodes)
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in edges)
    dependencies = {node_id: set() for node_id in node_ids}
    for edge in edges:
        dependencies[edge["target"]].add(edge["source"])
    pending = set(node_ids)
    while pending:
        ready = {node_id for node_id in pending if not (dependencies[node_id] & pending)}
        assert ready, "flow graph contains a cycle"
        pending -= ready

    types = [node["data"]["type"] for node in nodes]
    expected_branches = 3 if "comparison" in path.name else 1
    assert types.count("SyntheticDatasetGenerator") == 1
    assert types.count("HoldoutDatasetBuilder") == 1
    assert types.count("BatchRunComponent") == expected_branches
    assert types.count("BAUEvaluator") == expected_branches
    assert types.count("BAUEvaluationDashboard") == expected_branches

    batch_nodes = [node for node in nodes if node["data"]["type"] == "BatchRunComponent"]
    for node in batch_nodes:
        template = node["data"]["node"]["template"]
        instructions = template["system_message"]["value"]
        assert "L1" in instructions and "lowest" in instructions
        assert "L3" in instructions and "highest" in instructions
        assert "STOP_WITH_SOLUTION" in instructions
        assert "L3_AUTO_RESOLUTION=false" in instructions
        assert template["column_name"]["value"] == ""
        assert template["output_column_name"]["value"] == "model_response"
        assert template["max_concurrency"]["value"] == 1
        assert template["reuse_checkpoint"]["value"] is True
        assert template["checkpoint_name"]["value"].endswith("_predictions.json")
        code = template["code"]["value"]
        ast.parse(code)
        assert 'config={"max_concurrency"' in code
        assert "with_retry(stop_after_attempt=3)" in code
        assert "input_fingerprint =" in code
        assert "Reusing predictions checkpoint" in code

    holdout = next(node for node in nodes if node["data"]["type"] == "HoldoutDatasetBuilder")
    visible_fields = holdout["data"]["node"]["template"]["visible_fields"]["value"]
    assert "_expected_support_level" not in visible_fields

    evaluators = [node for node in nodes if node["data"]["type"] == "BAUEvaluator"]
    for node in evaluators:
        template = node["data"]["node"]["template"]
        assert template["target_fields"]["value"] == "support_level"
        assert template["response_column"]["value"] == "model_response"
        output_names = {output["name"] for output in node["data"]["node"]["outputs"]}
        assert "resolution_decisions" in output_names

    generator = next(node for node in nodes if node["data"]["type"] == "SyntheticDatasetGenerator")
    generator_template = generator["data"]["node"]["template"]
    assert generator_template["reuse_checkpoint"]["value"] is True
    generator_code = generator_template["code"]["value"]
    assert "input_signature" in generator_code
    assert "Save after every successful chunk" in generator_code

    if "comparison" in path.name:
        assert types.count("SaveToFile") == 8
        assert types.count("ExperimentRunCollector") == 1
        run_after_edges = [
            edge for edge in edges if edge["data"]["targetHandle"]["fieldName"] == "run_after"
        ]
        assert len(run_after_edges) == 2
        collector = next(node for node in nodes if node["data"]["type"] == "ExperimentRunCollector")
        collector_edges = [edge for edge in edges if edge["target"] == collector["id"]]
        assert len(collector_edges) == 11


def main() -> None:
    for flow_file in FLOW_FILES:
        validate_flow(flow_file)
        print(f"validated {flow_file.name}")


if __name__ == "__main__":
    main()
