# Synthetic ITSM Dataset Generator for Langflow

`servicenow_synthetic_dataset_generator.json` is an importable Langflow flow for producing fictional, schema-driven test datasets with an OpenAI-compatible LLM.

`know_your_bau_flow.json` is a complete evaluation pipeline that generates labeled tickets, builds a label-free holdout, classifies and routes the tickets, and scores the predictions against hidden ground truth.

`servicenow_support_tier_comparison_flow.json` is the recommended support-tier experiment suite. It uses one generated holdout and three built-in **Batch Run** classifier branches so prompt approaches and models can be compared on exactly the same incidents. Standalone zero-shot, rubric, and few-shot versions are also included.

`servicenow_support_tier_model_comparison_flow.json` keeps the rubric and data identical across three branches, isolating model choice as the experimental variable.

`support_engineer_chatbot/l1_l2_incident_resolution_chatbot.json` is a separate conversational assistant for solution engineers. It retrieves similar historical resolutions and KB content, can search Confluence with operator-supplied credentials, and returns cited L1/L2 troubleshooting and verification guidance in the Langflow Playground. See `support_engineer_chatbot/README.md` for setup.

## Import and configure

1. In Langflow, open a project and choose **Upload flow** (or **Import**), then select `servicenow_synthetic_dataset_generator.json`.
2. Open the **Synthetic ITSM Dataset Generator** component.
3. Choose **Incident**, **Change Request**, or **Service Request** from **Record Type**. Incident is selected by default, and each option uses its own internal schema.
4. Leave **Dry Run** enabled and run once. Inspect **Generation Summary** and **Prompt Preview**.
5. Enter the LLM proxy **Base URL** and **API Key** if they are not configured in the server environment. The model defaults to `gpt-oss-120b` but remains editable.
6. Disable **Dry Run**, choose the total record count, and keep **Records per Generation Call** at `5` for a smaller-context model. The component loops until it reaches the total.
7. Use **Dataset (DataFrame)** for tabular downstream processing or **Dataset (JSON)** for agent/evaluation flows.

The predefined field JSON, descriptions, test goal, dataset context, scenario mix, and reference examples remain visible. Changing **Record Type** refreshes the displayed table name and field JSON. Built-in generation uses the protected matching schema; choose **Custom** when you want edits to the table name or fields to take effect.

No extra Langflow package is required. The component uses `openai` and `pandas`, which are already included in the tested Langflow 1.11.5 installation.

When the connection fields are blank, the component reads `OPENAI_COMPATIBLE_BASE_URL` and `OPENAI_COMPATIBLE_API_KEY` from the Langflow server environment. It does not use Langflow's global-variable selector.

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

The support convention is: **L1** is routine/lowest-complexity support, **L2** is specialist/intermediate support, and **L3** is the highest-complexity senior solution-engineering tier. Support tier is based on the expertise needed to resolve an incident, not its business impact or urgency.

Classification and resolution happen in one model call. For a safely resolvable L1 or L2 incident, the model returns concrete `proposed_solution` and `verification` steps with `resolution_action=STOP_WITH_SOLUTION`. It returns `ESCALATE` when evidence is insufficient or the action is destructive, security-sensitive, or requires approval. L3 auto-resolution is off by default: each classifier prompt contains `L3_AUTO_RESOLUTION=false`. Change that policy line to `true` only for a bounded L3 experiment; the flow itself does not update or close ServiceNow records.

## Support-tier model and prompt comparison

Import `servicenow_support_tier_comparison_flow.json` for the fairest experiment. Its three branches use Langflow's default **Batch Run** component:

1. **Zero-shot** states the tier convention with minimal guidance.
2. **Rubric-based** supplies explicit resolution-complexity indicators and instructs the model not to confuse severity with complexity.
3. **Few-shot** supplies examples, including high-impact/known-fix and low-impact/engineering cases that test that distinction.

The generator starts in Dry Run. Configure its OpenAI-compatible endpoint, generate the labeled incidents, and keep the Holdout Dataset Builder between the generator and every classifier. In each Batch Run branch, choose any available model provider. Use the same model in all three branches to compare prompts, or different models with the same prompt in the standalone flows to compare models.

The importable comparison flows are configured for **100 generated records** and a **30-ticket evaluation holdout**. For the very first endpoint check, temporarily set **Number of Records** to `10`; after that succeeds, restore it to `100` or increase it further. Keep **Records per Generation Call** at `5` (or reduce it to `3` for a particularly small-context model).

### Run the complete experiment and resume safely

