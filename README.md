## Voucherify Core MCP

Use a MCP (Model Context Protocol) server to ask questions in plain language and explore your loyalty and promo data through Voucherify API endpoints. An MCP works like a teammate to pull the numbers for you.

[Read complete Voucherify Core MCP article](https://docs.voucherify.io/guides/voucherify-core-mcp)

## Pick your path

Set up MPC connection in two ways:
- **Use the published package (recommended)**: no local build; your agent spawns the server
- **Contribute or run from source**: set up the repo, run locally (HTTP or `stdio`), and hack away 🚀

### Use the published package (recommended)

You don't need a local setup. Your agent runs the server with `uvx`.

#### Package prerequisites

To set up Voucherify Core MCP, you need:

- An MCP client (for example Cursor, Claude Desktop, Visual Studio Code)
- [UV installed](https://docs.astral.sh/uv/getting-started/) (remember to restart your client if you've installed UV for the first time)
- *Recommended*: Use a *separate* Voucherify server-side app ID and token for the MCP.

#### Set up Voucherify Core MCP

To set up Voucherify Core MCP:

1. Open your MCP client.
2. Add the following code snippet to the `mcp.json` file in your client. This step may vary depending on your client; refer to the specific documentation for details.

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

3. Copy your Voucherify server-side app ID and token from **Project settings** into the `mcp.json`.
4. Provide your Voucherify API base URL. For shared clusters:
    - Europe: `https://api.voucherify.io`
    - North America: `https://us1.api.voucherify.io`
    - Asia: `https://as1.api.voucherify.io`
5. Run the connection with the MCP server.
6. Open a new chat to start your conversation.

### Contribute or run from source

If you want to explore the code, tweak things, or run a local HTTP server, follow this setup.

#### Contribute: Prerequisites

- **Python 3.12+**
- **Voucherify credentials**: `VOUCHERIFY_APP_ID`, `VOUCHERIFY_APP_TOKEN` (use a separate pair)
- [UV installed](https://docs.astral.sh/uv/getting-started/) (remember to restart your client if you've installed UV for the first time)
- Installed dependencies:

```sh
uv sync --all-extras
```

#### Configure project credentials

Create an `.env` file in the project root (useful for debugging):

```sh
## Voucherify API Configuration for localhost
VOUCHERIFY_API_BASE_URL=http://localhost:8000
VOUCHERIFY_APP_ID=<app id>
VOUCHERIFY_APP_TOKEN=<app token>

## Tests (Management API keys can be found in Team Settings if you have this feature enabled)
VOUCHERIFY_MANAGEMENT_APP_ID=
VOUCHERIFY_MANAGEMENT_APP_TOKEN=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

When running a local MCP server, you can point to a specific cluster or local environment with `.env`:

```sh
VOUCHERIFY_API_BASE_URL=http://localhost:8000
```

#### Run it your way

You can run it by:
- HTTP server
- `stdio`

##### HTTP server

1. Start the server:
```sh
uv run python src/voucherify_core_mcp/main.py
```

2. You’ll get an endpoint at `http://127.0.0.1:10000/mcp/`.

3. Configure your agent to connect over HTTP:
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

##### stdio (spawned by your agent)

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

## MCP test engine

Use the test engine to check MCP capabilities in a safe environment.

1. Initialize project data:
   1. Create your `.env` as above.
   2. Run the project preparation script:
```sh
uv run prepare_project.py
```
  This will:
      - Look into `tests/.test.env` and delete the test project defined there.
      - Create a new test project using the Management API credentials from `.env`.
      - Generate required resources.
      - Persist credentials and resource IDs for tests in `.test.env`.

2. Run scenarios
```sh
uv run pytest tests/scenario_1_basic_scenarios.py
```
or a specific test:
```sh
uv run pytest tests/scenario_5_get_best_deals.py::test_get_best_deals_json_output
```

## Available functionalities

You can access the following endpoints with the Voucherify MCP to fetch data:

- *Find_customer*: Displays a customer's current status and detailed information such as collected loyalty points, eligibility for rewards, and other profile data. You can use the customer's email, source ID, or Voucherify ID.
- *List_campaigns*: Retrieves a list of campaigns to view active, scheduled, or completed campaigns.
- *Get_campaign_summary*: Displays a performance summary of ongoing campaigns, including comparisons with past activity (for example, previous week), to visualize trends and measure success over time.
- *Get_promotion_tier*: Fetches details about the configuration of a promotion tier, such as reward levels or thresholds that determine customer benefits.
- *Qualifications*: Checks and returns a customer's eligibility for specific campaigns, promotions, or reward rules, ensuring only qualified users receive incentives.
- *Get_best_deals*: Returns information about better prices contextually by showing the top 5 best incentives.

  > For the best results, set the Application rule to **Partial** in Voucherify dashboard, Redemptions section, Stacking rules tab. Read the [Stacking rules](https://support.voucherify.io/article/604-stacking-rules) article for more details.

- *Estimate_loyalty_points*: Returns an estimation of how many points a customer will earn for an order
- *List_products*: Retrieves the catalog of products, including attributes like pricing, availability, and categories.
- *Get_voucher*: Returns full details of a specific voucher, such as code, status, balance, and expiration date, to support redemption or troubleshooting.

## Best practices

Follow these practices to get the best results.

### Ask specific questions

- Use precise date ranges (for example “July 2025 redemptions”) instead of vague prompts like “recent redemptions”.
- Describe exactly what you need: specific campaign names, product categories, or data types.
- Broad requests (for example “all campaigns in the last 3 years”) usually lead to unclear results.

### Add more context if necessary

If results look off, reframe your query or try again. If the AI loops or repeats itself, redirect with a new question or start a new chat with a more detailed prompt.

### Ask more questions

Once you've got an answer you like, ask the client to:

- Suggest additional insights or next steps.
- Explain how it reached its conclusions to help refine your future prompts.

### Change model

If you're not satisfied with answers or the overall process, use a different AI model. Each model is trained on different data, has their own strengths, and is best suited for various tasks.

### Prompt examples

Read the following prompt examples for inspiration on how to use Voucherify Core MCP:

- Find customer by email `tom@example.com` (or `source_id`, or `customer_id`). Return the ID, `loyalty_balance`, `active_vouchers`.
- Count total of customers in segment “VIP”. List their basic details: name, email address, `source_id`. Turn the data into a CSV-friendly format.
- List active campaigns with fields: ID, name, type, `start_date`, `end_date`.
- Get voucher by code “BK-4829” and show: status, `redemption.count`, `redemption.limit`, `balance` (for gift or loyalty cards).
- Get campaign “BK-Sept-20OFF” data: total budget, spent budget, redemption counts, and per-customer caps.
- Show the campaign with the most coupons generated. Return redemption data for this campaign.
- Show me the best performing campaign in terms of number of successful redemptions. Return the budget - the total discount value that was applied.
- Get redemptions aggregated by day between 2025-09-01 and 2025-09-03 (timezone Europe/Warsaw).
- Get best deals for a customer with this email address. They have these items in their cart: Voucherify T-shirt (SKU: VCH-TST-001, quantity: 1, price: 25 USD), Voucherify Mug (SKU: VCH-MUG-002, quantity: 2, price: 15 USD each). Suggest if there's anything they can do to get even better deals.

> The number of API calls made by the Voucherify MCP depends on your question. Complex queries, like get best deals for a given customer, will need more API calls, while simple questions can be limited to just a few or even one, like get campaign summary. The MCP client will ask for confirmation to make an API call.
> 
> The API calls made with the Voucherify MCP are included in your billing period.

## Troubleshooting and feedback

The Voucherify MCP is still under development and we'd love to have your feedback to improve it. Also, if you've encountered any issues, please let us know. Contact [Voucherify support](https://www.voucherify.io/contact-support) or your account manager.

### **Disclaimer**

The Model Context Protocol (MCP) is a new open-source standard and may still carry potential vulnerabilities. The Voucherify MCP server setup and instructions are provided “as is,” without warranties, and use is at your own risk.

Voucherify is not liable for issues caused by incorrect setup, misuse, or security gaps related to MCP.

If you have questions or need support,  [please reach out to our team](https://www.voucherify.io/contact-support), we’re here to help.