from typing import Any

import pandas as pd

from lfx.custom import Component
from lfx.io import DataFrameInput, IntInput, Output, StrInput
from lfx.schema import DataFrame, Message
from lfx.schema.properties import Properties


class BAUEvaluationDashboard(Component):
    display_name = "Know Your BAU Evaluation Dashboard"
    description = "Turns scored BAU tickets into visual Markdown, performance tables, confusion data, and failure analysis."
    icon = "ChartColumnBig"
    name = "BAUEvaluationDashboard"

    inputs = [
        DataFrameInput(name="scored_tickets", display_name="Scored Tickets", required=True),
        StrInput(name="scenario_field", display_name="Scenario Breakdown Field", value="_test_scenario"),
        StrInput(name="confusion_field", display_name="Confusion Matrix Field", value="assignment_group"),
        IntInput(name="failure_limit", display_name="Maximum Failures to Show", value=20, advanced=True),
    ]

    outputs = [
        Output(display_name="Dashboard", name="dashboard", method="build_dashboard"),
        Output(display_name="Field Performance", name="field_performance", method="build_field_performance"),
        Output(display_name="Scenario Performance", name="scenario_performance", method="build_scenario_performance"),
        Output(display_name="Confusion Matrix Data", name="confusion_matrix", method="build_confusion_matrix"),
        Output(display_name="Failed Tickets", name="failed_tickets", method="build_failed_tickets"),
    ]

    @staticmethod
    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, float) and pd.isna(value):
            return False
        return True

    @staticmethod
    def _bar(value: float, width: int = 12) -> str:
        filled = min(max(round(value * width), 0), width)
        return "█" * filled + "░" * (width - filled)

    def _analyze(self) -> dict[str, Any]:
        cached = getattr(self, "_dashboard_cache", None)
        if cached is not None:
            return cached
        frame = pd.DataFrame(self.scored_tickets).copy()
        if frame.empty:
            raise ValueError("Scored Tickets is empty.")

        correct_columns = [column for column in frame.columns if str(column).startswith("correct_")]
        if not correct_columns:
            raise ValueError("Scored Tickets has no correct_* evaluation columns.")
        fields = [str(column)[len("correct_") :] for column in correct_columns]
        total = len(frame)
        prediction_coverage = (
            float(frame["prediction_received"].fillna(False).astype(bool).mean())
            if "prediction_received" in frame.columns
            else 0.0
        )
        overall = (
            float(frame["all_fields_correct"].fillna(False).astype(bool).mean())
            if "all_fields_correct" in frame.columns
            else 0.0
        )

        field_rows: list[dict[str, Any]] = []
        for field in fields:
            correct = frame[f"correct_{field}"].fillna(False).astype(bool)
            predicted_column = f"predicted_{field}"
            if predicted_column in frame.columns:
                coverage = frame[predicted_column].map(self._present)
            else:
                coverage = pd.Series([False] * total)
            field_rows.append(
                {
                    "field": field,
                    "accuracy": float(correct.mean()),
                    "coverage": float(coverage.mean()),
                    "correct": int(correct.sum()),
                    "total": total,
                }
            )
        field_performance = pd.DataFrame(field_rows).sort_values(["accuracy", "field"]).reset_index(drop=True)

        scenario_field = str(self.scenario_field or "_test_scenario").strip()
        scenario_rows: list[dict[str, Any]] = []
        if scenario_field in frame.columns:
            scenario_values = frame[scenario_field].where(frame[scenario_field].notna(), "Unspecified")
            for scenario, group in frame.assign(_scenario_value=scenario_values).groupby("_scenario_value", dropna=False):
                scenario_rows.append(
                    {
                        "scenario": scenario,
                        "tickets": len(group),
                        "prediction_coverage": float(group["prediction_received"].fillna(False).astype(bool).mean()),
                        "all_fields_exact_match": float(group["all_fields_correct"].fillna(False).astype(bool).mean()),
                        "average_field_accuracy": float(group[correct_columns].fillna(False).astype(bool).mean(axis=1).mean()),
                    }
                )
        scenario_performance = pd.DataFrame(scenario_rows)

        confusion_field = str(self.confusion_field or "assignment_group").strip()
        expected_column = f"expected_{confusion_field}"
        predicted_column = f"predicted_{confusion_field}"
        if expected_column in frame.columns and predicted_column in frame.columns:
            confusion = (
                frame.assign(
                    expected=frame[expected_column].map(lambda value: str(value) if self._present(value) else "Missing"),
                    predicted=frame[predicted_column].map(lambda value: str(value) if self._present(value) else "Missing"),
                )
                .groupby(["expected", "predicted"], dropna=False)
                .size()
                .reset_index(name="tickets")
                .sort_values("tickets", ascending=False)
                .reset_index(drop=True)
            )
        else:
            confusion = pd.DataFrame(columns=["expected", "predicted", "tickets"])

        failures = frame.loc[~frame["all_fields_correct"].fillna(False).astype(bool)].copy()
        failure_columns = [
            column
            for column in frame.columns
            if column in {scenario_field, "prediction_received"}
            or str(column).startswith("expected_")
            or str(column).startswith("predicted_")
            or str(column).startswith("correct_")
        ]
        id_candidates = [column for column in frame.columns if column in {"number", "sys_id", "_evaluation_id"}]
        failures = failures[id_candidates + failure_columns].head(max(int(self.failure_limit), 1)).reset_index(drop=True)

        self._dashboard_cache = {
            "total": total,
            "prediction_coverage": prediction_coverage,
            "overall": overall,
            "field_performance": field_performance,
            "scenario_performance": scenario_performance,
            "confusion": confusion,
            "failures": failures,
        }
        return self._dashboard_cache

    def build_dashboard(self) -> Message:
        result = self._analyze()
        lines = [
            "# Know Your BAU Evaluation",
            "",
            "| Measure | Result | Visual |",
            "|---|---:|:---|",
            f"| Tickets evaluated | {result['total']} | |",
            f"| Prediction coverage | {result['prediction_coverage']:.1%} | `{self._bar(result['prediction_coverage'])}` |",
            f"| All-fields exact match | {result['overall']:.1%} | `{self._bar(result['overall'])}` |",
            "",
            "## Field performance",
            "",
            "| Field | Accuracy | Coverage | Accuracy bar |",
            "|---|---:|---:|:---|",
        ]
        for row in result["field_performance"].to_dict(orient="records"):
            lines.append(
                f"| {row['field']} | {row['accuracy']:.1%} | {row['coverage']:.1%} | `{self._bar(row['accuracy'])}` |"
            )
        if not result["scenario_performance"].empty:
            lines.extend(
                [
                    "",
                    "## Scenario performance",
                    "",
                    "| Scenario | Tickets | Average field accuracy | All-fields match |",
                    "|---|---:|---:|---:|",
                ]
            )
            for row in result["scenario_performance"].to_dict(orient="records"):
                lines.append(
                    f"| {row['scenario']} | {row['tickets']} | {row['average_field_accuracy']:.1%} | "
                    f"{row['all_fields_exact_match']:.1%} |"
                )
        lines.extend(
            [
                "",
                f"Failed tickets shown in the **Failed Tickets** output: {len(result['failures'])}.",
                "Use **Confusion Matrix Data** to inspect the most common routing substitutions.",
            ]
        )
        return Message(text="\n".join(lines), properties=Properties(allow_markdown=True))

    def build_field_performance(self) -> DataFrame:
        return DataFrame(self._analyze()["field_performance"])

    def build_scenario_performance(self) -> DataFrame:
        return DataFrame(self._analyze()["scenario_performance"])

    def build_confusion_matrix(self) -> DataFrame:
        return DataFrame(self._analyze()["confusion"])

    def build_failed_tickets(self) -> DataFrame:
        return DataFrame(self._analyze()["failures"])
