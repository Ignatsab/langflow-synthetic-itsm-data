import asyncio
import json
import sys
from pathlib import Path

import pandas as pd

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def load_component(path: str):
    code = Path(path).read_text(encoding="utf-8")
    _, instance = build_custom_component_template(Component(_code=code))
    return instance


def main() -> None:
    splitter = load_component(sys.argv[1])
    agent = load_component(sys.argv[2])
    evaluator = load_component(sys.argv[3])
    dashboard = load_component(sys.argv[4])

    truth = pd.DataFrame(
        [
            {
                "number": "INC0000001",
                "short_description": "VPN disconnects",
                "description": "Remote employee loses VPN every five minutes.",
                "category": "Network",
                "assignment_group": "Network Support",
                "_test_scenario": "common",
                "_expected_category": "Network",
                "_expected_ticket_type": "incident",
                "_expected_required_skills": ["VPN", "network troubleshooting"],
                "_expected_technology": "VPN",
                "_expected_support_level": "L2",
                "_expected_assignment_group": "Network Support",
                "_expected_agent_action": "Diagnose VPN session stability",
            },
            {
                "number": "INC0000002",
                "short_description": "Account locked",
                "description": "User cannot sign in after failed attempts.",
                "category": "Access",
                "assignment_group": "Service Desk",
                "_test_scenario": "edge",
                "_expected_category": "Access",
                "_expected_ticket_type": "incident",
                "_expected_required_skills": ["identity management"],
                "_expected_technology": "Directory services",
                "_expected_support_level": "L1",
                "_expected_assignment_group": "Service Desk",
                "_expected_agent_action": "Verify identity and unlock account",
            },
        ]
    )

    splitter.dataset = truth
    splitter.sample_size = 2
    splitter.id_field = "number"
    splitter.fields_to_hide = "category,assignment_group"
    splitter.random_sample = False
    splitter.random_seed = 42
    visible, hidden_truth, hidden_fields = splitter._split()
    assert len(visible) == 2
    assert "category" not in visible.columns
    assert "assignment_group" not in visible.columns
    assert not any(column.startswith("_expected_") for column in visible.columns)
    assert "_expected_support_level" in hidden_truth.columns
    assert "category" in hidden_fields

    agent.tickets = visible
    agent.dry_run = True
    agent.id_field = "number"
    agent.tickets_per_call = 10
    dry_result = asyncio.run(agent._result())
    assert dry_result["dry_run"] is True
    assert len(dry_result["predictions"]) == 2

    predictions = pd.DataFrame(
        [
            {
                "number": row["number"],
                "category": row["_expected_category"],
                "ticket_type": row["_expected_ticket_type"],
                "required_skills": row["_expected_required_skills"],
                "technology": row["_expected_technology"],
                "support_level": row["_expected_support_level"],
                "assignment_group": row["_expected_assignment_group"],
                "agent_action": row["_expected_agent_action"],
            }
            for row in truth.to_dict(orient="records")
        ]
    )
    unused_truth = hidden_truth.iloc[[0]].copy()
    unused_truth["number"] = "INC9999999"
    evaluator.ground_truth = pd.concat([hidden_truth, unused_truth], ignore_index=True)
    evaluator.predictions = predictions
    evaluator.id_field = "number"
    evaluator.target_fields = "category,ticket_type,required_skills,technology,support_level,assignment_group,agent_action"
    evaluator.breakdown_fields = "_test_scenario,state,priority"
    scored, metrics = evaluator._evaluate()
    assert len(scored) == 2
    assert metrics["prediction_coverage"] == 1.0
    assert metrics["overall_exact_match"] == 1.0
    assert all(details["accuracy"] == 1.0 for details in metrics["fields"].values())
    assert "_test_scenario" in scored.columns

    dashboard.scored_tickets = scored
    dashboard.scenario_field = "_test_scenario"
    dashboard.confusion_field = "assignment_group"
    dashboard.failure_limit = 20
    dashboard_result = dashboard._analyze()
    assert len(dashboard_result["field_performance"]) == 7
    assert len(dashboard_result["scenario_performance"]) == 2
    assert dashboard_result["overall"] == 1.0
    assert dashboard_result["failures"].empty
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
