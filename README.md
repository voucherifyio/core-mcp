# Voucherify MCP

We’re introducing an MCP (Model Context Protocol) server for the Voucherify API. An MCP lets you query and explore your loyalty & promo data in plain language, as if you were asking a teammate to pull the numbers for you.
[Learn more about the MCP Server](https://www.voucherify.io/blog/introducing-the-voucherify-mcp-server)

## Pick your path

- **Use the published package (recommended)**: no local build, your agent just spawns the server.
- **Contribute or run from source**: set up the repo, run locally (HTTP or stdio), and hack away.

---

### Path 1: Use the published package (quickest)

No local setup needed — your agent runs the server with `uvx`.  

#### Agent config (`mcp.json`)

```json
{
  "version": 1,
  "mcpServers": {
    "voucherify-core-mcp": {
      "command": "uvx",
      "args": ["voucherify-core-mcp", "--transport", "stdio"],
      "env": {
        "VOUCHERIFY_APP_ID": "<app id>",
        "VOUCHERIFY_APP_TOKEN": "<app token>",
        "VOUCHERIFY_API_BASE_URL": "https://<clusterId>.api.voucherify.io"
      }
    }
  }
}
```

That’s it. Your agent will start the server on demand over `stdio` and pass the credentials.

Where to place this file?
- **Cursor**: put it in `.cursor/mcp.json` at your repo root.
- **Other tools (Continue, Zed, Claude Desktop, Cline, …)**: check their docs for the exact path.

--- 

### Path 2: Contribute or run from source

If you want to explore the code, tweak things, or run a local HTTP server, this is for you.

#### Prereqs

- **Python 3.12+**
- **Voucherify credentials**: `VOUCHERIFY_APP_ID`, `VOUCHERIFY_APP_TOKEN`
- Install [`uv`](https://docs.astral.sh/uv/)
- Install dependencies:
```sh
uv sync --all-extras
```

#### Configure project credentials

Create a `.env` in the project root (super handy when debugging):

```sh
# Voucherify API Configuration for localhost
VOUCHERIFY_API_BASE_URL=http://localhost:8000
VOUCHERIFY_APP_ID=<app id>
VOUCHERIFY_APP_TOKEN=<app token>

# Tests (Management API keys can be found in Team Settings)
VOUCHERIFY_MANAGEMENT_APP_ID=
VOUCHERIFY_MANAGEMENT_APP_TOKEN=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

When running a local MCP server, you can point to a specific cluster or local env via `.env`:

```sh
VOUCHERIFY_API_BASE_URL=http://localhost:8000
```

#### Run it your way

##### Option A: HTTP server

Start the server:
```sh
uv run python src/voucherify_core_mcp/main.py
```

You’ll get an endpoint at `http://127.0.0.1:10000/mcp/`.
Configure your agent to connect over HTTP:
```json
{
  "mcpServers": {
    "voucherify-remote-mcp": {
      "url": "http://localhost:10000/mcp/",
      "headers": {
        "x-app-id": "your-application-id",
        "x-app-token": "your-secret-key"
      }
    }
  }
}
```

##### Option B: stdio (spawned by your agent)

Let your agent spawn the server from source:
```json
{
  "version": 1,
  "mcpServers": {
    "voucherify-core-mcp-from-sources": {
      "command": "uv",
      "args": ["run", "python", "src/voucherify_core_mcp/main.py", "--transport", "stdio"],
      "env": {
        "VOUCHERIFY_APP_ID": "<app id>",
        "VOUCHERIFY_APP_TOKEN": "<app token>",
        "VOUCHERIFY_API_BASE_URL": "https://api.voucherify.io"
      }
    }
  }
}
```

Place the file where your agent expects it (same locations as above). 

## MCP Test Engine

1) Initialize project data
- Create your `.env` as above
- Run the project preparation script:
```sh
uv run prepare_project.py
```
This will:
- Look into `tests/.test.env` and delete the test project defined there
- Create a new test project using the Management API credentials from `.env`
- Generate required resources
- Persist credentials and resource IDs for tests in `.test.env`

2) Run scenarios
```sh
uv run pytest tests/scenario_1_basic_scenarios.py
```
or a specific test:
```sh
uv run pytest tests/scenario_5_get_best_deals.py::test_get_best_deals_json_output
```

## Best practices

### 1. Be specific in your queries

- Use precise date ranges (e.g., “July 2025 redemptions”) instead of vague prompts like “recent redemptions.”
- Call out exactly what you want: specific campaign names, product categories, or data types.
- Broad requests (e.g., “all campaigns in the last 3 years”) usually lead to messy results.

### 2. Don’t just ask

If results look off, reframe your query or try again. If the AI loops or repeats itself, redirect with a new question or start a fresh chat with a sharper prompt.

### 3. Dig deeper

Once you’ve got an answer you like, ask MCP to:

- Suggest additional insights or next steps.
- Explain how it reached its conclusions (to help refine your future prompts).

### 4. Prioritize by impact

If you’re short on time, ask MCP to sort results by what matters most like biggest revenue lift, quickest win, or highest time savings. This helps cut through information overload.

## Prompt examples

- “Find products where attribute ‘category’ = ‘Burgers’ and price < 20.”
- “Find customer by email tom@example.com (or source_id); return id, loyalty_balance, active_vouchers.”
- “Count total of customers in segment ‘VIP-Warsaw’”
- “List active campaigns with fields id, name, type, start_date, end_date.”
- “Get voucher by code ‘BK-4829’ and show: status, redemption.count, redemption.limit, balance (if gift-card).”
- “Get campaign ‘BK-Sept-20OFF’ counters: total budget, spent budget, redemption counts, and per-customer caps.”
- “Get redemptions aggregated by day for 2025-09-01 → 2025-09-03 (timezone Europe/Warsaw).”
- “Top 10 codes by redemption count in the last 14 days; include redemption.success vs. redemption.failed.”
- “Export redemptions to CSV for 2025-09-01 to 2025-09-03 and provide a download URL.”

## **Disclaimer**

The Model Context Protocol (MCP) is a new open-source standard and may still carry potential vulnerabilities. The Voucherify MCP server setup and instructions are provided “as is,” without warranties, and use is at your own risk.

Voucherify is not liable for issues caused by incorrect setup, misuse, or security gaps related to MCP.

If you have questions or need support,  [please reach out to our team](https://www.voucherify.io/contact-support), we’re here to help.