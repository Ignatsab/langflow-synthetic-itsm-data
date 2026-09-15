import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
from openai import AsyncOpenAI, BadRequestError

from lfx.custom import Component
from lfx.io import BoolInput, DropdownInput, FloatInput, IntInput, MultilineInput, Output, SecretStrInput, StrInput
from lfx.schema import Data, DataFrame, Message


DEFAULT_INCIDENT_FIELDS = json.dumps(
    [
        {"name": "sys_id", "type": "string", "description": "Unique fictional 32-character lowercase hexadecimal ID."},
        {"name": "number", "type": "string", "description": "Unique ServiceNow-style incident number such as INC0012345."},
        {"name": "short_description", "type": "string", "description": "Short user-reported issue summary; vary clarity and terminology."},
        {"name": "description", "type": "string", "description": "Full issue narrative with realistic symptoms, context, and occasional missing details."},
        {"name": "state", "type": "string", "description": "One of New, In Progress, On Hold, Resolved, Closed, or Canceled."},
        {"name": "impact", "type": "integer", "description": "1=High, 2=Medium, 3=Low."},
        {"name": "urgency", "type": "integer", "description": "1=High, 2=Medium, 3=Low."},
        {"name": "priority", "type": "integer", "description": "ServiceNow priority derived consistently from impact and urgency; 1 is most critical and 5 is lowest."},
        {"name": "category", "type": "string", "description": "Examples: Network, Software, Hardware, Access, Email, Database, Security."},
        {"name": "subcategory", "type": "string", "description": "A plausible subcategory consistent with category."},
        {"name": "assignment_group", "type": "string", "description": "Fictional resolver group appropriate for the issue."},
        {"name": "caller_id", "type": "string", "description": "Fictional employee identifier; never use real personal data."},
        {"name": "opened_at", "type": "datetime", "description": "ISO 8601 timestamp."},
        {"name": "updated_at", "type": "datetime", "description": "ISO 8601 timestamp at or after opened_at."},
        {"name": "close_code", "type": "string|null", "description": "Null unless resolved or closed; otherwise a plausible close code."},
        {"name": "resolution_notes", "type": "string|null", "description": "Null for active tickets; plausible resolution for resolved or closed tickets."},
        {"name": "business_service", "type": "string", "description": "Fictional affected business service."},
        {"name": "_test_scenario", "type": "string", "description": "Ground-truth scenario label: common, edge, ambiguous, noisy, or adversarial."},
        {"name": "_expected_category", "type": "string", "description": "Ground-truth category expected from the AI agent."},
        {"name": "_expected_ticket_type", "type": "string", "description": "Ground-truth type, such as incident, service request, access request, security event, or problem candidate."},
        {"name": "_expected_required_skills", "type": "array[string]", "description": "Ground-truth technical skills needed to resolve or triage the ticket."},
        {"name": "_expected_technology", "type": "string", "description": "Ground-truth primary technology or platform involved."},
        {
            "name": "_expected_support_level",
            "type": "string",
            "description": (
                "Ground-truth support tier by resolution complexity: "
                "L1=routine/lowest complexity, L2=specialist/intermediate complexity, "
                "L3=senior solution engineering/highest complexity."
            ),
        },
        {"name": "_expected_assignment_group", "type": "string", "description": "Ground-truth resolver group expected from the AI agent."},
        {"name": "_expected_agent_action", "type": "string", "description": "Ground-truth next action expected from the AI agent."},
    ],
    indent=2,
)

