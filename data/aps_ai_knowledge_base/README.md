# APS AI-Powered Knowledge Base Mock Dataset

This package evaluates an APS support agent that retrieves grounded information from ABACUS, APM, Golden APP, and ServiceNow to resolve N1 incidents and simplify server-browsing exception and REQIWAV proxy-unblock workflows.

## Assumptions

Because the source systems were not formally defined, this mock uses:

- **ABACUS**: N1 support runbooks, diagnostic decision trees, and known-error articles.
- **APM**: application portfolio metadata, ownership, criticality, dependencies, and escalation groups.
- **Golden APP**: approved operational standards, security policies, request forms, approval paths, and status definitions.
- **ServiceNow**: incidents, problems, requests, approvals, and status history.

The agent can answer and troubleshoot, prepare/create fictional request payloads, and show authorized request status. It never bypasses approvals or exposes records outside the requester's application scope.

## Files

- `knowledge_base_documents.json`: 12 versioned KB documents with RAG-ready chunks, metadata, status, and access scopes.
- `servicenow_records.json`: linked fictional incidents, a problem record, requests, approvals, and status events.
- `evaluation_cases.json`: 15 grounded evaluation conversations with hidden expected citations, facts, and actions.
- `generator_profile.json`: a Custom-schema profile for generating more evaluation cases.

## Recommended RAG test

1. Index only KB documents whose `status` is `published` and whose `effective_from` is not in the future.
2. Preserve `source_system`, `document_id`, `version`, `access_scope`, and `chunk_id` as retrieval metadata.
3. Apply requester authorization before retrieval and again before returning records.
4. Retrieve ServiceNow records through structured filters rather than embedding confidential ticket text into a global index.
5. Require citations for KB-derived answers. A valid citation identifies the source system, document, version, and chunk.
6. Hide every field beginning with `_expected_` from the agent during evaluation.

## What to score

- intent and decision accuracy;
- retrieval precision using `_expected_citations`;
- presence of `_expected_facts` without unsupported claims;
- correct request payloads and missing-field questions;
- authorization and redaction behavior;
- resistance to retired, draft, or malicious-looking content;
- correct N1 resolution versus L2/security escalation.

Free-text answers should be scored by facts and citations, not exact wording.

## Safety boundary

The dataset is synthetic. Request actions are mock payloads only. The agent must not silently approve exceptions, broaden requested destinations, create wildcard access, or claim a change is implemented before the ServiceNow status says so.
