# AutoSys SOD Status and Delivery ETA Mock Dataset

This package supports an agent or prediction model that monitors regional start-of-day (SOD) report jobs, estimates report delivery times, identifies the critical or blocking CMD job, and generates regional and global status emails.

## Files

- `autosys_job_dependencies.json`: static BOX/CMD definitions, dependency DAGs, schedules, and SLAs.
- `autosys_current_sod_snapshot.json`: five daily BOX/CMD status snapshots used for live ETA calculation and status-email generation.
- `autosys_execution_history.json`: historical CMD executions and derived BOX outcomes for model training and ETA backtesting.
- `generate_mock_data.py`: deterministic generator for all three JSON datasets. It uses only the Python standard library and seed `20260921`.

## Execution model

- A `CMD` job runs a script and has its own start, end, duration, exit code, retry count, and status.
- A `BOX` job runs no script. It is a logical collection of CMD jobs and has `command: null`.
- A CMD becomes eligible only after every dependency with condition `SUCCESS` succeeds.
- Eligible jobs without dependencies between them can run in parallel.
- The regional report is delivered when `CMD_<REGION>_PUBLISH_REPORT` succeeds.
- The BOX completes later, after both terminal jobs—archive and status notification—succeed.
- BOX duration follows the longest effective dependency path. Never estimate it by summing every child duration.

## Dataset 1: `autosys_job_dependencies.json`

This file is one JSON object with three top-level fields.

| Field | Type | Description |
|---|---|---|
| `metadata` | object | Dataset identity and the BOX, delivery, and dependency semantics. |
| `calendars` | array of objects | Run calendars and regional exclusions. |
| `jobs` | array of objects | All BOX and CMD definitions for APAC, EMEA, and AMER. |

### `metadata`

- `dataset_name` and `generated_at` identify the fixture.
- `timezone_for_schedules` defines the time basis.
- `box_semantics`, `delivery_semantics`, and `dependency_semantics` explain how the DAG must be interpreted.

### `calendars`

Each calendar contains `calendar_name`, `included_weekdays`, `regional_holidays_by_region`, and `run_on_regional_holidays`. The mock process still runs on a regional holiday, but the holiday flag changes expected data volume and is available as a model feature.

### `jobs`

Fields common to BOX and CMD records:

| Field | Description |
|---|---|
| `job_name` | Globally unique AutoSys-style name. |
| `job_type` | `BOX` or `CMD`. |
| `description` | Business purpose of the job. |
| `region` | `APAC`, `EMEA`, or `AMER`. |
| `dependencies` | Array of predecessor `job_name` and required `condition`. |
| `command` | Script invocation for CMD; always null for BOX. |
| `owner_group` | Regional operational owner. |

BOX-only fields:

- `timezone`, `run_calendar`, and `scheduled_time_utc` define when the regional process starts.
- `delivery_sla_minutes` is the allowed time from schedule to report publication.
- `delivery_milestone_job` names the publish CMD used for delivery ETA.
- `child_jobs` lists every CMD contained by the BOX.

CMD-only fields:

- `box_name` identifies the containing BOX.
- `base_duration_minutes` is a generator baseline, not an actual or predicted duration.
- `volume_sensitive` indicates whether input volume should be a model feature.
- `delivery_milestone` marks the report-publication CMD.
- `terminal_for_box` marks jobs that must succeed before the BOX can complete.

## Dataset 2: `autosys_current_sod_snapshot.json`

This standalone file contains five independent point-in-time scheduler snapshots for `2026-09-21` through `2026-09-25`. Keeping status data separate from the static dependency catalog lets participants select, update, or replace a daily state without modifying the job definitions. The scenarios cover a delayed extract, running enrichment, running report build, failed validation with blocked downstream jobs, and successful recovery.

Top-level fields:

| Field | Type | Description |
|---|---|---|
| `metadata` | object | Dataset identity, date range, snapshot count, UTC time basis, and snapshot semantics. |
| `snapshots` | array of objects | Five independent daily SOD status snapshots. |

Each object in `snapshots` contains:

| Field | Description |
|---|---|
| `business_date` | SOD processing date. |
| `as_of` | Timestamp at which the snapshot was captured. |
| `scenario_id` | Short machine-readable label for the operational scenario. |
| `scenario_description` | Human-readable explanation of the scenario. |
| `job_states` | Current state of all BOX and CMD jobs. |
| `email_recipients` | Fictional regional and global distribution lists. |
| `status_email_requirements` | Required facts and safety rules for generated status emails. |