DEFAULT_CHANGE_REQUEST_FIELDS = json.dumps(
    [
        {"name": "sys_id", "type": "string", "description": "Unique fictional 32-character lowercase hexadecimal ID."},
        {"name": "number", "type": "string", "description": "Unique fictional ServiceNow change number such as CHG0012345."},
        {"name": "short_description", "type": "string", "description": "Concise summary of the proposed change."},
        {"name": "description", "type": "string", "description": "Business and technical reason for the change."},
        {"name": "type", "type": "string", "description": "One of Standard, Normal, or Emergency."},
        {"name": "state", "type": "string", "description": "One of New, Assess, Authorize, Scheduled, Implement, Review, Closed, or Canceled."},
        {"name": "risk", "type": "string", "description": "One of High, Moderate, or Low; consistent with scope and potential impact."},
        {"name": "impact", "type": "integer", "description": "1=High, 2=Medium, 3=Low."},
        {"name": "priority", "type": "integer", "description": "Integer 1 through 5, consistent with risk and impact."},
        {"name": "assignment_group", "type": "string", "description": "Fictional group responsible for implementing the change."},
        {"name": "requested_by", "type": "string", "description": "Fictional employee identifier; never use real personal data."},
        {"name": "business_service", "type": "string", "description": "Fictional service affected by the change."},
        {"name": "planned_start_date", "type": "datetime", "description": "ISO 8601 planned start timestamp."},
        {"name": "planned_end_date", "type": "datetime", "description": "ISO 8601 timestamp after planned_start_date."},
        {"name": "implementation_plan", "type": "string", "description": "Concrete, plausible implementation steps."},
        {"name": "backout_plan", "type": "string", "description": "Concrete rollback steps appropriate for the implementation."},
        {"name": "test_plan", "type": "string", "description": "Checks that demonstrate whether the change succeeded."},
        {"name": "close_code", "type": "string|null", "description": "Null before closure; otherwise Successful, Successful with Issues, or Unsuccessful."},
        {"name": "close_notes", "type": "string|null", "description": "Null before closure; otherwise a plausible outcome summary."},
        {"name": "_test_scenario", "type": "string", "description": "Ground-truth scenario label: common, edge, ambiguous, noisy, or adversarial."},
        {"name": "_expected_assignment_group", "type": "string", "description": "Ground-truth resolver group expected from the AI agent."},
        {"name": "_expected_agent_action", "type": "string", "description": "Ground-truth next action expected from the AI agent."},
    ],
    indent=2,
)

DEFAULT_SERVICE_REQUEST_FIELDS = json.dumps(
    [
        {"name": "sys_id", "type": "string", "description": "Unique fictional 32-character lowercase hexadecimal ID."},
        {"name": "number", "type": "string", "description": "Unique fictional ServiceNow request number such as REQ0012345."},
        {"name": "short_description", "type": "string", "description": "Concise summary of what the user requested."},
        {"name": "description", "type": "string", "description": "Full request details, business need, and relevant constraints."},
        {"name": "catalog_item", "type": "string", "description": "Fictional catalog item appropriate for the request."},
        {"name": "request_type", "type": "string", "description": "A plausible category such as Access, Hardware, Software, Information, or Workplace."},
        {"name": "state", "type": "string", "description": "One of Pending Approval, Open, Work in Progress, Closed Complete, Closed Incomplete, or Canceled."},
        {"name": "stage", "type": "string", "description": "A stage consistent with state, such as Request Approved, Fulfillment, Delivery, or Completed."},
        {"name": "approval", "type": "string", "description": "One of Not Requested, Requested, Approved, Rejected, or Not Required."},
        {"name": "priority", "type": "integer", "description": "Integer 1 through 5; 1 is most urgent and 5 is lowest."},
        {"name": "assignment_group", "type": "string", "description": "Fictional fulfillment group appropriate for the catalog item."},
        {"name": "requested_for", "type": "string", "description": "Fictional employee identifier; never use real personal data."},
        {"name": "requested_by", "type": "string", "description": "Fictional employee identifier; never use real personal data."},
        {"name": "opened_at", "type": "datetime", "description": "ISO 8601 timestamp."},
        {"name": "due_date", "type": "datetime|null", "description": "Plausible ISO 8601 due timestamp after opened_at, or null when not applicable."},
        {"name": "quantity", "type": "integer", "description": "Positive requested quantity."},
        {"name": "price", "type": "number", "description": "Non-negative fictional unit price."},
        {"name": "currency", "type": "string", "description": "ISO 4217 currency code consistent across the record."},
        {"name": "business_service", "type": "string|null", "description": "Fictional related business service, or null when not applicable."},
        {"name": "comments", "type": "string|null", "description": "Plausible fictional requester or fulfiller comments."},
        {"name": "_test_scenario", "type": "string", "description": "Ground-truth scenario label: common, edge, ambiguous, noisy, or adversarial."},
        {"name": "_expected_assignment_group", "type": "string", "description": "Ground-truth fulfillment group expected from the AI agent."},
        {"name": "_expected_agent_action", "type": "string", "description": "Ground-truth next action expected from the AI agent."},
    ],
    indent=2,
)

SERVICENOW_TABLES = {
    "Incident": ("incident", DEFAULT_INCIDENT_FIELDS),
    "Change Request": ("change_request", DEFAULT_CHANGE_REQUEST_FIELDS),
    "Service Request": ("sc_request", DEFAULT_SERVICE_REQUEST_FIELDS),
}

