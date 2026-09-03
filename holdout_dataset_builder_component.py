import json
from typing import Any

import pandas as pd

from lfx.custom import Component
from lfx.io import BoolInput, DataFrameInput, IntInput, Output, StrInput
from lfx.schema import DataFrame, Message


class HoldoutDatasetBuilder(Component):
    display_name = "BAU Holdout Dataset Builder"
    description = "Selects a limited test sample and removes hidden ground-truth labels before classification."
    icon = "ListFilter"
    name = "HoldoutDatasetBuilder"

    inputs = [
        DataFrameInput(name="dataset", display_name="Generated Dataset", required=True),
        IntInput(name="sample_size", display_name="Tickets to Test", value=10),
        StrInput(name="id_field", display_name="Ticket ID Field", value="number"),
        StrInput(
            name="fields_to_hide",
            display_name="Additional Fields to Hide",
            value="category,subcategory,assignment_group",
            info="Comma-separated labels that must not be visible to the BAU agent. All _expected_* fields are always hidden.",
        ),
        StrInput(
            name="visible_fields",
            display_name="Fields Sent to BAU Agent",
            value="number,short_description,description,state,impact,urgency,priority,business_service",
            info="Comma-separated allow-list that limits prompt size. The ticket ID field is always retained.",
        ),
        BoolInput(name="random_sample", display_name="Random Sample", value=True),
        IntInput(name="random_seed", display_name="Random Seed", value=42, advanced=True),
    ]

    outputs = [
        Output(display_name="Visible Tickets", name="tickets", method="build_tickets"),
        Output(display_name="Hidden Ground Truth", name="ground_truth", method="build_ground_truth"),
        Output(display_name="Split Summary", name="summary", method="build_summary"),
    ]

    def _split(self) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
        cached = getattr(self, "_split_cache", None)
        if cached is not None:
            return cached

        frame = pd.DataFrame(self.dataset).copy()
        if frame.empty:
            raise ValueError("Generated Dataset is empty.")
        size = min(max(int(self.sample_size), 1), len(frame))
        if self.random_sample and len(frame) > size:
            selected = frame.sample(n=size, random_state=int(self.random_seed)).reset_index(drop=True)
        else:
            selected = frame.head(size).reset_index(drop=True)

        id_field = str(self.id_field or "number").strip()
        if not id_field or id_field not in selected.columns or selected[id_field].duplicated().any():
            id_field = "_evaluation_id"
            selected[id_field] = [f"TEST-{index + 1:05d}" for index in range(len(selected))]
            self.id_field = id_field

        configured = {
            field.strip()
            for field in str(self.fields_to_hide or "").split(",")
            if field.strip()
        }
        hidden = sorted(
            column
            for column in selected.columns
            if str(column).startswith("_expected_") or column in configured
        )
        visible = selected.drop(columns=hidden, errors="ignore")
        allowed = [
            field.strip()
            for field in str(self.visible_fields or "").split(",")
            if field.strip()
        ]
        if allowed:
            retained = [column for column in [id_field, *allowed] if column in visible.columns]
            retained = list(dict.fromkeys(retained))
            visible = visible[retained]
        self._split_cache = (visible, selected, hidden)
        return self._split_cache

    def build_tickets(self) -> DataFrame:
        visible, _, _ = self._split()
        return DataFrame(visible)

    def build_ground_truth(self) -> DataFrame:
        _, ground_truth, _ = self._split()
        return DataFrame(ground_truth)

    def build_summary(self) -> Message:
        visible, _, hidden = self._split()
        return Message(
            text=(
                f"Prepared {len(visible)} holdout tickets. Hidden fields: "
                f"{json.dumps(hidden, ensure_ascii=False)}. Ticket ID field: {self.id_field}."
            )
        )