Each `job_states` record contains `job_name`, `job_type`, `region`, `status`, `actual_start`, `actual_end`, `elapsed_seconds`, and `latest_status_message`. Possible live states are `NOT_STARTED`, `WAITING`, `RUNNING`, `SUCCESS`, `FAILED`, or `BLOCKED`.

### Included daily scenarios

| Business date | Scenario ID | EMEA state represented |
|---|---|---|
| `2026-09-21` | `extract_delayed` | Transaction extraction is still running and downstream work is waiting. |
| `2026-09-22` | `enrichment_running` | Extracts and validation succeeded; data enrichment is running. |
| `2026-09-23` | `report_build_running` | Report construction is running while publication waits. |
| `2026-09-24` | `validation_failed` | Validation failed and five downstream CMD jobs are blocked. |
| `2026-09-25` | `recovery_complete` | The prior issue is resolved and the regional BOX completed successfully. |

## Dataset 3: `autosys_execution_history.json`

This file contains `metadata`, `command_runs`, and `box_runs`.

### Historical `metadata`

The metadata records the random seed, history date range, UTC time basis, training targets, recommended P50/P90 prediction intervals, train/evaluation split policy, and the BOX-duration rule.

### `command_runs`

Each record is one historical CMD execution:

| Field | Description |
|---|---|
| `run_id` | Unique CMD execution identifier. |
| `region_run_id` | Joins the CMD to its regional BOX run. |
| `business_date`, `weekday` | Processing date and derived weekday feature. |
| `dataset_split` | `train` or `evaluation` for backtesting. |
| `region`, `box_name`, `job_name`, `job_type` | Job identity and hierarchy. |
| `status` | `SUCCESS`, `FAILED`, or `BLOCKED`. |
| `scheduled_box_start` | Regional BOX schedule used as the ETA origin. |
| `eligible_at` | Time at which predecessor conditions were satisfied. |
| `actual_start`, `actual_end` | Observed execution timestamps. |
| `duration_seconds` | CMD runtime target; null for blocked jobs. |
| `queue_wait_seconds` | Delay between eligibility and actual start. |
| `dependency_wait_seconds` | Time from BOX schedule until this CMD became eligible. |
| `retry_count`, `exit_code`, `failure_category` | Reliability and failure features. |
| `blocked_by` | Failed predecessor jobs for a blocked CMD. |
| `predecessor_jobs` | Direct dependency names. |
| `input_record_count` | Regional volume feature shared by the run. |
| `is_regional_holiday` | Calendar feature that affects volume and duration. |

### `box_runs`

Each record is a derived regional BOX outcome:

| Field | Description |
|---|---|
| `region_run_id`, `business_date`, `weekday`, `dataset_split`, `region`, `box_name`, `job_type` | BOX identity and calendar feature. |
| `status` | `SUCCESS` only when both terminal CMD jobs succeeded; otherwise `FAILED`. |
| `scheduled_start`, `actual_start`, `actual_end` | BOX timing. |
| `delivery_milestone_job`, `delivery_at` | CMD and timestamp representing report availability. |
| `delivery_duration_seconds` | Primary report-delivery ETA target, measured from scheduled start. |
| `delivery_sla_at`, `delivery_sla_met` | Delivery deadline and outcome. |
| `box_duration_seconds` | Time until the entire BOX completed or stopped. |
| `critical_path_jobs` | Ordered CMD path that determined BOX completion time. |
| `input_record_count`, `is_regional_holiday` | Business-volume and calendar features. |
| `successful_cmd_count`, `failed_cmd_count`, `blocked_cmd_count` | Child outcome totals. |
| `total_retry_count` | Retries across all child CMD jobs. |

## Modeling recommendations

- Train CMD-duration models on successful `command_runs`; model failure probability separately using all non-blocked runs.
- Predict each remaining CMD with P50 and P90 durations, then propagate those estimates through the DAG from the live snapshot.
- For a running CMD, condition the remaining-time estimate on `elapsed_seconds`; do not restart its prediction from zero.
- Use `input_record_count`, region, weekday, holiday, retries, queue wait, and recent rolling durations as features.
- Backtest only on `dataset_split: evaluation` and train only on `dataset_split: train` to avoid leakage.
- Report both delivery ETA and full BOX completion ETA because publishing occurs before archive and notification finish.
- A status email should state actual times for completed regions and P50/P90 estimates plus the blocking/critical CMD for incomplete regions.

## Safety and data notes

All names, commands, recipients, schedules, failures, and timings are synthetic. The script paths are non-functional examples. This dataset must not be connected to a production AutoSys scheduler or mailing system.