SERVICENOW_GOALS = {
    "Incident": (
        "Evaluate whether an AI service-desk agent correctly categorizes incidents, assigns the right resolver group, "
        "recognizes priority and SLA risk, asks for missing information, recommends the correct next action, and assigns "
        "support by resolution complexity: L1 for routine/lowest-complexity work, L2 for specialist work, and "
        "L3 for the highest-complexity senior solution-engineering work."
    ),
    "Change Request": (
        "Evaluate whether an AI change-management agent correctly assesses type, risk, impact, scheduling, approvals, "
        "implementation readiness, rollback quality, assignment group, and the correct next action."
    ),
    "Service Request": (
        "Evaluate whether an AI fulfillment agent correctly identifies the catalog need, approval path, priority, "
        "fulfillment group, missing information, delivery stage, and the correct next action."
    ),
}

SERVICENOW_CONTEXTS = {
    "Incident": (
        "Use one fictional mid-sized company with a stable service catalog and resolver-group taxonomy. Keep category, "
        "subcategory, assignment group, business service, priority, timestamps, state, resolution, and expected support "
        "level mutually consistent. Support level describes resolution complexity and expertise, not business impact: "
        "L1 is lowest, L2 is intermediate, and L3 is highest. Include enough diagnostic evidence for a safe proposed "
        "resolution for L1 and L2 incidents; L3 incidents should normally require escalation."
    ),
    "Change Request": (
        "Use one fictional mid-sized company with recurring services and implementation teams. Keep change type, risk, "
        "impact, priority, assignment group, schedule, plans, state, close code, and close notes mutually consistent."
    ),
    "Service Request": (
        "Use one fictional mid-sized company with a stable catalog and fulfillment groups. Keep catalog item, request type, "
        "approval, priority, assignment group, dates, price, currency, stage, and state mutually consistent."
    ),
}

SERVICENOW_SCENARIOS = {
    "Incident": (
        "Approximately 60% common incidents, 20% edge cases, 10% ambiguous or incomplete/noisy cases, and 10% adversarial cases. "
        "Include varied writing styles, typos, duplicates, escalations, missing optional data, outages, and SLA risks. "
        "Keep the ground-truth support levels approximately balanced across L1, L2, and L3 while preserving realistic evidence."
    ),
    "Change Request": (
        "Approximately 55% normal changes, 20% standard changes, 10% emergency changes, 10% risky or incomplete plans, and 5% adversarial text. "
        "Include scheduling conflicts, weak rollback plans, approval gaps, failed changes, and successful reviews."
    ),
    "Service Request": (
        "Approximately 60% common requests, 20% unusual catalog combinations, 10% incomplete or ambiguous requests, and 10% rejected, canceled, or adversarial cases. "
        "Include access, hardware, software, information, approval, delivery, and fulfillment variations."
    ),
}


