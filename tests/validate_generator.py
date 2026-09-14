import asyncio
import copy
import json
import sys
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def main() -> None:
    code = Path(sys.argv[1]).read_text(encoding="utf-8")
    template, generator = build_custom_component_template(Component(_code=code))

    assert template["template"]["schema_preset"]["options"] == [
        "Incident",
        "Change Request",
        "Service Request",
        "Custom",
    ]
    assert template["template"]["schema_preset"]["value"] == "Incident"
    assert template["template"]["table_name"]["advanced"] is False
    assert template["template"]["field_definitions"]["advanced"] is False
    assert template["template"]["test_goal"]["advanced"] is False
    assert template["template"]["dataset_context"]["advanced"] is False
    assert template["template"]["scenario_guidance"]["advanced"] is False
    assert template["template"]["batch_size"]["value"] == 10
    assert template["template"]["maintain_continuity"]["value"] is True
    assert template["template"]["model_name"]["value"] == "gpt-oss-120b"
    assert template["template"]["base_url"]["load_from_db"] is False
    assert template["template"]["api_key"]["load_from_db"] is False
    assert template["template"]["model_name"]["load_from_db"] is False

    change_config = generator.update_build_config(
        copy.deepcopy(template["template"]), "Change Request", "schema_preset"
    )
    assert change_config["table_name"]["value"] == "change_request"
    assert "CHG0012345" in change_config["field_definitions"]["value"]
    assert "change-management" in change_config["test_goal"]["value"]
    assert "implementation teams" in change_config["dataset_context"]["value"]
    assert "emergency changes" in change_config["scenario_guidance"]["value"]

    expected = {
        "Incident": ("incident", "INC"),
        "Change Request": ("change_request", "CHG"),
        "Service Request": ("sc_request", "REQ"),
    }
    generator.record_count = 3
    generator.batch_size = 2
    generator.max_reference_examples = 20
    generator.reference_examples = "[]"
    generator.example_group_field = "assignment_group"
    generator.redact_reference_fields = "email"
    generator.compact_prompt = True
    generator.dry_run = True
    for selection, (table_name, number_prefix) in expected.items():
        generator.schema_preset = selection
        selected_table, schema_text = generator._table_config()
        fields = generator._parse_fields()
        assert selected_table == table_name
        assert number_prefix in schema_text
        assert len(fields) >= 20
        result = asyncio.run(generator._generate())
        assert result["table_name"] == table_name
        assert result["schema_preset"] == selection
        assert result["requested_records"] == 3

    generator.schema_preset = "Custom"
    generator.table_name = "products"
    generator.field_definitions = json.dumps(
        [{"name": "sku", "type": "string", "description": "Unique product identifier."}]
    )
    assert generator._table_config()[0] == "products"
    assert generator._parse_fields()[0]["name"] == "sku"

    generator.schema_preset = "Incident"
    generator.dry_run = False
    generator.base_url = "http://example.invalid/v1"
    generator.api_key = "test-key"
    generator.model_name = "gpt-oss-120b"
    generator.record_count = 25
    generator.batch_size = 10
    generator.maintain_continuity = True
    generator.continuity_sample_size = 3
    generator.max_concurrency = 2
    calls = []

    async def fake_request_batch(client, fields, examples, count, batch_number, model, continuity_profile=None):
        calls.append((count, batch_number, continuity_profile or {}))
        start = sum(item[0] for item in calls[:-1])
        return [
            {
                "number": f"INC{start + index + 1:07d}",
                "category": "Network" if (start + index) % 2 == 0 else "Access",
                "state": "New",
                "assignment_group": "Network Support" if (start + index) % 2 == 0 else "Service Desk",
                "_test_scenario": "common",
            }
            for index in range(count)
        ]

    generator._request_batch = fake_request_batch
    result = asyncio.run(generator._generate())
    assert result["generated_records"] == 25
    assert [call[0] for call in calls] == [10, 10, 5]
    assert calls[0][2] == {}
    assert calls[1][2]["generated_so_far"] == 10
    assert calls[2][2]["generated_so_far"] == 20
    assert result["continuity_profile"]["generated_so_far"] == 25
    assert result["continuity_profile"]["latest_record_number"] == "INC0000025"

    print("Generator validation passed")


if __name__ == "__main__":
    main()
