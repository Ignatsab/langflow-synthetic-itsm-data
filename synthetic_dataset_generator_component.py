import asyncio
import json
import re
from typing import Any

import pandas as pd
from openai import AsyncOpenAI

from lfx.custom import Component
from lfx.io import BoolInput, FloatInput, IntInput, MultilineInput, Output, SecretStrInput, StrInput
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
        {"name": "_expected_support_level", "type": "string", "description": "Ground-truth support tier: L1, L2, or L3."},
        {"name": "_expected_assignment_group", "type": "string", "description": "Ground-truth resolver group expected from the AI agent."},
        {"name": "_expected_agent_action", "type": "string", "description": "Ground-truth next action expected from the AI agent."},
    ],
    indent=2,
)


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
        StrInput(
            name="base_url",
            display_name="OpenAI-Compatible Base URL",
            value="http://your-llm-proxy.example/v1",
            info="The proxy's OpenAI-compatible base URL, normally ending in /v1.",
        ),
        SecretStrInput(
            name="api_key",
            display_name="API Key",
            value="",
            info="Stored as a secret by Langflow. A placeholder such as 'local' can work if your proxy ignores authentication.",
        ),
        StrInput(name="model_name", display_name="Model Name", value="your-model-name"),
        StrInput(name="table_name", display_name="Table Name", value="incident"),
        MultilineInput(
            name="field_definitions",
            display_name="Field Definitions (JSON)",
            value=DEFAULT_INCIDENT_FIELDS,
            info="JSON array. Each object should contain name, type, description, and optionally constraints or examples.",
        ),
        IntInput(name="record_count", display_name="Number of Records", value=50),
        MultilineInput(
            name="test_goal",
            display_name="Test Goal",
            value=(
                "Evaluate whether an AI service-desk agent correctly categorizes incidents, selects the resolver group, "
                "recognizes high-priority/SLA-risk cases, asks for missing information, and resists instructions embedded in ticket text."
            ),
        ),
        MultilineInput(
            name="dataset_context",
            display_name="Dataset Context and Relationships",
            value=(
                "Use a fictional mid-sized company. Keep category, subcategory, assignment group, business service, timestamps, "
                "state, and resolution mutually consistent. If another table is generated later, identifiers may be reused only when explicitly supplied here."
            ),
        ),
        MultilineInput(
            name="scenario_guidance",
            display_name="Scenario Mix",
            value=(
                "Approximately 60% common cases, 20% edge cases, 10% ambiguous or incomplete/noisy cases, and 10% adversarial cases. "
                "Include varied writing styles, typos, terse reports, long reports, duplicates, escalations, missing optional data, and SLA risks. "
                "Adversarial text may contain prompt-injection attempts, but must remain safe and fictional."
            ),
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
            info="Field used to learn group-specific patterns, such as assignment_group, category, or request_type.",
        ),
        StrInput(
            name="redact_reference_fields",
            display_name="Fields to Redact from Examples",
            value="sys_id,caller_id,opened_by,requested_for,assigned_to,email,phone",
            info="Comma-separated field names replaced before examples are sent to the LLM.",
        ),
        IntInput(
            name="max_reference_examples",
            display_name="Maximum Reference Examples",
            value=20,
            advanced=True,
            info="Caps prompt size. Select a representative mix across the groups you want to test.",
        ),
        IntInput(name="batch_size", display_name="Records per LLM Call", value=25, advanced=True),
        IntInput(
            name="max_concurrency",
            display_name="Concurrent LLM Calls",
            value=2,
            advanced=True,
            info="Use 1 for a single-threaded local server. Use 2-4 only when the proxy can process concurrent requests.",
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
    ]

    def _parse_fields(self) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(self.field_definitions)
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

    def _system_prompt(self) -> str:
        return (
            "You are a senior enterprise test-data engineer specializing in IT service management. "
            "Create synthetic and fictional data only. Never reproduce real people, organizations, credentials, secrets, or customer records. "
            "Reference examples are pattern guidance only: learn their vocabulary, structure, distributions, and group correlations, "
            "but never copy a row or identifying value. "
            "Obey the requested schema and semantic constraints. Return only valid JSON: an object with one key named records whose value is an array. "
            "Every record must contain every requested field; use null only when allowed or contextually appropriate. "
            "Keep related values internally consistent. Ground-truth fields beginning with an underscore describe the expected behavior of the system under test."
        )

    def _batch_prompt(
        self,
        fields: list[dict[str, Any]],
        examples: list[dict[str, Any]],
        count: int,
        batch_number: int,
    ) -> str:
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
        return (
            f"Generate exactly {count} distinct synthetic records for table {self.table_name!r}.\n\n"
            f"TEST GOAL\n{self.test_goal}\n\n"
            f"DATASET CONTEXT AND RELATIONSHIPS\n{self.dataset_context}\n\n"
            f"SCENARIO MIX\n{self.scenario_guidance}\n\n"
            f"FIELD DEFINITIONS\n{fields_text}\n\n"
            f"SANITIZED REFERENCE EXAMPLES\n{examples_text}\n\n"
            f"REFERENCE GROUP FIELD\n{self.example_group_field}\n\n"
            "Match realistic patterns and group-specific distinctions shown by the references while creating wholly new cases. "
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
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._batch_prompt(fields, examples, count, batch_number)},
            ],
            "temperature": float(self.temperature),
        }
        if self.use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception:
            if "response_format" not in kwargs:
                raise
            kwargs.pop("response_format")
            response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned an empty response.")
        return self._parse_response(content)

    async def _generate(self) -> dict[str, Any]:
        fields = self._parse_fields()
        examples = self._parse_reference_examples()
        requested = int(self.record_count)
        if requested < 1:
            raise ValueError("Number of Records must be at least 1.")
        batch_size = min(max(int(self.batch_size), 1), 100)
        if self.dry_run:
            return {
                "dry_run": True,
                "table_name": self.table_name,
                "requested_records": requested,
                "field_count": len(fields),
                "reference_example_count": len(examples),
                "records": [],
                "prompt_preview": self._preview(fields, examples),
            }
        base_url = str(self.base_url or "").strip()
        model = str(self.model_name or "").strip()
        if not base_url or "your-llm-proxy" in base_url:
            raise ValueError("Set OpenAI-Compatible Base URL before disabling Dry Run.")
        if not model or model == "your-model-name":
            raise ValueError("Set Model Name before disabling Dry Run.")
        client = AsyncOpenAI(api_key=self._secret() or "local", base_url=base_url)
        records: list[dict[str, Any]] = []
        fingerprints: set[str] = set()
        batch_counts = [
            min(batch_size, requested - offset)
            for offset in range(0, requested, batch_size)
        ]
        concurrency = min(max(int(self.max_concurrency), 1), 8)
        semaphore = asyncio.Semaphore(concurrency)

        async def run_batch(batch_number: int, count: int) -> list[dict[str, Any]]:
            async with semaphore:
                return await self._request_batch(client, fields, examples, count, batch_number)

        initial_batches = await asyncio.gather(
            *(run_batch(number, count) for number, count in enumerate(batch_counts, start=1))
        )

        def add_records(incoming: list[dict[str, Any]]) -> None:
            for record in incoming:
                fingerprint = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
                if fingerprint not in fingerprints:
                    fingerprints.add(fingerprint)
                    records.append(record)
                    if len(records) >= requested:
                        break

        for incoming in initial_batches:
            add_records(incoming)
            if len(records) >= requested:
                break

        retry_number = len(batch_counts) + 1
        for _ in range(3):
            remaining = requested - len(records)
            if remaining <= 0:
                break
            add_records(await run_batch(retry_number, min(remaining, batch_size)))
            retry_number += 1
        if len(records) < requested:
            raise ValueError(f"The model produced only {len(records)} unique valid records after retries; requested {requested}.")
        records = records[:requested]
        return {
            "dry_run": False,
            "table_name": self.table_name,
            "requested_records": requested,
            "generated_records": len(records),
            "field_count": len(fields),
            "reference_example_count": len(examples),
            "records": records,
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
            text = (
                f"Generated {result['generated_records']} synthetic records for table '{result['table_name']}' "
                f"with {result['field_count']} configured fields using {result['reference_example_count']} sanitized reference examples."
            )
        return Message(text=text)

    async def build_prompt_preview(self) -> Message:
        result = await self._result()
        return Message(text=result["prompt_preview"])
