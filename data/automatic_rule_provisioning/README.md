# Automatic Rule Provisioning Mock Dataset

This dataset tests an agent that reacts when a server is added to an application pool and decides whether to create matching Illumio and perimeter/internal-firewall policy.

## Files

- `provisioning_test_cases.json` contains 12 self-contained test cases. Input fields are visible to the agent; fields beginning with `_expected_` are hidden ground truth.
- `generator_profile.json` contains a Custom-schema configuration that can be copied into the Synthetic ITSM Dataset Generator to create a larger dataset with the same semantics.

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