After configuring the generator and the three Batch Run model selectors, run only the final **Run Complete Experiment** component. Because it depends on every dashboard and checkpoint receipt, Langflow executes the complete upstream graph automatically. The three classifier branches are chained in sequence and each classifier defaults to **Max Concurrent Requests = 1**, which is deliberately conservative for a local endpoint.

The comparison flows contain eight default **Write File** checkpoints: generated data, visible holdout data, predictions and scored results for each of the three branches. They overwrite their named JSON snapshot on a successful run and the final component lists every saved path alongside all three dashboards.

There are also automatic resume checkpoints inside the expensive components:

- The generator saves after every successful generation chunk. A rerun with the same generator configuration and **Dataset Checkpoint Name** resumes from those records.
- Each Batch Run saves completed predictions. A rerun reuses them only when the incident table, prompt, selected model, and relevant settings match.
- Change a checkpoint name or disable **Reuse Matching ... Checkpoint** when you intentionally want a fresh run.
- Changing the source fields, prompt, model, or other fingerprinted settings invalidates the matching cache automatically. Existing human-readable Write File snapshots remain available as backups.
- Internal recovery checkpoints default to the runtime's writable temporary directory. If checkpoint storage is unavailable, generation/classification continues and reports a warning instead of failing the successful model work.

If a later branch fails, fix its endpoint/model setting and run **Run Complete Experiment** again. Completed generation and classifier branches are read from matching checkpoints, while the failed or changed branch is recomputed.

For a direct model benchmark, import `servicenow_support_tier_model_comparison_flow.json` and select a different model in Model A, B, and C. All three branches use the exact same rubric, visible fields, and holdout rows, avoiding prompt/data confounding.

Customize **Fields Sent to BAU Agent** on the shared Holdout Dataset Builder. This is a comma-separated allow-list; the ticket ID is always retained and all `_expected_*` labels are always removed. The default uses `number,short_description,description,state,impact,urgency,priority,business_service`. Because Batch Run's **Column Name** is intentionally blank, it serializes all retained fields for each ticket.

Each model returns one compact JSON object per row with `support_level`, `confidence`, `resolution_action`, `proposed_solution`, `verification`, and `reason`. The evaluator parses the built-in Batch Run `model_response` column, scores `support_level` against `_expected_support_level`, preserves the resolution decision for inspection, and the dashboard shows accuracy, scenario breakdowns, tier confusion, and failed tickets.

For statistically useful comparisons, keep the generated dataset fixed, use the same holdout seed and fields, run each configuration multiple times, and record at least support-level accuracy, macro F1, per-tier recall, invalid-response rate, latency, and cost. The included deterministic evaluator reports exact accuracy and confusion-ready rows; export those rows if you want confidence intervals or cost/latency analysis in a notebook.

The comparison flow's Holdout Dataset Builder uses 30 randomly selected tickets with a fixed seed. It removes `category`, `subcategory`, `assignment_group`, and all `_expected_*` columns, preventing ground-truth leakage. Add other answer-bearing fields to **Additional Fields to Hide** when you customize the schema. The evaluator independently receives the original generated dataset and keeps only rows whose ticket IDs occur in the agent predictions.

Use **Fields Sent to BAU Agent** as a prompt-size allow-list. The default sends only the ticket number, short and full descriptions, state, impact, urgency, priority, and business service. Add another visible field only when the classifier needs it.

The evaluator performs normalized exact matching. Arrays such as required skills are compared without regard to order or capitalization. Free-text fields such as agent action are therefore intentionally strict; use categorical action labels in the ground truth when you need stable automated scores.

The dashboard preserves `_test_scenario`, `state`, and `priority` from hidden ground truth for aggregate breakdowns; these values are never passed to the classification agent. Change **Scenario Breakdown Field** to analyze another preserved field. Change **Confusion Matrix Field** to inspect routing substitutions for `assignment_group`, `category`, `support_level`, or another scored label.

## Performance tuning

The generator defaults to 5 records per call and loops until **Number of Records** is reached. A 100-record dataset therefore uses 20 successful small generation calls rather than one large prompt. With **Keep Dataset Connected Across Calls** enabled, calls run sequentially and each new call receives only a bounded continuity profile containing earlier distributions, two recent record summaries, and the latest identifier. The full growing dataset is never sent back to the model.

Five is a per-request chunk size, not a dataset limit. Each call receives at most three rotating reference examples and requests at most 4,096 output tokens. A length-limited or malformed response is split immediately and recursively until its smaller chunks fit; transient network failures are retried without creating a request explosion. Up to 20 recovery batches can fill missing or duplicate records. Concurrent Langflow outputs share one in-flight generation job, so connecting the DataFrame, JSON, summary, and profile outputs does not duplicate the model workload. The support-tier comparison flows also cap the built-in Batch Run classifier at **Max Concurrent Requests = 1** with three request attempts.

