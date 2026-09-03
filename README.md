# Synthetic ITSM Dataset Generator for Langflow

`servicenow_synthetic_dataset_generator.json` is an importable Langflow flow for producing fictional, schema-driven test datasets with an OpenAI-compatible LLM.

`know_your_bau_flow.json` is a complete evaluation pipeline that generates labeled tickets, builds a label-free holdout, classifies and routes the tickets, and scores the predictions against hidden ground truth.

## Import and configure

1. In Langflow, open a project and choose **Upload flow** (or **Import**), then select `servicenow_synthetic_dataset_generator.json`.
2. Open the **Synthetic ITSM Dataset Generator** component.
3. Leave **Dry Run** enabled and run once. Inspect **Generation Summary** and **Prompt Preview**.
4. Enter the LLM proxy **Base URL**, **API Key**, and **Model Name**.
5. Disable **Dry Run**, set the table, fields, record count, test goal, context, and scenario mix, then run the component.
6. Use **Dataset (DataFrame)** for tabular downstream processing or **Dataset (JSON)** for agent/evaluation flows.

No extra Langflow package is required. The component uses `openai` and `pandas`, which are already included in the tested Langflow 1.11.5 installation.

## Know Your BAU evaluation flow

Import `know_your_bau_flow.json`. It contains five connected components:

1. **Synthetic ITSM Dataset Generator** creates fictional tickets and `_expected_*` ground-truth labels.
2. **BAU Holdout Dataset Builder** takes only the configured sample size and removes category, assignment group, and every `_expected_*` field before the agent sees the tickets.
3. **Know Your BAU Classification Agent** predicts:
   - category
   - ticket type
   - required skills
   - technology
   - support level (`L1`, `L2`, or `L3`)
   - assignment group
   - recommended agent action
4. **Know Your BAU Evaluator** receives the full generated dataset as hidden truth, restricts it to ticket IDs actually sent to the agent, and reports prediction coverage, all-fields exact match, and per-field accuracy.
5. **Know Your BAU Evaluation Dashboard** renders an easy-to-read Markdown scorecard and provides separate tables for field performance, scenario performance, routing confusion, and failed tickets.

Both LLM-powered components start in **Dry Run** mode. Enter the same OpenAI-compatible Base URL, API key, and model name in the generator and classification agent. Test each prompt preview, then disable Dry Run on both components.

The Holdout Dataset Builder defaults to 10 randomly selected tickets with a fixed seed. It removes `category`, `subcategory`, `assignment_group`, and all `_expected_*` columns, preventing ground-truth leakage. Add other answer-bearing fields to **Additional Fields to Hide** when you customize the schema. The evaluator independently receives the original generated dataset and keeps only rows whose ticket IDs occur in the agent predictions.

Use **Fields Sent to BAU Agent** as a prompt-size allow-list. The default sends only the ticket number, short and full descriptions, state, impact, urgency, priority, and business service. Add another visible field only when the classifier needs it.

The evaluator performs normalized exact matching. Arrays such as required skills are compared without regard to order or capitalization. Free-text fields such as agent action are therefore intentionally strict; use categorical action labels in the ground truth when you need stable automated scores.

The dashboard preserves `_test_scenario`, `state`, and `priority` from hidden ground truth for aggregate breakdowns; these values are never passed to the classification agent. Change **Scenario Breakdown Field** to analyze another preserved field. Change **Confusion Matrix Field** to inspect routing substitutions for `assignment_group`, `category`, `support_level`, or another scored label.

## Performance tuning

The optimized generator defaults to 25 records per call and two concurrent calls, so a 50-record dataset can be generated in two parallel batches instead of three sequential batches. It also sends compact schema and example JSON to reduce repeated input tokens.

