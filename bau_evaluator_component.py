import json
from typing import Any

import pandas as pd

from lfx.custom import Component
from lfx.io import DataFrameInput, Output, StrInput
from lfx.schema import Data, DataFrame, Message


class BAUEvaluator(Component):
    display_name = "Know Your BAU Evaluator"
    description = "Compares BAU predictions with hidden synthetic ground truth and calculates evaluation metrics."
    icon = "ChartNoAxesCombined"
    name = "BAUEvaluator"

    inputs = [
        DataFrameInput(name="ground_truth", display_name="Hidden Ground Truth", required=True),
        DataFrameInput(name="predictions", display_name="BAU Predictions", required=True),
        StrInput(name="id_field", display_name="Ticket ID Field", value="number"),
        StrInput(
            name="target_fields",
            display_name="Fields to Score",
            value="category,ticket_type,required_skills,technology,support_level,assignment_group,agent_action",
        ),
        StrInput(
            name="breakdown_fields",
            display_name="Fields Preserved for Dashboard Breakdowns",
            value="_test_scenario,state,priority",
            info="Comma-separated ground-truth context fields copied into scored results but not used as prediction targets.",
        ),
    ]

    outputs = [
        Output(display_name="Scored Tickets", name="scored_tickets", method="build_scored_tickets"),
        Output(display_name="Evaluation Metrics", name="metrics", method="build_metrics"),
        Output(display_name="Evaluation Summary", name="summary", method="build_summary"),
    ]

    @staticmethod
    def _normalize(value: Any) -> Any:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    return BAUEvaluator._normalize(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
            return " ".join(stripped.casefold().split())
        if isinstance(value, (list, tuple, set)):
            normalized = [BAUEvaluator._normalize(item) for item in value]
            return sorted((item for item in normalized if item is not None), key=str)
        if isinstance(value, dict):
            return {key: BAUEvaluator._normalize(item) for key, item in sorted(value.items())}
        return value

    def _evaluate(self) -> tuple[pd.DataFrame, dict[str, Any]]:
        cached = getattr(self, "_evaluation_cache", None)
        if cached is not None:
            return cached
        truth = pd.DataFrame(self.ground_truth).copy()
        predicted = pd.DataFrame(self.predictions).copy()
        if truth.empty:
            raise ValueError("Hidden Ground Truth is empty.")
        if predicted.empty:
            raise ValueError("BAU Predictions is empty.")
        id_field = str(self.id_field or "number").strip()
        if id_field not in truth.columns or id_field not in predicted.columns:
            if "_evaluation_id" in truth.columns and "_evaluation_id" in predicted.columns:
                id_field = "_evaluation_id"
                self.id_field = id_field
            else:
                raise ValueError(f"Ticket ID field '{id_field}' must exist in ground truth and predictions.")

        predicted_by_id = {
            str(row[id_field]): row
            for row in predicted.to_dict(orient="records")
        }
        targets = [field.strip() for field in str(self.target_fields or "").split(",") if field.strip()]
        breakdowns = [field.strip() for field in str(self.breakdown_fields or "").split(",") if field.strip()]
        scored: list[dict[str, Any]] = []
        correct_counts = {field: 0 for field in targets}
        covered_counts = {field: 0 for field in targets}

        for truth_row in truth.to_dict(orient="records"):
            ticket_id = str(truth_row[id_field])
            prediction = predicted_by_id.get(ticket_id, {})
            row: dict[str, Any] = {id_field: truth_row[id_field], "prediction_received": bool(prediction)}
            for field in breakdowns:
                if field in truth_row:
                    row[field] = truth_row.get(field)
            all_correct = bool(prediction)
            for field in targets:
                expected_key = f"_expected_{field}"
                expected = truth_row.get(expected_key, truth_row.get(field))
                actual = prediction.get(field)
                covered = actual is not None and not (isinstance(actual, float) and pd.isna(actual))
                correct = covered and self._normalize(expected) == self._normalize(actual)
                row[f"expected_{field}"] = expected
                row[f"predicted_{field}"] = actual
                row[f"correct_{field}"] = correct
                covered_counts[field] += int(covered)
                correct_counts[field] += int(correct)
                all_correct = all_correct and correct
            row["all_fields_correct"] = all_correct
            scored.append(row)

        total = len(scored)
        metrics = {
            "ticket_count": total,
            "prediction_coverage": sum(int(row["prediction_received"]) for row in scored) / total,
            "overall_exact_match": sum(int(row["all_fields_correct"]) for row in scored) / total,
            "fields": {
                field: {
                    "accuracy": correct_counts[field] / total,
                    "coverage": covered_counts[field] / total,
                    "correct": correct_counts[field],
                    "total": total,
                }
                for field in targets
            },
        }
        self._evaluation_cache = (pd.DataFrame(scored), metrics)
        return self._evaluation_cache

    def build_scored_tickets(self) -> DataFrame:
        scored, _ = self._evaluate()
        return DataFrame(scored)

    def build_metrics(self) -> Data:
        _, metrics = self._evaluate()
        return Data(data=metrics)

    def build_summary(self) -> Message:
        _, metrics = self._evaluate()
        field_lines = ", ".join(
            f"{field}: {details['accuracy']:.1%}"
            for field, details in metrics["fields"].items()
        )
        return Message(
            text=(
                f"Know Your BAU evaluation: {metrics['ticket_count']} tickets, "
                f"{metrics['prediction_coverage']:.1%} prediction coverage, "
                f"{metrics['overall_exact_match']:.1%} all-fields exact match. "
                f"Per-field accuracy — {field_lines}."
            )
        )