The **Dataset (JSON)** output includes `generation_diagnostics`. Each successful endpoint response records the requested row count, returned row count, finish reason, and completion-token count when the proxy supplies it. Repeated `finish_reason: "length"` means the per-call output is too large; lower **Records per Generation Call** or raise **Maximum Output Tokens per Call** if the endpoint supports it. If calls finish normally but return fewer rows, inspect duplicate rates and simplify long text fields. If no response diagnostic appears, investigate endpoint availability, authentication, proxy logs, and outer Langflow or gateway timeouts.

- Keep continuity enabled when relationships and stable categories/groups matter. Disable it when maximum generation speed matters more than cross-batch consistency.
- **Concurrent LLM Calls** is used only when continuity is disabled; try `2` to `4` only after checking server capacity.
- If the proxy serializes requests or runs close to its memory limit, set concurrency to `1`.
- Increase **Records per Generation Call** only after a stable 100-row run; reduce it from `5` to `3` if responses truncate or contain malformed JSON.
- Generate only the fields needed for the test. Long descriptions and many output columns dominate generation time.
- For quick iterations, generate 10-20 source tickets and set the holdout sample to 5. Scale up only for final evaluation.
- For 100-500 source tickets, keep **Records per Generation Call** at `3` or `5`, **Keep Dataset Connected Across Calls** enabled, and **Concurrent LLM Calls** at `1`. Set **Tickets to Test** independently; generating 500 tickets does not require classifying all 500 in one experiment.
- After a stable run, increase **Max Concurrent Requests** on each Batch Run classifier from `1` to `2` only if the endpoint has spare capacity.
- The classification agent also batches tickets and supports concurrent calls independently.
- For a slow local classifier, start with **Tickets per LLM Call = 1-3** and **Concurrent LLM Calls = 1**. The defaults are 5 and 1.
- **Request Timeout** defaults to 600 seconds per classifier call. A timeout is not automatically repeated as a JSON-mode fallback.
- If the model omits ticket IDs but returns the correct number of ordered predictions, the classifier safely restores IDs by batch position. Missing predictions are retried individually and produce a specific error instead of the misleading `BAU Predictions is empty` message.

## Save or load the generated dataset

The standalone flow includes a connected **Write File** component. Set its file name and choose `json` or `csv`, then run that component to save the generator's DataFrame through Langflow's managed file storage.

For a database, connect **Dataset (DataFrame)** to the database-writer component once its interface is defined. The same output contains the complete dataset accumulated across every generation call; the generator does not emit isolated batches downstream.

## Built-in and custom schemas

The ServiceNow data source includes these ready-to-use schemas:

- **Incident** (`incident`)
- **Change Request** (`change_request`)
- **Service Request** (`sc_request`)

The selected table name and field JSON remain visible in the normal component view. Choose **Custom** from **Record Type** when edits to those two inputs should control generation. When a predefined record type is selected, the protected matching schema is used, so visible JSON cannot accidentally turn a Change Request run into Incident data.

### Custom Field Definitions format

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

Add fields beginning with `_expected_` to store ground truth used to score a downstream AI agent.

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
- `servicenow_support_tier_comparison_flow.json`: shared-holdout comparison of zero-shot, rubric, and few-shot Batch Run classifiers
- `servicenow_support_tier_model_comparison_flow.json`: shared-holdout comparison of three models using an identical rubric
- `servicenow_support_tier_zero_shot_flow.json`: standalone zero-shot classifier experiment
- `servicenow_support_tier_rubric_flow.json`: standalone rubric-based classifier experiment
- `servicenow_support_tier_few_shot_flow.json`: standalone few-shot classifier experiment
- `synthetic_dataset_generator_component.py`: editable component source
- `holdout_dataset_builder_component.py`: limits the test set and hides labels
- `know_your_bau_agent_component.py`: OpenAI-compatible BAU classification agent
- `bau_evaluator_component.py`: deterministic ground-truth comparison and metrics
- `bau_evaluation_dashboard_component.py`: visual scorecard, scenario breakdowns, confusion data, and failure tables
- `build_langflow_artifact.py`: rebuilds the portable JSON inside a compatible Langflow Python environment
- `build_know_your_bau_flow.py`: assembles the four-node flow
- `build_support_tier_experiments.py`: assembles the default Batch Run comparison and standalone flows
- `tests/validate_know_your_bau.py`: validates masking, dry-run classification, and scoring in the Langflow runtime
- `tests/validate_support_tier_flows.py`: validates graph wiring, tier semantics, auto-resolution policy, field masking, and evaluation configuration
