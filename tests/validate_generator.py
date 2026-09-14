import asyncio
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
    assert template["template"]["table_name"]["advanced"] is True
    assert template["template"]["field_definitions"]["advanced"] is True
    assert template["template"]["model_name"]["value"] == "gpt-oss-120b"
    assert template["template"]["base_url"]["load_from_db"] is False
    assert template["template"]["api_key"]["load_from_db"] is False
    assert template["template"]["model_name"]["load_from_db"] is False

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

    print("Generator validation passed")


if __name__ == "__main__":
    main()