class SyntheticDatasetGenerator(Component):
    display_name = "Synthetic ITSM Dataset Generator"
    description = "Generates schema-driven synthetic test data with an OpenAI-compatible LLM proxy."
    icon = "DatabaseZap"
    name = "SyntheticDatasetGenerator"

    inputs = [
        BoolInput(
            name="dry_run",
            display_name="Dry Run (No LLM Call)",
            value=True,
            info="Preview and validate the prompt without using credentials or calling the model.",
        ),
        BoolInput(
            name="reuse_checkpoint",
            display_name="Reuse Matching Dataset Checkpoint",
            value=True,
            info="Load a saved dataset when it contains at least Number of Records; otherwise continue generating and save it.",
        ),
        StrInput(
            name="checkpoint_name",
            display_name="Dataset Checkpoint Name",
            value="servicenow_incidents_checkpoint.json",
            info="Change this name to start a completely new experiment dataset.",
        ),
        DropdownInput(
            name="schema_preset",
            display_name="Record Type",
            options=[*SERVICENOW_TABLES, "Custom"],
            value="Incident",
            real_time_refresh=True,
            info="Select Incident, Change Request, or Service Request for a validated built-in schema. Custom is available under Advanced.",
        ),
        StrInput(
            name="base_url",
            display_name="OpenAI-Compatible Base URL",
            value="",
            info="Enter the endpoint, or leave blank to use OPENAI_COMPATIBLE_BASE_URL from the Langflow server environment.",
        ),
        SecretStrInput(
            name="api_key",
            display_name="API Key",
            value="",
            load_from_db=False,
            info="Enter the key, or leave blank to use OPENAI_COMPATIBLE_API_KEY from the Langflow server environment.",
        ),
        StrInput(
            name="model_name",
            display_name="Model Name",
            value="gpt-oss-120b",
            info="Model served by the OpenAI-compatible endpoint.",
        ),
        StrInput(
            name="table_name",
            display_name="Table Name",
            value="incident",
            info="Shows the selected ServiceNow table name. It is editable when Record Type is Custom.",
        ),
        MultilineInput(
            name="field_definitions",
            display_name="Field Definitions (JSON)",
            value=DEFAULT_INCIDENT_FIELDS,
            info="Shows the selected schema with field descriptions. Built-in presets use their protected schema; select Custom to edit it.",
        ),
        IntInput(name="record_count", display_name="Number of Records", value=50),
        MultilineInput(
            name="test_goal",
            display_name="Test Goal",
            value=SERVICENOW_GOALS["Incident"],
        ),
        MultilineInput(
            name="dataset_context",
            display_name="Dataset Context and Relationships",
            value=SERVICENOW_CONTEXTS["Incident"],
        ),
        MultilineInput(
            name="scenario_guidance",
            display_name="Scenario Mix",
            value=SERVICENOW_SCENARIOS["Incident"],
        ),
        MultilineInput(
            name="reference_examples",
            display_name="Sanitized Reference Examples (JSON)",
            value="[]",
            info=(
                "Optional examples used to learn structure, vocabulary, and group patterns. Paste a JSON array of records "
                "or an object whose keys are group names. Use only data approved for your LLM environment."
            ),
        ),
        StrInput(
            name="example_group_field",
            display_name="Reference Group Field",
            value="assignment_group",
            advanced=True,
            info="Field used to learn group-specific patterns, such as assignment_group, category, or request_type.",
        ),
        StrInput(
            name="redact_reference_fields",
            display_name="Fields to Redact from Examples",
            value="sys_id,caller_id,opened_by,requested_for,assigned_to,email,phone",
            advanced=True,
            info="Comma-separated field names replaced before examples are sent to the LLM.",
        ),
        IntInput(
            name="max_reference_examples",
            display_name="Maximum Reference Examples",
            value=20,
            advanced=True,
            info="Caps prompt size. Select a representative mix across the groups you want to test.",
        ),
        IntInput(
            name="batch_size",
            display_name="Records per Generation Call",
            value=10,
            info="The component loops until Number of Records is reached. Keep this at 10 for models with a smaller context window.",
        ),
        BoolInput(
            name="maintain_continuity",
            display_name="Keep Dataset Connected Across Calls",
            value=True,
            info="Runs batches sequentially and sends a compact profile of earlier records to each next call.",
        ),
        IntInput(
            name="continuity_sample_size",
            display_name="Recent Records in Continuity Profile",
            value=3,
            advanced=True,
            info="Number of compact recent records included alongside distribution summaries. Capped at 10.",
        ),
        IntInput(
            name="max_concurrency",
            display_name="Concurrent LLM Calls",
            value=2,
            advanced=True,
            info="Used only when connected-dataset continuity is disabled. Use 1 for a single-threaded local server.",
        ),
        BoolInput(
            name="compact_prompt",
            display_name="Compact Prompt",
            value=True,
            advanced=True,
            info="Reduces repeated input tokens by sending schema and examples as compact JSON.",
        ),
        FloatInput(name="temperature", display_name="Temperature", value=0.7, advanced=True),
        BoolInput(
            name="use_json_mode",
            display_name="Request JSON Mode",
            value=True,
            advanced=True,
            info="If unsupported by the proxy, the component automatically retries without JSON mode.",
        ),
    ]

    outputs = [
        Output(display_name="Dataset (DataFrame)", name="dataset", method="build_dataframe"),
        Output(display_name="Dataset (JSON)", name="dataset_json", method="build_json"),
        Output(display_name="Generation Summary", name="summary", method="build_summary"),
        Output(display_name="Prompt Preview", name="prompt_preview", method="build_prompt_preview"),
        Output(display_name="Continuity Profile", name="continuity_profile", method="build_continuity_profile"),
    ]

    def update_build_config(self, build_config: dict, field_value: Any, field_name: str | None = None) -> dict:
        if field_name == "schema_preset" and field_value in SERVICENOW_TABLES:
            table_name, schema = SERVICENOW_TABLES[field_value]
            build_config["table_name"]["value"] = table_name
            build_config["field_definitions"]["value"] = schema
            build_config["test_goal"]["value"] = SERVICENOW_GOALS[field_value]
            build_config["dataset_context"]["value"] = SERVICENOW_CONTEXTS[field_value]
            build_config["scenario_guidance"]["value"] = SERVICENOW_SCENARIOS[field_value]
        return build_config

    def _table_config(self) -> tuple[str, str]:
        selection = str(self.schema_preset or "Custom")
        if selection != "Custom":
            if selection not in SERVICENOW_TABLES:
                raise ValueError(f"Unsupported schema preset: {selection}")
            return SERVICENOW_TABLES[selection]
        table_name = str(self.table_name or "").strip()
        if not table_name:
            raise ValueError("Custom Table Name is required when Data Source is Custom.")
        return table_name, str(self.field_definitions or "")

    def _parse_fields(self) -> list[dict[str, Any]]:
        _, field_definitions = self._table_config()
        try:
            parsed = json.loads(field_definitions)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Field Definitions is not valid JSON: {exc}") from exc
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("Field Definitions must be a non-empty JSON array.")
        names: set[str] = set()
        for index, field in enumerate(parsed):
            if not isinstance(field, dict) or not field.get("name"):
                raise ValueError(f"Field definition {index + 1} must be an object with a non-empty 'name'.")
            name = str(field["name"])
            if name in names:
                raise ValueError(f"Duplicate field name: {name}")
            names.add(name)
        return parsed

    def _parse_reference_examples(self) -> list[dict[str, Any]]:
        text = str(self.reference_examples or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Sanitized Reference Examples is not valid JSON: {exc}") from exc

        records: list[dict[str, Any]] = []
        group_field = str(self.example_group_field or "assignment_group").strip()
        if isinstance(parsed, list):
            records = [item for item in parsed if isinstance(item, dict)]
        elif isinstance(parsed, dict):
            for group_name, group_records in parsed.items():
                if not isinstance(group_records, list):
                    raise ValueError("Each group in Reference Examples must contain a JSON array of records.")
                for item in group_records:
                    if isinstance(item, dict):
                        record = dict(item)
                        if group_field:
                            record.setdefault(group_field, group_name)
                        records.append(record)
        else:
            raise ValueError("Reference Examples must be a JSON array or an object containing group arrays.")

        limit = min(max(int(self.max_reference_examples), 0), 100)
        redacted_fields = {
            name.strip().lower()
            for name in str(self.redact_reference_fields or "").split(",")
            if name.strip()
        }

        def sanitize(value: Any, field_name: str = "") -> Any:
            if field_name.lower() in redacted_fields:
                return f"[REDACTED_{field_name.upper()}]"
            if isinstance(value, dict):
                return {key: sanitize(item, str(key)) for key, item in value.items()}
            if isinstance(value, list):
                return [sanitize(item, field_name) for item in value]
            if isinstance(value, str):
                return re.sub(
                    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
                    "[REDACTED_EMAIL]",
                    value,
                    flags=re.IGNORECASE,
                )
            return value

        return [sanitize(record) for record in records[:limit]]

    def _secret(self) -> str:
        value = self.api_key
        if hasattr(value, "get_secret_value"):
            return value.get_secret_value()
        return str(value or "")

    def _checkpoint_path(self) -> Path:
        directory = Path(os.getenv("LANGFLOW_CHECKPOINT_DIR") or (Path.cwd() / "langflow_checkpoints"))
        safe_name = Path(str(self.checkpoint_name or "servicenow_incidents_checkpoint.json")).name
        if not safe_name.endswith(".json"):
            safe_name += ".json"
        return directory / safe_name

    def _checkpoint_signature(
        self,
        table_name: str,
        fields: list[dict[str, Any]],
        examples: list[dict[str, Any]],
    ) -> str:
        payload = {
            "schema_preset": str(self.schema_preset or "Custom"),
            "table_name": table_name,
            "fields": fields,
            "test_goal": str(self.test_goal or ""),
            "dataset_context": str(self.dataset_context or ""),
            "scenario_guidance": str(self.scenario_guidance or ""),
            "reference_examples": examples,
            "example_group_field": str(self.example_group_field or ""),
            "maintain_continuity": bool(self.maintain_continuity),
            "model_name": str(self.model_name or "gpt-oss-120b"),
            "temperature": float(self.temperature),
            "use_json_mode": bool(self.use_json_mode),
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _load_checkpoint(self, signature: str) -> list[dict[str, Any]]:
        if not bool(self.reuse_checkpoint):
            return []
        path = self._checkpoint_path()
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("input_signature") != signature:
                return []
            records = payload.get("records", payload) if isinstance(payload, dict) else payload
            return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_checkpoint(self, records: list[dict[str, Any]], signature: str) -> str:
        path = self._checkpoint_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"input_signature": signature, "record_count": len(records), "records": records},
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        return str(path)

    def _system_prompt(self) -> str:
        is_servicenow = str(self.schema_preset or "Custom") != "Custom"
        domain_guidance = (
            "Create realistic ServiceNow records and follow ServiceNow field semantics. "
            if is_servicenow
            else "Create realistic records for the domain described by the user. "
        )
        return (
            "You are a senior enterprise test-data engineer. "
            f"{domain_guidance}"
            "Create synthetic and fictional data only. Never reproduce real people, organizations, credentials, secrets, or customer records. "
            "Reference examples are pattern guidance only: learn their vocabulary, structure, distributions, and group correlations, "
            "but never copy a row or identifying value. "
            "Obey the requested schema and semantic constraints. Return only valid JSON: an object with one key named records whose value is an array. "
            "Every record must contain every requested field; use null only when allowed or contextually appropriate. "
            "Keep related values internally consistent. Ground-truth fields beginning with an underscore describe the expected behavior of the system under test."
        )

    def _continuity_profile(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}
        distribution_fields = (
            "category",
            "subcategory",
            "state",
            "priority",
            "assignment_group",
            "business_service",
            "type",
            "risk",
            "request_type",
            "catalog_item",
            "approval",
            "stage",
            "_test_scenario",
        )
        distributions: dict[str, dict[str, int]] = {}
        for field in distribution_fields:
            counts: dict[str, int] = {}
            for record in records:
                value = record.get(field)
                if value is None or isinstance(value, (dict, list)):
                    continue
                label = str(value)[:100]
                counts[label] = counts.get(label, 0) + 1
            if counts:
                distributions[field] = dict(
                    sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]
                )

        recent_fields = (
            "number",
            "category",
            "subcategory",
            "state",
            "priority",
            "assignment_group",
            "business_service",
            "type",
            "risk",
            "request_type",
            "catalog_item",
            "approval",
            "stage",
            "opened_at",
            "planned_start_date",
            "_test_scenario",
        )
        sample_size = min(max(int(self.continuity_sample_size), 0), 10)
        recent_records = [
            {
                field: (str(record[field])[:160] if isinstance(record[field], str) else record[field])
                for field in recent_fields
                if field in record
            }
            for record in records[-sample_size:]
        ]
        numbers = [str(record["number"]) for record in records if record.get("number")]
        return {
            "generated_so_far": len(records),
            "first_record_number": numbers[0] if numbers else None,
            "latest_record_number": numbers[-1] if numbers else None,
            "distributions": distributions,
            "recent_records": recent_records,
        }

    def _batch_prompt(
        self,
        fields: list[dict[str, Any]],
        examples: list[dict[str, Any]],
        count: int,
        batch_number: int,
        continuity_profile: dict[str, Any] | None = None,
    ) -> str:
        table_name, _ = self._table_config()
        json_options = {"ensure_ascii": False}
        if self.compact_prompt:
            json_options["separators"] = (",", ":")
        else:
            json_options["indent"] = 2
        examples_text = (
            json.dumps(examples, **json_options)
            if examples
            else "No reference examples supplied."
        )
        fields_text = json.dumps(fields, **json_options)
        continuity_text = (
            json.dumps(continuity_profile, **json_options)
            if continuity_profile
            else "This is the first batch; no earlier records exist."
        )
        source = "ServiceNow" if str(self.schema_preset or "Custom") != "Custom" else "custom"
        return (
            f"Generate exactly {count} distinct synthetic records for {source} table {table_name!r}.\n\n"
            f"TEST GOAL\n{self.test_goal}\n\n"
            f"DATASET CONTEXT AND RELATIONSHIPS\n{self.dataset_context}\n\n"
            f"SCENARIO MIX\n{self.scenario_guidance}\n\n"
            f"FIELD DEFINITIONS\n{fields_text}\n\n"
            f"SANITIZED REFERENCE EXAMPLES\n{examples_text}\n\n"
            f"REFERENCE GROUP FIELD\n{self.example_group_field}\n\n"
            f"EARLIER DATASET CONTINUITY PROFILE\n{continuity_text}\n\n"
            "Match realistic patterns and group-specific distinctions shown by the references while creating wholly new cases. "
            "Continue the same fictional organization, recurring services, group taxonomy, chronology, and identifier sequence reflected in the continuity profile. "
            "Preserve its broad distributions without mechanically repeating earlier values. "
            "Do not repeat reference identifiers, wording, timestamps, or complete records. Cover the represented groups meaningfully. "
            f"This is generation batch {batch_number}. Use diverse values and avoid template-like repetition. "
            "Do not include explanations or Markdown. Return compact JSON as {\"records\":[...]} only."
        )

    def _preview(self, fields: list[dict[str, Any]], examples: list[dict[str, Any]]) -> str:
        count = min(max(int(self.record_count), 1), max(int(self.batch_size), 1))
        return f"SYSTEM\n{self._system_prompt()}\n\nUSER\n{self._batch_prompt(fields, examples, count, 1)}"

    @staticmethod
    def _parse_response(text: str) -> list[dict[str, Any]]:
        cleaned = text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("The model response did not contain a valid JSON object.")
            payload = json.loads(cleaned[start : end + 1])
        records = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("The model response must contain a 'records' array.")
        return [record for record in records if isinstance(record, dict)]

    async def _request_batch(
        self,
        client: AsyncOpenAI,
        fields: list[dict[str, Any]],
        examples: list[dict[str, Any]],
        count: int,
        batch_number: int,
        model: str,
        continuity_profile: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._batch_prompt(fields, examples, count, batch_number, continuity_profile),
                },
            ],
            "temperature": float(self.temperature),
        }
        if self.use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await client.chat.completions.create(**kwargs)
        except BadRequestError:
            if "response_format" not in kwargs:
                raise
            kwargs.pop("response_format")
            response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned an empty response.")
        return self._parse_response(content)

    async def _generate(self) -> dict[str, Any]:
        table_name, _ = self._table_config()
        fields = self._parse_fields()
        examples = self._parse_reference_examples()
        checkpoint_signature = self._checkpoint_signature(table_name, fields, examples)
        requested = int(self.record_count)
        if requested < 1:
            raise ValueError("Number of Records must be at least 1.")
        batch_size = min(max(int(self.batch_size), 1), 100)
        if self.dry_run:
            return {
                "dry_run": True,
                "schema_preset": self.schema_preset,
                "table_name": table_name,
                "requested_records": requested,
                "field_count": len(fields),
                "reference_example_count": len(examples),
                "batch_size": batch_size,
                "maintain_continuity": bool(self.maintain_continuity),
                "continuity_profile": {},
                "records": [],
                "prompt_preview": self._preview(fields, examples),
            }
        checkpoint_records = self._load_checkpoint(checkpoint_signature)
        if len(checkpoint_records) >= requested:
            records = checkpoint_records[:requested]
            return {
                "dry_run": False,
                "from_checkpoint": True,
                "schema_preset": self.schema_preset,
                "table_name": table_name,
                "requested_records": requested,
                "generated_records": len(records),
                "field_count": len(fields),
                "reference_example_count": len(examples),
                "batch_size": batch_size,
                "generation_calls": 0,
                "maintain_continuity": bool(self.maintain_continuity),
                "continuity_profile": self._continuity_profile(records),
                "records": records,
                "checkpoint_path": str(self._checkpoint_path()),
                "prompt_preview": self._preview(fields, examples),
            }
        base_url = str(self.base_url or os.getenv("OPENAI_COMPATIBLE_BASE_URL") or "").strip()
        api_key = self._secret() or os.getenv("OPENAI_COMPATIBLE_API_KEY") or ""
        model = str(self.model_name or "gpt-oss-120b").strip()
        if not base_url:
            raise ValueError(
                "Set OpenAI-Compatible Base URL or configure OPENAI_COMPATIBLE_BASE_URL on the Langflow server."
            )
        if not api_key:
            raise ValueError(
                "Set API Key or configure OPENAI_COMPATIBLE_API_KEY on the Langflow server."
            )
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        records: list[dict[str, Any]] = checkpoint_records[:requested]
        fingerprints: set[str] = set()
        for record in records:
            fingerprints.add(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str))
        remaining_to_generate = requested - len(records)
        batch_counts = [
            min(batch_size, remaining_to_generate - offset)
            for offset in range(0, remaining_to_generate, batch_size)
        ]
        concurrency = min(max(int(self.max_concurrency), 1), 8)
        semaphore = asyncio.Semaphore(concurrency)

        async def run_batch(
            batch_number: int,
            count: int,
            continuity_profile: dict[str, Any] | None = None,
        ) -> list[dict[str, Any]]:
            async with semaphore:
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        batch = await self._request_batch(
                            client,
                            fields,
                            examples,
                            count,
                            batch_number,
                            model,
                            continuity_profile,
                        )
                        if batch:
                            return batch
                        raise ValueError("The model returned an empty records array.")
                    except Exception as exc:  # noqa: BLE001 - retry transient proxy and malformed-output failures
                        last_error = exc
                        if attempt < 2:
                            await asyncio.sleep(1 + attempt)
                raise ValueError(
                    f"Generation batch {batch_number} failed after 3 attempts: {last_error}"
                ) from last_error

        def add_records(incoming: list[dict[str, Any]]) -> None:
            previous_count = len(records)
            for record in incoming:
                fingerprint = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
                if fingerprint not in fingerprints:
                    fingerprints.add(fingerprint)
                    records.append(record)
                    if len(records) >= requested:
                        break
            if len(records) > previous_count:
                # Save after every successful chunk so an interrupted generation can resume.
                self._save_checkpoint(records, checkpoint_signature)

        batch_errors: list[str] = []
        if self.maintain_continuity:
            for batch_number, count in enumerate(batch_counts, start=1):
                profile = self._continuity_profile(records)
                try:
                    add_records(await run_batch(batch_number, count, profile))
                except Exception as exc:  # noqa: BLE001 - later fill calls can recover this missing chunk
                    batch_errors.append(str(exc))
                if len(records) >= requested:
                    break
        else:
            initial_batches = await asyncio.gather(
                *(run_batch(number, count) for number, count in enumerate(batch_counts, start=1)),
                return_exceptions=True,
            )
            for incoming in initial_batches:
                if isinstance(incoming, Exception):
                    batch_errors.append(str(incoming))
                else:
                    add_records(incoming)
                if len(records) >= requested:
                    break

        retry_number = len(batch_counts) + 1
        for _ in range(3):
            remaining = requested - len(records)
            if remaining <= 0:
                break
            profile = self._continuity_profile(records) if self.maintain_continuity else None
            try:
                add_records(await run_batch(retry_number, min(remaining, batch_size), profile))
            except Exception as exc:  # noqa: BLE001 - report all failed fill attempts together
                batch_errors.append(str(exc))
            retry_number += 1
        if len(records) < requested:
            error_summary = "; ".join(batch_errors[-3:])
            raise ValueError(
                f"The model produced {len(records)} of {requested} unique valid records after chunk retries. "
                f"Recent batch errors: {error_summary or 'the model repeatedly returned too few unique records'}. "
                "Try Records per Generation Call = 5, Concurrent LLM Calls = 1, or a smaller Number of Records."
            )
        records = records[:requested]
        checkpoint_path = self._save_checkpoint(records, checkpoint_signature)
        return {
            "dry_run": False,
            "from_checkpoint": bool(checkpoint_records),
            "schema_preset": self.schema_preset,
            "table_name": table_name,
            "requested_records": requested,
            "generated_records": len(records),
            "field_count": len(fields),
            "reference_example_count": len(examples),
            "batch_size": batch_size,
            "generation_calls": retry_number - 1,
            "maintain_continuity": bool(self.maintain_continuity),
            "continuity_profile": self._continuity_profile(records),
            "records": records,
            "checkpoint_path": checkpoint_path,
            "prompt_preview": self._preview(fields, examples),
        }

    async def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_synthetic_result_cache", None)
        if cached is None:
            cached = await self._generate()
            self._synthetic_result_cache = cached
        return cached

    async def build_dataframe(self) -> DataFrame:
        result = await self._result()
        if result["dry_run"]:
            return DataFrame(pd.DataFrame([{
                "status": "dry_run",
                "number": "DRY-RUN-00001",
                "table_name": result["table_name"],
                "requested_records": result["requested_records"],
                "field_count": result["field_count"],
                "reference_example_count": result["reference_example_count"],
            }]))
        return DataFrame(pd.DataFrame(result["records"]))

    async def build_json(self) -> Data:
        result = await self._result()
        return Data(data={key: value for key, value in result.items() if key != "prompt_preview"})

    async def build_summary(self) -> Message:
        result = await self._result()
        if result["dry_run"]:
            text = (
                f"Dry run passed for table '{result['table_name']}'. "
                f"Schema has {result['field_count']} fields and the requested dataset has {result['requested_records']} records. "
                f"The prompt includes {result['reference_example_count']} sanitized reference examples. "
                "Enter the proxy settings, switch Dry Run off, and run again to generate data."
            )
        else:
            source = "Loaded" if result.get("from_checkpoint") and result.get("generation_calls") == 0 else "Generated"
            continuity = " with continuity enabled" if result["maintain_continuity"] else ""
            text = (
                f"{source} {result['generated_records']} synthetic records for table '{result['table_name']}' "
                f"in batches of up to {result['batch_size']}{continuity}. "
                f"The dataset has {result['field_count']} fields and used {result['reference_example_count']} sanitized reference examples. "
                f"Checkpoint: {result.get('checkpoint_path', 'not saved')}."
            )
        return Message(text=text)

    async def build_prompt_preview(self) -> Message:
        result = await self._result()
        return Message(text=result["prompt_preview"])

    async def build_continuity_profile(self) -> Data:
        result = await self._result()
        return Data(data=result["continuity_profile"])
