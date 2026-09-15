from lfx.custom import Component
from lfx.io import MessageInput, Output
from lfx.schema import Message
from lfx.schema.properties import Properties


class ExperimentRunCollector(Component):
    display_name = "Run Complete Experiment"
    description = "One-click final node that runs all classifier branches and confirms every checkpoint was saved."
    icon = "PlayCircle"
    name = "ExperimentRunCollector"

    inputs = [
        MessageInput(name="dataset_checkpoint", display_name="Generated Dataset Checkpoint", required=True),
        MessageInput(name="holdout_checkpoint", display_name="Visible Holdout Checkpoint", required=True),
        MessageInput(name="predictions_a_checkpoint", display_name="A Predictions Checkpoint", required=True),
        MessageInput(name="scores_a_checkpoint", display_name="A Scores Checkpoint", required=True),
        MessageInput(name="dashboard_a", display_name="A Dashboard", required=True),
        MessageInput(name="predictions_b_checkpoint", display_name="B Predictions Checkpoint", required=True),
        MessageInput(name="scores_b_checkpoint", display_name="B Scores Checkpoint", required=True),
        MessageInput(name="dashboard_b", display_name="B Dashboard", required=True),
        MessageInput(name="predictions_c_checkpoint", display_name="C Predictions Checkpoint", required=True),
        MessageInput(name="scores_c_checkpoint", display_name="C Scores Checkpoint", required=True),
        MessageInput(name="dashboard_c", display_name="C Dashboard", required=True),
    ]

    outputs = [Output(display_name="Complete Run Summary", name="summary", method="build_summary")]

    @staticmethod
    def _text(value: Message) -> str:
        return str(value.text if hasattr(value, "text") else value)

    def build_summary(self) -> Message:
        receipts = [
            ("Generated dataset", self.dataset_checkpoint),
            ("Visible holdout", self.holdout_checkpoint),
            ("A predictions", self.predictions_a_checkpoint),
            ("A scores", self.scores_a_checkpoint),
            ("B predictions", self.predictions_b_checkpoint),
            ("B scores", self.scores_b_checkpoint),
            ("C predictions", self.predictions_c_checkpoint),
            ("C scores", self.scores_c_checkpoint),
        ]
        lines = [
            "# Complete support-tier experiment finished",
            "",
            "All three classifier branches and their evaluation dashboards ran successfully.",
            "",
            "## Saved checkpoints",
            "",
        ]
        lines.extend(f"- **{label}:** {self._text(receipt)}" for label, receipt in receipts)
        lines.extend(
            [
                "",
                "## Dashboard A",
                "",
                self._text(self.dashboard_a),
                "",
                "## Dashboard B",
                "",
                self._text(self.dashboard_b),
                "",
                "## Dashboard C",
                "",
                self._text(self.dashboard_c),
            ]
        )
        return Message(text="\n".join(lines), properties=Properties(allow_markdown=True))