- If the proxy/model can process simultaneous requests, keep **Concurrent LLM Calls** at `2`; try `3` or `4` only after checking server capacity.
- If the proxy serializes requests or runs close to its memory limit, set concurrency to `1`.
- Increase **Records per LLM Call** to reduce prompt repetition, but ensure the model has enough context/output-token capacity.
- Generate only the fields needed for the test. Long descriptions and many output columns dominate generation time.
- For quick iterations, generate 10-20 source tickets and set the holdout sample to 5. Scale up only for final evaluation.
- The classification agent also batches tickets and supports concurrent calls independently.
- For a slow local classifier, start with **Tickets per LLM Call = 1-3** and **Concurrent LLM Calls = 1**. The defaults are 5 and 1.
- **Request Timeout** defaults to 600 seconds per classifier call. A timeout is not automatically repeated as a JSON-mode fallback.
- If the model omits ticket IDs but returns the correct number of ordered predictions, the classifier safely restores IDs by batch position. Missing predictions are retried individually and produce a specific error instead of the misleading `BAU Predictions is empty` message.

## Field Definitions format

Field Definitions must be a JSON array:

```json
[
  {
    "name": "number",
    "type": "string",
    "description": "Unique ServiceNow-style incident number such as INC0012345."
  },
  {
    "name": "priority",
    "type": "integer",
    "description": "Integer 1 through 5, consistent with impact and urgency."
  }
]
```

The imported flow contains a complete Incident example. Edit that JSON for `change_request`, `sc_request`, `sc_req_item`, or any non-ServiceNow table. Add fields beginning with `_expected_` to store ground truth used to score the final AI agent.

## Use examples from real data

Paste a small, representative, pre-approved sample into **Sanitized Reference Examples (JSON)**. It can be a flat array or grouped by the behavior you want to preserve:

```json
{
  "Network Support": [
    {
      "short_description": "VPN disconnects after several minutes",
      "category": "Network",
      "subcategory": "VPN",
      "assignment_group": "Network Support"
    }
  ],
  "Access Management": [
    {
      "short_description": "Cannot access the finance application",
      "category": "Access",
      "subcategory": "Application access",
      "assignment_group": "Access Management"
    }
  ]
}
```

Set **Reference Group Field** to the distinguishing field, normally `assignment_group`, `category`, or `request_type`. The generator uses the examples to imitate vocabulary, distributions, and group-specific correlations without copying complete records. It limits the number of examples and redacts configured fields plus email addresses before building the prompt.

Only provide reference data that is approved for the target LLM environment. Automatic redaction is a safety layer, not a substitute for organizational data-handling rules; remove names and sensitive free text before pasting examples.

## Practical notes

- The generator makes multiple calls in batches, which is safer for local models than asking for hundreds of rows in one response.
- If the proxy does not implement OpenAI JSON mode, the component retries automatically without it.
- A blank API key is sent as `local`; this supports proxies that do not require authentication.
- The component asks for exactly the requested number of distinct valid JSON records and retries when a batch is short or duplicated.
- Synthetic records can contain safe prompt-injection text to test agent robustness, but the system prompt prohibits real people, customer data, credentials, and secrets.
- Reference examples are treated as few-shot pattern guidance and are never used as output records.
- For linked tables, generate the parent table first and paste its fictional identifiers or relationship rules into **Dataset Context and Relationships** for the next table.

## Included files

- `servicenow_synthetic_dataset_generator.json`: portable Langflow flow
- `know_your_bau_flow.json`: complete generation, holdout, classification, and evaluation flow
- `synthetic_dataset_generator_component.py`: editable component source
- `holdout_dataset_builder_component.py`: limits the test set and hides labels
- `know_your_bau_agent_component.py`: OpenAI-compatible BAU classification agent
- `bau_evaluator_component.py`: deterministic ground-truth comparison and metrics
- `bau_evaluation_dashboard_component.py`: visual scorecard, scenario breakdowns, confusion data, and failure tables
- `build_langflow_artifact.py`: rebuilds the portable JSON inside a compatible Langflow Python environment
- `build_know_your_bau_flow.py`: assembles the four-node flow
- `tests/validate_know_your_bau.py`: validates masking, dry-run classification, and scoring in the Langflow runtime
