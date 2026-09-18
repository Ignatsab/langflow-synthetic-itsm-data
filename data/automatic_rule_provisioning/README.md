# Automatic Rule Provisioning Mock Dataset

This dataset tests an agent that reacts when a server is added to an application pool and decides whether to create matching Illumio and perimeter/internal-firewall policy.

## Files

- `provisioning_test_cases.json` contains 12 self-contained test cases. Input fields are visible to the agent; fields beginning with `_expected_` are hidden ground truth.
- `generator_profile.json` contains a Custom-schema configuration that can be copied into the Synthetic ITSM Dataset Generator to create a larger dataset with the same semantics.

## JSON data dictionary

### `provisioning_test_cases.json`

The file is a JSON array. Each object is one independent provisioning event and contains:

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Unique evaluation identifier such as `ARP-001`. |
| `_test_scenario` | string | Scenario grouping: `happy_path`, `idempotent`, `partial_state`, `invalid_input`, `dependency_failure`, `conflict`, or `multi_flow`. Keep for reporting, but it may be hidden if it gives the agent too much guidance. |
| `membership_event` | object | The server-to-pool event that triggered automation. |
| `server` | object | CMDB, network, ownership, and Illumio state for the affected server. |
| `application_pool` | object | Application pool metadata and the labels used to build policy. |
| `approved_connectivity_intents` | array of objects | The only flows that are authorized for provisioning. |
| `existing_state` | object | Relevant Illumio and firewall rules already present before the event. |
| `_expected_decision` | string | Ground-truth provisioning decision. |
| `_expected_actions` | array of strings | Ordered actions the automation should take. |
| `_expected_illumio_rules` | array of objects | Normalized Illumio rules expected to be created. |
| `_expected_firewall_rules` | array of objects | Normalized firewall rules expected to be created. |
| `_expected_reason_code` | string | Stable explanation category used for scoring. |

Nested input fields:

- `membership_event`: `event_id`, `event_type`, `server_id`, `pool_id`, `occurred_at`, `approved_change_id`, and retry-safe `idempotency_key`.
- `server`: `server_id`, `hostname`, `ip_address`, `environment`, `location`, `network_zone`, `owner`, `illumio_workload_id`, `ven_state`, and `cmdb_status`.
- `application_pool`: `pool_id`, `application`, `environment`, `role`, `owner`, `lifecycle_state`, `security_tier`, and `labels`. Labels normally contain `app`, `env`, `role`, and `loc`.
- Each `approved_connectivity_intents` item: `intent_id`, `status`, `direction`, `source`, `destination`, `protocol`, `port`, `source_zone`, `destination_zone`, and `business_purpose`.
- `existing_state`: `illumio_rules` and `firewall_rules`. Existing rules may contain `name`, `equivalent`, `enabled`, `action`, `managed_by`, or `overlaps_requested_flow` depending on the scenario.

Expected rule fields:

- Illumio rule: `name`, `consumers`, `providers`, `services`, `action`, and `enabled`; each service contains `protocol` and `port`.
- Firewall rule: `name`, `source`, `destination`, `services`, `source_zone`, `destination_zone`, `action`, and `log`.

### `generator_profile.json`

| Field | Description |
|---|---|
| `schema_preset` | Uses `Custom` so the supplied schema controls generation. |
| `table_name` | Logical generated-record name. |
| `test_goal` | Behavior the generated dataset is intended to evaluate. |
| `dataset_context` | Cross-field rules, policy assumptions, and idempotency requirements. |
| `scenario_guidance` | Desired scenario distribution and safety constraints. |
| `field_definitions` | Array of generated field names, types, and descriptions. |
| `reference_examples_file` | File containing examples that demonstrate the target structure and decisions. |

## What is modeled

Each case contains:

- the pool-membership event that triggers automation;
- server/CMDB facts, including IP address, environment, zone, and Illumio VEN state;
- application-pool labels used by Illumio;
- approved connectivity intents (the only flows the agent may provision);
- current Illumio and firewall state, so idempotency and partial recovery can be tested;
- hidden expected decision, actions, normalized rules, and reason code.

The mock policy uses these decisions:

- `CREATE_BOTH`: create one or more rules in both platforms;
- `CREATE_ILLUMIO_ONLY` or `CREATE_FIREWALL_ONLY`: repair partial state;
- `NO_CHANGE`: the desired state already exists;
- `BLOCK`: do not provision because policy or required data is invalid;
- `DEFER`: wait for a recoverable prerequisite, such as an offline Illumio VEN;
- `MANUAL_REVIEW`: stop because automatic action could weaken an explicit control.

## Recommended evaluation

Send every field except those beginning with `_expected_` to the agent. Compare its structured response to:

- `_expected_decision` and `_expected_actions` for primary accuracy;
- `_expected_illumio_rules` and `_expected_firewall_rules` after sorting arrays and normalizing case;
- `_expected_reason_code` for failure-path accuracy.

Start with cases `ARP-001` through `ARP-006` for basic behavior, then add the negative and multi-flow cases. Never let the test harness execute these synthetic rules against a real management plane.

## Assumptions to adapt

The rule representation is intentionally vendor-neutral. Replace `consumers`, `providers`, label keys, zones, address groups, and service naming with your organization's approved Illumio PCE and firewall-manager contract. The mock workflow is transaction-oriented: if both systems are required, success means both reach the desired state; retry uses `idempotency_key` and must not create duplicates.
