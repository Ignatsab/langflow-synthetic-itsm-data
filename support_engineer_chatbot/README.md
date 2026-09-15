# L1/L2 Incident Resolution Chatbot

This directory contains a separate, importable Langflow chatbot built from the same support-tier and safe-resolution policy as the evaluation workflows in the parent project.

## What it does

- Accepts questions and incident descriptions through Langflow's Playground chat.
- Retrieves relevant prior resolutions from uploaded CSV/JSON exports, Markdown/text KB files, or a connected DataFrame.
- Optionally searches Confluence at question time using credentials entered in the component.
- Sends the question, recent conversation, and retrieved evidence to any OpenAI-compatible chat endpoint.
- Requires source citations and recommends escalation when evidence is missing or the work is destructive, security-sensitive, approval-gated, or L3.
- Never updates or closes a ticket and never writes to Confluence.

The local retriever is dependency-free BM25-style lexical retrieval. It works offline and does not send the entire knowledge base to the model: only the top matching chunks are included. This is a practical first RAG implementation; an embedding/vector-store retriever can later replace it without changing the chat contract.

## Import and run

1. In Langflow, import `l1_l2_incident_resolution_chatbot.json` from this directory.
2. Open **L1/L2 Incident Resolution Chatbot**.
3. Upload one or more approved incident/KB files under **Incident and KB Files**. The included `sample_incident_resolutions.json` is safe demo data.
4. Leave **Dry Run** on and ask a question in the Playground. The response lists the sources retrieval selected without calling a model.
5. Enter the OpenAI-compatible base URL, API key, and model, then disable **Dry Run**.
6. Ask a question such as: `VPN disconnects five minutes after connecting. What should I check and how do I verify the fix?`

CSV/JSON incident exports work best when they include fields such as `number`, `short_description`, `description`, `support_level`, `technology`, `resolution_notes`, `verification`, and `assignment_group`. Unknown columns are still retained as searchable context.

## Confluence setup

Confluence is optional and read-only.

For Confluence Cloud:

1. Enable **Search Confluence**.
2. Set the site URL to `https://your-company.atlassian.net` or `https://your-company.atlassian.net/wiki`.
3. Select **Cloud email + API token**.
4. Enter the Atlassian account email and an API token in the secret token field.
5. Optionally enter a space key to limit search scope.

For a Confluence deployment that accepts personal access tokens, select **Bearer token** and enter the PAT. The component calls the read-only content-search REST endpoint and adds matching pages as cited sources. Credentials are used only in the request Authorization header and are not placed in prompts, outputs, or source tables.

Use a least-privilege account that can read only the intended support spaces. Because retrieved pages are sent to the configured model endpoint, confirm that this data path complies with your organization's policies.

## Rebuild and validate

From the parent project directory:

```bash
.venv/bin/python support_engineer_chatbot/build_chatbot_flow.py \
  support_engineer_chatbot/incident_resolution_chatbot_component.py \
  support_engineer_chatbot/l1_l2_incident_resolution_chatbot.json

.venv/bin/python support_engineer_chatbot/tests/test_chatbot.py
```

The flow stores chat messages through the standard Chat Input/Output nodes. The assistant reads a bounded number of recent messages for follow-up questions when Langflow runtime history is available.
