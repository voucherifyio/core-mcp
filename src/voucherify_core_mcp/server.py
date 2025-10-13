# voucherify_core_mcp.py
"""
Voucherify Core API FastMCP Server

This server provides read-only MCP tools for retrieving information from Voucherify API.
It includes tools for accessing campaigns, customers, orders, products, and more.
"""

from fastmcp import FastMCP, Context
from typing import Annotated, Optional, Dict, Any, List
import json
import logging
import os
import argparse

from .client import (
    VOUCHERIFY_API_BASE_URL,
    VoucherifyError,
    async_make_voucherify_request,
)
from enum import Enum
from fastmcp.exceptions import ToolError

from urllib.parse import quote_plus, quote
from .pagination import _auto_paginate_pages


def map_voucherify_error_to_tool_error(e: Exception, context: str, ctx: Optional[Context] = None, resource_id: Optional[str] = None) -> ToolError:
    """
    Map Voucherify client exceptions to appropriate ToolError messages.
    
    Args:
        e: The caught exception
        context: Context description for the error (e.g., "finding customer")
        ctx: Optional MCP context for logging
        resource_id: Optional resource identifier for more specific error messages
    
    Returns:
        ToolError with appropriate message
    """
    resource_context = f" '{resource_id}'" if resource_id else ""
    
    if isinstance(e, VoucherifyError):
        if e.error_type == "http":
            # Handle specific HTTP status codes
            if e.status_code == 400:
                error_msg = f"Invalid parameters while {context}{resource_context}: {e.message}. Details: {e.response_text}"
            elif e.status_code == 404:
                error_msg = f"Resource{resource_context} not found while {context}: {e.message}. Details: {e.response_text}"
            else:
                error_msg = f"API error while {context}{resource_context} (HTTP {e.status_code}): {e.message}. Details: {e.response_text}"
        elif e.error_type == "timeout":
            error_msg = f"Request timeout while {context}{resource_context}: {e.message}"
        elif e.error_type == "connection":
            error_msg = f"Connection error while {context}{resource_context}: {e.message}"
        else:  # unexpected
            error_msg = f"Failed {context}{resource_context}: {e.message}"
    else:
        error_msg = f"Unexpected error while {context}{resource_context}: {str(e)}"
    
    if ctx:
        ctx.error(error_msg)
    
    return ToolError(error_msg)


def _build_pairs(obj, prefix=None):
    pairs = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}[{k}]" if prefix else str(k)
            pairs.extend(_build_pairs(v, new_prefix))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            pairs.extend(_build_pairs(v, f"{prefix}[{i}]"))
    else:
        pairs.append((prefix, obj))
    return pairs

def dict_to_querystring(data: dict, *, safe_key="[]$.", safe_val="-_.~", plus_spaces=True) -> str:
    pairs = _build_pairs(data)
    q = "&".join(
        f"{quote_plus(k, safe=safe_key) if plus_spaces else quote(k, safe=safe_key)}="
        f"{quote_plus(str(v), safe=safe_val) if plus_spaces else quote(str(v), safe=safe_val)}"
        for k, v in pairs
    )
    return q

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


instructions = """
This server provides read-only MCP tools for retrieving information from Voucherify API.

## Core Tool Categories:

### Customer Tools:
- `find_customer`: Look up customer by email or ID (cust_ prefix)

### Campaign & Promotion Tools:
- `get_campaign`: Retrieve complete campaign details by ID with validation rules
- `list_campaigns`: Get all campaigns for name-based lookup
- `get_campaign_summary`: Retrieve campaign analytics and statistics  
- `get_voucher`: Get specific voucher details by code or ID
- `get_promotion_tier`: Get specific promotion tier details

### Qualification & Deal Tools:
- `qualifications`: Find applicable vouchers/promotions for a customer
- `get_best_deals(customer, order)`: Get top 5 promotions with best deals (do NOT combine with qualifications)

### Product Tools:
- `list_products`: Search products with complex filtering

## ID Format Requirements:
- Campaign IDs: start with 'camp_' (e.g., camp_aPVb581gdJ1xF6esnDnDocVK)
- Customer IDs: start with 'cust_' (e.g., cust_abc123def456)
- Product IDs: start with 'prod_' (e.g., prod_112e92ce9a7cf5b1d8)
- Voucher Codes: alphanumeric codes and special characters (e.g., WELCOME10, SAVE20, TEST-ABC)
- Voucher IDs: start with 'v_' (e.g., v_abc123def456)
- Promotion Tier IDs: start with 'promo_' (e.g., promo_abc123def456)

## Common Workflows:

### Campaign Lookup:
1. If user provides campaign name only → use `list_campaigns` first
2. Match campaign by name, show multiple options if ambiguous
3. For detailed configuration → use `get_campaign` with campaign ID
4. For analytics/statistics → use `get_campaign_summary` with campaign ID

### Customer Analysis:
1. Find customer with `find_customer` (by email or ID)
2. For voucher wallet → use `qualifications` with customer + scenario="CUSTOMER_WALLET" (⚠️ customer is ALWAYS required)
3. For best deals analysis → use `get_best_deals(customer, order)` with customer + order (⚠️ customer and order are ALWAYS required)

### Product Search:
- Use `list_products` with structured filters
- Prices must be in cents (2000 = $20.00)
- Filter format: {"field": {"conditions": {"$operator": "value"}}}

## Parameter Guidelines:
- Always validate ID formats before API calls
- Use exact customer object structure: {"id": "cust_...", "source_id": "...", "metadata": {...}}
- For date parameters, use ISO 8601 format (YYYY-MM-DD)
- Empty strings are invalid - use null/None instead
- Price values always in cents across all tools (example: $20.10 = 2010)

## Validation Rules Structure:
Several tools (get_campaign, get_voucher, get_promotion_tier, get_best_deals) return processed validation rules with consistent structure:

### Enhanced Validation Rules Fields:
- **assigned_validation_rules** (get_campaign, get_voucher, get_promotion_tier): Complete rules definition
- **validation_rules** (get_best_deals): Rules information for deal analysis (complete rule definition is under "validation_rules_definition")

### Rule Structure Components:
```json
{
  "rules": {
    "1": {
      "name": "order.items.any",
      "conditions": {"$is": [{"id": "prod_123", "type": "product_or_sku"}]},
      "rules": {
        "1": {"name": "order.items.aggregated_quantity", "conditions": {"$more_than_or_equal": [4]}},
        "logic": "1"
      }
    },
    "2": {
      "name": "customer.segment",
      "conditions": {"$is": ["VIP"]}
    },
    "$RULE_ID": {
      "name": "order.amount",
      "conditions": {"$more_than_or_equal": [100000]}
    },
    "logic": "(1 AND 2) OR $RULE_ID"
  },
  "bundle_rules": {},
  "applicable_to": {
    "excluded": [],
    "included": [
      {
        "object": "product",
        "id": "prod_123",
        "effect": "APPLY_TO_EVERY",
        "target": "ITEM"
      }
    ],
    "included_all": false
  }
}
```

**Logic Explanation for Above Example:**
- Rule key "1": Order must contain product "prod_123" with at least 4 items total
- Rule key "2": Customer must be in "VIP" segment  
- Rule key "$RULE_ID": Order total must be ≥ $1000.00 (100000 cents)
- **Final Logic**: `"(1 AND 2) OR $RULE_ID"` means:
  - (Product + quantity requirements AND VIP status) OR minimum order amount

### Logic Patterns:
Rules are referenced by their numeric or string keys within the "rules" object:
- **Simple**: `"logic": "1"` - Rule under key "1" must be met
- **AND**: `"logic": "1 AND 2"` - Rule under key "1" AND rule under key "2" must be met
- **OR**: `"logic": "1 OR 2"` - Rule under key "1" OR rule under key "2" must be met  
- **Complex**: `"logic": "(1 AND 2) OR 3"` - (Rule "1" AND rule "2") OR rule "3" must be met


### Common Rule Names:
**Customer Rules:**
- `customer.segment`: Customer segment validation
- `customer.metadata`: Customer metadata conditions
- `customer.loyalty.tier`: Customer loyalty tier validation

**Order Volume Rules:**
- `order.amount`: Order total amount conditions
- `order.initial_amount`: Order amount before discounts
- `order.items.count`: Number of items in order
- `order.items.price_any`: Price validation for any item
- `order.items.price_each`: Price validation for each item

**Order Item Rules:**
- `order.items.any`: Check if order contains specific products
- `order.items.every`: All items must match conditions
- `order.items.none`: No items should match conditions
- `order.items.cheapest`: Apply to cheapest items
- `order.items.most_expensive`: Apply to most expensive items
- `order.items.quantity`: Item quantity validation
- `order.items.aggregated_quantity`: Total quantity across items
- `order.items.price`: Item price validation
- `order.items.aggregated_amount`: Total amount across items
- `order.items.metadata`: Item metadata conditions

**Campaign/Redemption Rules:**
- `campaign.orders.amount`: Campaign order amount limits
- `campaign.redemptions.count`: Campaign redemption count limits
- `redemption.count.per_customer`: Per-customer redemption limits
- `redemption.count.daily`: Daily redemption limits
- `redemption.count.monthly`: Monthly redemption limits

### Common Operators:
- `$is`: Exact match
- `$is_not`: Not equal
- `$in`: Value in array
- `$not_in`: Value not in array
- `$more_than`: Greater than
- `$more_than_or_equal`: Greater than or equal
- `$less_than`: Less than
- `$less_than_or_equal`: Less than or equal
- `$starts_with`: String starts with
- `$ends_with`: String ends with
- `$contains`: String contains

## Error Handling:
- If customer/campaign not found, suggest using list tools first
- For invalid parameters, provide specific format requirements
- Tool failures typically indicate missing resources or malformed requests
"""

# Create FastMCP server with explicit configuration
mcp = FastMCP(
    name="Voucherify Read API",
    instructions=instructions,
    on_duplicate_tools="warn"
)

# ----------------------- Customers ------------------------------

@mcp.tool(
    name="find_customer",
    tags={"customers", "read"}
)
async def find_customer(
    ctx: Context,
    email: Annotated[
        Optional[str],
        {"description": "Customer email address for lookup. Must be valid email format. Mutually exclusive with 'id' parameter."}
    ] = None,
    id: Annotated[
        Optional[str],
        {"description": "Customer ID starting with 'cust_' prefix or source_id (e.g., 'cust_abc123def456'). Mutually exclusive with 'email' parameter."}
    ] = None,
) -> str:
    """
    Find a customer by email or ID and return complete customer object.
    
    Lookup Behavior:
    - ID lookup: Direct retrieval by customer ID (faster, more reliable)
    - Email lookup: Searches customers and returns first match (case-insensitive)
    - Returns complete customer object including loyalty summary when available
    
    Parameters:
    - email: Valid email address for customer search
    - id: Customer identifier with 'cust_' prefix for direct lookup
    
    Validation Rules:
    - Exactly one parameter (email OR id) must be provided
    - Email must be valid email format
    - ID must start with 'cust_' prefix
    
    Examples:
    - find_customer(email="john.doe@example.com")
    - find_customer(id="cust_abc123def456")
    
    Returns:
    JSON object containing complete customer data including:
    - id, source_id, email, name
    - metadata (custom attributes)
    - loyalty summary (points, tier, etc.) when available
    - creation and update timestamps
    
    Raises:
    - ToolError: If both/neither parameters provided, customer not found, or invalid format
    """
    try:
        if not email and not id:
            raise ToolError("Provide either 'email' or 'id'.")

        # Direct by ID
        if id:
            ctx.info(f"Retrieving customer by id: {id}")
            resp = await async_make_voucherify_request("GET", f"/v1/customers/{id}", ctx=ctx)
            return json.dumps(resp.json(), indent=2)

        # Lookup by email
        params: Dict[str, Any] = {"limit": 1, "email": email}
        ctx.info(f"Searching customer by email: {email}")
        list_resp = await async_make_voucherify_request("GET", "/v1/customers", params=params, ctx=ctx)
        data = list_resp.json()
        customers: List[Dict[str, Any]] = _safe_get(data, ["customers"], []) or []

        if not customers:
            raise ToolError(f"Customer with email '{email}' not found")

        # Prefer exact email match (case-insensitive)
        return json.dumps(customers[0], indent=2)

        # # Fetch full details by id to include loyalty summary if available
        # ctx.info(f"Fetching full customer details for: {cust_id}")
        # full_resp = await async_make_voucherify_request("GET", f"/v1/customers/{cust_id}", ctx=ctx)
        # return json.dumps(full_resp.json(), indent=2)
    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "finding customer", ctx)

# ----------------------- Campaigns ------------------------------

@mcp.tool(
    name="get_campaign",
    tags={"campaigns", "read"}
)
async def get_campaign(
    ctx: Context,
    campaign_id: Annotated[
        str,
        {"description": "Campaign ID with 'camp_' prefix (e.g., 'camp_X26jzR8ObD55nlwOUcr63Px0')"}
    ]
) -> str:
    """
    Retrieve detailed information about a specific campaign by its ID.

    Returns complete campaign configuration including discount details, validation rules,
    voucher settings, and current status for campaign analysis and management.
    
    Enhanced Features:
    - Automatically fetches and processes validation rules for detailed rule analysis
    - Provides both raw validation_rules_assignments and processed assigned_validation_rules
    - Includes complete campaign hierarchy and voucher generation settings

    Parameters:
    - campaign_id: Campaign identifier for lookup

    Identifier Requirements:
    - Campaign ID: Must start with 'camp_' prefix (e.g., "camp_X26jzR8ObD55nlwOUcr63Px0")
    - ID must correspond to existing campaign

    Validation Rules:
    - Campaign ID must be valid and existing
    - ID format is case-sensitive

    Examples:
    - get_campaign(campaign_id="camp_X26jzR8ObD55nlwOUcr63Px0")

    Returns:
    JSON object containing complete campaign details including:
    
    Core Campaign Information:
    - id: Campaign system identifier (e.g., "camp_X26jzR8ObD55nlwOUcr63Px0")
    - name: Human-readable campaign name (e.g., "Burger Deluxe Family Campaign")
    - campaign_type: Campaign type ("DISCOUNT_COUPONS", "GIFT_VOUCHERS", "LOYALTY_PROGRAM", "PROMOTION")
    - type: Campaign generation type ("STATIC", "DYNAMIC")
    - active: Boolean campaign status
    - object: Always "campaign"
    
    Campaign Configuration:
    - auto_join: Boolean automatic customer enrollment setting
    - join_once: Boolean single enrollment restriction
    - use_voucher_metadata_schema: Boolean voucher metadata schema usage
    - protected: Boolean protection status against modifications
    
    Voucher Template Settings:
    - voucher: Complete voucher template configuration:
      * type: Voucher type ("DISCOUNT_VOUCHER", "GIFT_VOUCHER", etc.)
      * discount: Discount configuration (e.g., {"type": "PERCENT", "percent_off": 3})
      * redemption: Usage limits (e.g., {"quantity": null} for unlimited)
      * code_config: Code generation settings:
        - length: Code length (e.g., 8)
        - charset: Character set for code generation
        - pattern: Code pattern (e.g., "########")
      * is_referral_code: Boolean referral code status
    
    Campaign Status and Statistics:
    - vouchers_count: Total vouchers generated in campaign
    - creation_status: Campaign creation status ("DONE", "IN_PROGRESS", "FAILED")
    - vouchers_generation_status: Voucher generation status ("DONE", "IN_PROGRESS", "FAILED")
    - created_at: Campaign creation timestamp (ISO 8601)
    
    Access and Categorization:
    - access_settings_assignments: Access control assignments with data array and total count
    - category_id: Campaign category identifier (null if uncategorized)
    - categories: Array of campaign categories (empty if uncategorized)
    
    Validation Rules (Enhanced):
    - assigned_validation_rules: Processed validation rules with detailed conditions (added by this tool)
      See "Validation Rules Structure" section in server instructions for complete field documentation

    Use Cases:
    - Analyze campaign configuration and discount mechanics
    - Understand validation rules and product requirements
    - Check campaign status and voucher generation progress
    - Review campaign hierarchy and settings
    - Get complete campaign blueprint for duplication

    Raises:
    - ToolError: If campaign not found or invalid campaign ID format
    """
    try:
        ctx.info(f"Retrieving campaign: {campaign_id}")
        response = await async_make_voucherify_request("GET", f"/v1/campaigns/{campaign_id}", ctx=ctx)
        ctx.info(f"Successfully retrieved campaign: {campaign_id}")
        campaign = response.json()
        
        # Process validation rules if they exist
        if "validation_rules_assignments" in campaign and campaign["validation_rules_assignments"]["total"] > 0:
            validation_rules = []
            for rule in campaign["validation_rules_assignments"]["data"]:
                val_rule_response = await async_make_voucherify_request("GET", f"/v1/validation-rules/{rule['rule_id']}", ctx=ctx)
                val_rule = val_rule_response.json()
                validation_rules.append({
                    # Don't send name to avoid confusion with campaign name
                    "rules": val_rule["rules"],
                    "bundle_rules": val_rule["bundle_rules"],
                    "applicable_to": val_rule["applicable_to"]
                })
            # Expose validation rules to the model
            del campaign["validation_rules_assignments"]
            campaign["assigned_validation_rules"] = validation_rules

        return json.dumps(campaign, indent=2)

    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "retrieving campaign", ctx, campaign_id)


@mcp.tool(
    name="list_campaigns",
    tags={"campaigns", "list", "read"},
)
async def list_campaigns(
    ctx: Context
) -> str:
    """
    List all campaigns with basic information for campaign resolution.
    
    Primary Use Case:
    Resolve campaign ID when user provides only campaign name or partial name.
    Returns comprehensive list of all campaigns for further name-based matching.
    
    Behavior:
    - Retrieves all campaigns (up to 1000) in single request
    - No filtering - returns complete campaign catalog
    - Avoid multiple calls as results are comprehensive
    
    No Parameters Required:
    This tool requires no input parameters and returns all available campaigns.
    
    Returns:
    JSON array of campaign objects, each containing:
    - id: Campaign identifier starting with 'camp_'
    - name: Human-readable campaign name
    - campaign_type: Campaign type (e.g., 'DISCOUNT_COUPONS', 'GIFT_VOUCHERS')
    - created_at: ISO 8601 creation timestamp
    
    Example Output:
    [
        {
            "id": "camp_abc123def456",
            "name": "Summer Sale 2025",
            "campaign_type": "DISCOUNT_COUPONS",
            "created_at": "2025-01-01T00:00:00.000Z"
        },
        {
            "id": "camp_xyz789ghi012",
            "name": "Holiday Promotions",
            "campaign_type": "GIFT_VOUCHERS", 
            "created_at": "2024-12-01T00:00:00.000Z"
        }
    ]
    
    Usage Pattern:
    1. Call list_campaigns() to get all campaigns
    2. Match user's campaign name against returned names
    3. Use resolved campaign ID for other campaign tools
    
    Limitations:
    - Maximum 1000 campaigns returned
    - No filtering options available
    - Results sorted by creation date
    """
    try:
        result = await _auto_paginate_pages(
            ctx,
            endpoint = "/v1/campaigns",
            base_params = {},
            data_key = "campaigns",
            limit = 100,
            auto_paginate = True,
            max_items = 1000,
        )
        campaignsList = [ 
            {
                "id": campaign["id"],
                "name": campaign["name"],
                "campaign_type": campaign["campaign_type"],
                "created_at": campaign["created_at"],
            } for campaign in result["campaigns"] 
        ]

        return json.dumps(campaignsList, indent=2, default=str)
    except Exception as e:
        error = map_voucherify_error_to_tool_error(e, "listing campaigns", ctx)
        raise error from e


@mcp.tool(
    name="get_campaign_summary",
    tags={"campaigns", "summary", "read"}
)
async def get_campaign_summary(
    ctx: Context,
    campaign_id: Annotated[
        str,
        {"description": "Campaign ID starting with 'camp_' prefix (e.g., 'camp_aPVb581gdJ1xF6esnDnDocVK')"}
    ],
    start_date: Annotated[
        Optional[str], 
        {"description": "Optional start date in ISO 8601 format (YYYY-MM-DD). Must be provided together with end_date."}
    ] = None,
    end_date: Annotated[
        Optional[str], 
        {"description": "Optional end date in ISO 8601 format (YYYY-MM-DD). Must be provided together with start_date."}
    ] = None,
) -> str:
    """
    Retrieve comprehensive analytics summary for a specific campaign.
    
    Returns detailed statistics including validations, redemptions, publications, and 
    campaign-type-specific metrics for performance analysis.
    
    Parameters:
    - campaign_id: Valid campaign identifier with 'camp_' prefix
    - start_date: Optional analysis period start (ISO 8601 date format)
    - end_date: Optional analysis period end (ISO 8601 date format)
    
    Date Parameter Rules:
    - Both start_date and end_date must be provided together or omitted together
    - Empty strings are invalid - use null/None for no date filtering
    - Omitting both dates returns full campaign period summary
    - Date format: YYYY-MM-DD (e.g., "2025-01-01")
    
    Examples:
    - get_campaign_summary(campaign_id="camp_aPVb581gdJ1xF6esnDnDocVK")
    - get_campaign_summary(
        campaign_id="camp_aPVb581gdJ1xF6esnDnDocVK",
        start_date="2025-01-01",
        end_date="2025-01-31"
      )
    
    Examples of bad usage:
    - get_campaign_summary(campaign_id="camp_aPVb581gdJ1xF6esnDnDocVK", start_date="", end_date="")

    Returns:
    JSON object containing campaign analytics including:
    - validations: Validation attempt statistics
    - redemptions: Successful redemption counts and values
    - publications: Voucher distribution metrics
    - campaign_type specific metrics (varies by campaign type)
    - date range information
    - performance indicators
    
    Raises:
    - ToolError: If campaign not found, invalid date format, or mismatched date parameters
    """
    try:
        ctx.info(f"Retrieving campaign summary: {campaign_id}")
        
        # Make API request
        response = await async_make_voucherify_request("GET", f"/v1/campaigns/{campaign_id}/summary", ctx=ctx, params={
            "start_date": start_date,
            "end_date": end_date,
        })
        
        ctx.info(f"Successfully retrieved campaign summary: {campaign_id}")
        
        # Return formatted JSON
        return json.dumps(response.json(), indent=2)
        
    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "retrieving campaign summary for", ctx, campaign_id)

# ----------------------- Vouchers ------------------------------


@mcp.tool(
    name="get_voucher",
    tags={"vouchers", "read"}
)
async def get_voucher(
    ctx: Context,
    identifier: Annotated[
        str,
        {"description": "Voucher code (e.g., 'WELCOME10', 'SAVE20', 'TEST-ABC') or voucher ID with 'v_' prefix (e.g., 'v_abc123def456')"}
    ]
) -> str:
    """
    Retrieve detailed information about a specific voucher by its code or ID.

    Returns complete voucher configuration including discount details, usage limits,
    validation rules, and current status for voucher analysis and management.

    Enhanced Features:
    - Automatically fetches and processes validation rules for detailed rule analysis
    - Provides both raw validation_rules_assignments and processed validation_rules
    - Includes QR/barcode assets for voucher display and distribution

    Parameters:
    - identifier: Voucher code or ID for lookup

    Identifier Types:
    - Voucher Code: Human-readable code with alphanumeric and special characters (e.g., "WELCOME10", "SAVE20", "TEST-ABC")
    - Voucher ID: System identifier with 'v_' prefix (e.g., "v_abc123def456")

    Validation Rules:
    - Identifier must correspond to existing voucher
    - Both codes and IDs are case-sensitive

    Examples:
    - get_voucher(identifier="WELCOME10")
    - get_voucher(identifier="v_abc123def456")

    Returns:
    JSON object containing complete voucher details including:

    Core Voucher Information:
    - id: Voucher system identifier (e.g., "v_4dyaDRCMD0bUDNv47pDqnGlCJhSVWtnT")
    - code: Human-readable voucher code (e.g., "DELUXE-SG63RY")
    - type: Voucher type ("DISCOUNT_VOUCHER", "GIFT_VOUCHER", "LOYALTY_CARD")
    - active: Boolean voucher status
    - object: Always "voucher"

    Discount Configuration:
    - discount: Discount details with type and value (e.g., {"type": "PERCENT", "percent_off": 25})
    - gift: Gift voucher amount (null for discount vouchers)
    - loyalty_card: Loyalty card details (null for regular vouchers)

    Validity and Constraints:
    - start_date, expiration_date: Validity period (ISO 8601 or null)
    - validity_timeframe, validity_hours: Time-based restrictions
    - validity_day_of_week: Array of valid weekdays (1=Monday, 7=Sunday)

    Usage Tracking:
    - redemption: Usage statistics with quantity limits and current usage
    - publish: Publication information and count
    - holder_id: Customer ID if voucher is assigned

    Campaign and Categorization:
    - campaign, campaign_id: Parent campaign information (null for standalone vouchers)
    - category, category_id, categories: Voucher categorization

    Validation Rules (Enhanced):
    - assigned_validation_rules: Processed validation rules with detailed conditions (added by this tool)
      See "Validation Rules Structure" section in server instructions for complete field documentation

    Additional Data:
    - metadata: Custom voucher attributes
    - additional_info: Extra voucher information
    - assets: QR code and barcode URLs for voucher display
    - is_referral_code: Boolean indicating referral voucher
    - created_at, updated_at: ISO 8601 timestamps

    Use Cases:
    - Verify voucher validity and details
    - Check voucher usage and limits
    - Analyze voucher configuration and discount mechanics
    - Understand validation rules and product requirements
    - Check voucher ownership and assignment
    - Get QR/barcode assets for voucher display

    Raises:
    - ToolError: If voucher not found or invalid identifier format
    """
    try:
        ctx.info(f"Retrieving voucher: {identifier}")
        response = await async_make_voucherify_request("GET", f"/v1/vouchers/{identifier}", ctx=ctx)
        ctx.info(f"Successfully retrieved voucher: {identifier}")
        voucher = response.json()
        if "validation_rules_assignments" in voucher and voucher["validation_rules_assignments"]["total"] > 0:
            validation_rules = []
            for rule in voucher["validation_rules_assignments"]["data"]:
                val_rule_response = await async_make_voucherify_request("GET", f"/v1/validation-rules/{rule['rule_id']}", ctx=ctx)
                val_rule = val_rule_response.json()
                validation_rules.append({
                    # Don't send name to avoid confusion with incentive name
                    "rules": val_rule["rules"],
                    "bundle_rules": val_rule["bundle_rules"],
                    "applicable_to": val_rule["applicable_to"]
                })
            # Expose validation rules to the model
            del voucher["validation_rules_assignments"]
            voucher["assigned_validation_rules"] = validation_rules

        return json.dumps(voucher, indent=2)

    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "retrieving voucher", ctx, identifier)


# ----------------------- Promotions ------------------------------

@mcp.tool(
    name="get_promotion_tier",
    tags={"promotions", "tiers", "read"}
)
async def get_promotion_tier(
    ctx: Context,
    promotion_tier_id: Annotated[
        str,
        {"description": "Promotion tier ID starting with 'promo_' prefix (e.g., 'promo_abc123def456')"}
    ]
) -> str:
    """
    Retrieve detailed information about a specific promotion tier by its ID.

    Returns complete promotion tier configuration including discount rules, 
    validation criteria, and metadata for promotion analysis and management.
    
    Enhanced Features:
    - Automatically fetches and processes validation rules for detailed rule analysis
    - Provides both raw validation_rules_assignments and processed assigned_validation_rules
    - Includes complete promotion tier hierarchy and action settings

    Parameters:
    - promotion_tier_id: Promotion tier identifier for lookup

    Identifier Requirements:
    - Promotion Tier ID: Must start with 'promo_' prefix (e.g., "promo_abc123def456")
    - ID must correspond to existing promotion tier

    Validation Rules:
    - Promotion tier ID must be valid and existing
    - ID format is case-sensitive

    Examples:
    - get_promotion_tier(promotion_tier_id="promo_abc123def456")

    Returns:
    JSON object containing complete promotion tier details including:
    
    Core Promotion Tier Information:
    - id: Promotion tier system identifier (e.g., "promo_abc123def456")
    - name: Human-readable tier name
    - banner: Display banner text for promotion
    - object: Always "promotion_tier"
    
    Discount Configuration:
    - action: Complete discount configuration including:
      * discount: Discount type and value settings
      * unit_off: Fixed amount discount (if applicable)
      * unit_off_formula: Dynamic discount calculation (if applicable)
      * percent_off: Percentage discount (if applicable)
      * percent_off_formula: Dynamic percentage calculation (if applicable)
    
    Promotion Settings:
    - hierarchy: Tier ordering and priority within campaign
    - campaign: Parent campaign information
    - campaign_id: Parent campaign identifier
    - summary: Promotion tier summary and statistics
    
    Validation Rules (Enhanced):
    - assigned_validation_rules: Processed validation rules with detailed conditions (added by this tool)
      See "Validation Rules Structure" section in server instructions for complete field documentation
    
    Additional Data:
    - metadata: Custom promotion tier attributes
    - created_at, updated_at: ISO 8601 timestamps

    Use Cases:
    - Analyze promotion tier configuration and discount mechanics
    - Understand validation rules and eligibility requirements
    - Review promotion tier hierarchy and priority
    - Get complete promotion tier blueprint for management
    - Check promotion tier status and performance
    
    Raises:
    - ToolError: If promotion tier not found or invalid ID format
    """
    try:
        ctx.info(f"Retrieving promotion tier: {promotion_tier_id}")
        response = await async_make_voucherify_request("GET", f"/v1/promotions/tiers/{promotion_tier_id}", ctx=ctx)
        ctx.info(f"Successfully retrieved promotion tier: {promotion_tier_id}")
        promotion_tier = response.json()
        
        # Process validation rules if they exist
        if "validation_rule_assignments" in promotion_tier and promotion_tier["validation_rule_assignments"]["total"] > 0:
            validation_rules = []
            for rule in promotion_tier["validation_rule_assignments"]["data"]:
                val_rule_response = await async_make_voucherify_request("GET", f"/v1/validation-rules/{rule['rule_id']}", ctx=ctx)
                val_rule = val_rule_response.json()
                validation_rules.append({
                    # Don't send name to avoid confusion with promotion tier name
                    "rules": val_rule["rules"],
                    "bundle_rules": val_rule["bundle_rules"],
                    "applicable_to": val_rule["applicable_to"]
                })
            # Expose validation rules to the model
            del promotion_tier["validation_rule_assignments"]
            promotion_tier["assigned_validation_rules"] = validation_rules

        return json.dumps(promotion_tier, indent=2)

    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "retrieving promotion tier", ctx, promotion_tier_id)


# ----------------------- Qualifications ------------------------------

class QualificationScenario(str, Enum):
    ALL = "ALL"
    CUSTOMER_WALLET = "CUSTOMER_WALLET" 
    AUDIENCE_ONLY = "AUDIENCE_ONLY"
    PRODUCTS = "PRODUCTS"
    PRODUCTS_DISCOUNT = "PRODUCTS_DISCOUNT"
    PROMOTION_STACKS = "PROMOTION_STACKS"
    PRODUCTS_BY_CUSTOMER = "PRODUCTS_BY_CUSTOMER"
    PRODUCTS_DISCOUNT_BY_CUSTOMER = "PRODUCTS_DISCOUNT_BY_CUSTOMER"

@mcp.tool(
    name="qualifications",
    tags={"qualifications", "customers", "wallet", "read"}
)
async def qualifications(
    ctx: Context,
    customer: Annotated[
        Dict[str, Any],
        {"description": "REQUIRED: Customer object that MUST be provided. Must contain either 'id' (cust_ prefixed) or 'source_id'. This parameter is NEVER optional - always provide customer data."}
    ],
    scenario: Annotated[
        QualificationScenario,
        {"description": "Qualification scenario determining which redeemables to return. Default: ALL for comprehensive results."}
    ] = QualificationScenario.ALL,
) -> str:
    """
    Find redeemables (vouchers, promotions, campaigns) applicable to given customer.
    
    ⚠️  CRITICAL: The 'customer' parameter is ALWAYS REQUIRED - never call this tool without it!
    
    Returns list of available discounts, vouchers, and promotions based on customer 
    profile and selected scenario for targeted marketing and cart optimization.
    
    Parameters:
    - customer: 🔴 MANDATORY - Customer identification and profile data. This parameter is REQUIRED for every call.
    - scenario: 🔴 MANDATORY - Qualification scope determining which redeemables to evaluate (optional, defaults to ALL)
    
    Customer Object Structure:
    Required (one of):
    - id: Customer ID with 'cust_' prefix (e.g., "cust_abc123")
    - source_id: External customer identifier
    Optional:
    - metadata: Dict of custom customer attributes for rule matching
    
    Scenario Guide (Choose Based on Use Case):
    
    CUSTOMER-FOCUSED:
    - ALL: Scenario that returns redeemables available for the customer
    - CUSTOMER_WALLET: returns vouchers applicable to the customer's cart based on the vouchers assigned to the customer's profile
    - AUDIENCE_ONLY: returns all vouchers, promotion tiers, and campaigns available to the customer. It validates the rules based on the customer profile only.
    
    PRODUCT-FOCUSED (require product context in other tools):
    - PRODUCTS: returns all promotions available for the products (when a discount is defined to be applied to the item or when the item is required in the validation rule)
    - PRODUCTS_DISCOUNT:  returns all promotions available for products when a discount is defined as applicable to specific item(s).
    - PRODUCTS_BY_CUSTOMER: returns all promotions available for a customer for the products (when a discount is defined to be applied to the item or when the item is required in the validation rule).
    - PRODUCTS_DISCOUNT_BY_CUSTOMER: returns all promotions available for a customer for products when a discount is defined as applicable to specific item(s).
    
    ADVANCED:
    - PROMOTION_STACKS: returns the applicable promotion stacks
    
    Common Usage Patterns:
    - Customer wallet check: Use CUSTOMER_WALLET
    - Matching redeemables to given context: Use ALL
    - Customer-based targeting: Use AUDIENCE_ONLY
    
    ✅ CORRECT Examples (always include customer):
    - qualifications(customer={"id": "cust_abc123"}, scenario="CUSTOMER_WALLET")
    - qualifications(customer={"source_id": "user_456", "metadata": {"tier": "gold"}})
    - qualifications(customer={"id": "cust_xyz789"}, scenario="ALL")
    - qualifications(customer={"id": "cust_abc123"})  # scenario defaults to ALL

    🚫 WRONG Examples (missing required customer parameter):
    - qualifications()  # ❌ NEVER do this - customer is required
    - qualifications(scenario="CUSTOMER_WALLET")  # ❌ NEVER do this - customer is required
    - qualifications(scenario="ALL")  # ❌ NEVER do this - customer is required
    
    💡 Remember: ALWAYS provide the customer parameter - it's never optional!
    
    Returns:
    JSON object containing:
    - redeemables: Array of applicable vouchers/promotions
    - Each redeemable includes: id, name, discount details, validation rules
    - Scenario-specific filtering applied
    
    Raises:
    - ToolError: If customer missing required fields or invalid scenario
    """
    try:
        # Explicit validation: customer parameter must always be provided
        if not customer:
            raise ToolError("🚫 CRITICAL ERROR: 'customer' parameter is REQUIRED and was not provided. Always include customer data like: qualifications(customer={'id': 'cust_abc123'})")
        
        payload: Dict[str, Any] = {
            "options": {
                "limit": 100
            }
        }
        cust_payload: Dict[str, Any] = {}
        for k in ["id", "source_id", "metadata"]:
            if k in customer and customer[k] is not None:
                cust_payload[k] = customer[k]
        if not cust_payload:
            raise ToolError("🚫 INVALID CUSTOMER: Customer object must include at least 'id' or 'source_id'. Example: qualifications(customer={'id': 'cust_abc123'}, scenario='CUSTOMER_WALLET')")
        payload["customer"] = cust_payload
        if scenario:
            payload["scenario"] = scenario
        resp = await async_make_voucherify_request("POST", "/v1/qualifications", json_data=payload, ctx=ctx)
        return json.dumps(resp.json(), indent=2)
    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "calling qualifications", ctx)


@mcp.tool(
    name="get_best_deals",
    tags={"best_deals", "customers", "upsell", "promotions"}
)
async def get_best_deals(
    ctx: Context,
    customer: Annotated[
        Dict[str, Any],
        {"description": "Customer object. Must contain either 'id' (cust_ prefixed) or 'source_id'. Optional 'metadata' dict."}
    ],
    order: Annotated[
        Dict[str, Any],
        {"description": "Order object containing items list for promotion analysis and upselling recommendations"}
    ],
) -> str:
    """
    Find top 5 best deal promotions for customer's order with validation analysis.
    
    Analyzes order items against available promotions to identify highest-value deals.
    Returns promotions with validation rules - some may be partially valid, requiring
    additional items or changes to qualify for the discount.
    
    Use Case: Upselling and cross-selling optimization
    - Identify best promotions for current cart
    - Determine what customer needs to add/change for qualification
    - Optimize cart value through targeted recommendations
    
    Important: This tool is specialized for order-based promotion analysis.
    Do not combine with 'qualifications' tool as they serve different purposes.
    
    Parameters:
    Parameters:
    - customer: 🔴 MANDATORY - Customer identification and profile data. This parameter is REQUIRED for every call.
    - order: 🔴 MANDATORY - Order with items list for promotion matching and analysis. This parameter is REQUIRED for every call.
    
    Order Item Configuration:
    Each item can be specified in multiple ways:
    
    1. By Product ID (most precise):
       {"product_id": "prod_abc123", "price": 2000, "quantity": 1}
    
    2. By Source ID (requires related_object):
       {"source_id": "special-meal", "related_object": "product", "price": 3000, "quantity": 1}
    
    3. Generic with metadata (for product collection matching):
       {"quantity": 2, "product": {"metadata": {"category": "Electronics"}}}
    
    4. Price-less items (uses catalog price):
       {"source_id": "drink", "related_object": "product", "quantity": 1}
    
    Pricing Rules:
    - All prices in cents (2000 = $20.00, 150 = $1.50)
    - Items without price use product catalog pricing
    - Quantity must be positive integer
    
    Examples:
    - get_best_deals(
        customer={"id": "cust_abc123"},
        order={
            "items": [
                {"product_id": "prod_112e92ce9a7cf5b1d8", "price": 2000, "quantity": 1},
                {"source_id": "special-meal", "related_object": "product", "price": 3000, "quantity": 1}
            ]
        }
      )

    Example of invalid usage:
    - get_best_deals()
    
    Returns:
    JSON array of up to 5 promotion objects, each containing:
    - id: Promotion identifier
    - result: Qualification status (APPLICABLE, PARTIALLY_APPLICABLE, etc.)
    - is_applicable: Boolean indicating if given incentive meets all validation rules
    - redeemable_details: Promotion information (banner, description, campaign)
    - validation_rules: Array of validation requirements with status
    - resolved_order: Order with calculated totals and promotion effects if incentive is applicable
    
    Each validation rule includes:
    - validation_rules_definition: Rule logic and requirements
    - validation_status: Current compliance status
    - validation_omitted_sub_rules: Missing requirements for qualification
    
    See "Validation Rules Structure" section in server instructions for detailed rule format documentation
    
    Raises:
    - ToolError: If customer missing required fields or order structure invalid
    """
    try:
        payload: Dict[str, Any] = {
            "customer": {},
            "options": {
                "limit": 5,
                "expand": [
                    "redeemable",
                    "validation_rules"
                ],
                "sorting_rule": "BEST_DEAL"
            },
            "scenario": "PRODUCTS_DISCOUNT_BY_CUSTOMER",
            "order": order
        }
        for k in ["id", "source_id", "metadata"]:
            if k in customer and customer[k] is not None:
                payload["customer"][k] = customer[k]
        response = await async_make_voucherify_request("POST", "/v1/qualifications", json_data=payload, ctx=ctx)

        qualifications = response.json()

        if qualifications["redeemables"]["total"] == 0:
            return json.dumps([], indent=2)
        else:
            applicable_redeemables_map = {}

            requested_redeemables = []
            for qualified_item in qualifications["redeemables"]["data"]:
                redeemable_type = qualified_item.get("object")
                if redeemable_type in ("promotion_tier", "voucher", "promotion_stack"):
                    requested_redeemables.append({"object": redeemable_type, "id": qualified_item.get("id")})

            if requested_redeemables:
                validations_payload = {
                    "customer": payload.get("customer", {}),
                    "order": order,
                    "redeemables": requested_redeemables,
                }
                validations_resp = await async_make_voucherify_request(
                    "POST", "/v1/validations", json_data=validations_payload, ctx=ctx
                )
                validations_data = validations_resp.json()

                for item in (validations_data.get("redeemables") or []):
                    if item.get("status") == "APPLICABLE":
                        applicable_redeemables_map[item.get("id")] = {
                            "status": item.get("status"),
                            "order": item.get("order"),
                        }

            redeemables = []
            for redeemable in qualifications["redeemables"]["data"]:
                validation_rules = []
                if "validation_rules_assignments" in redeemable:
                    for rule in redeemable["validation_rules_assignments"]["data"]:
                        val_rule_response = await async_make_voucherify_request("GET", f"/v1/validation-rules/{rule['rule_id']}", ctx=ctx) 
                        val_rule = val_rule_response.json()

                        validation_rules.append({
                            # Don't send name to avoid confusion with incentive name
                            "validation_rules_definition": {
                                "rules": val_rule["rules"],
                                "bundle_rules": val_rule["bundle_rules"],
                                "applicable_to": val_rule["applicable_to"]
                            },
                            "validation_status": rule["validation_status"],
                            "validation_omitted_sub_rules": rule["validation_omitted_rules"],
                        })

                redeemable_id = redeemable.get("id")
                is_applicable = applicable_redeemables_map.get(redeemable_id) is not None

                redeemables.append({
                    "id": redeemable_id,
                    "object": redeemable["object"],
                    "result": redeemable["result"],
                    "is_applicable": is_applicable,
                    "redeemable_details": {
                        "public_banner": redeemable["banner"] if "banner" in redeemable else None,
                        "alternative_description": redeemable["name"] if "name" in redeemable else None,
                        "campaign_name": redeemable["campaign_name"] if "campaign_name" in redeemable else None,
                    },
                    "validation_rules": validation_rules,
                    "resolved_order": applicable_redeemables_map.get(redeemable_id).get("order") if is_applicable else None,
                })
            return json.dumps(redeemables, indent=2)
    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "calling get_best_deals", ctx)

# =====================================================================
# Pagination helpers and listing tools (customers, voucher tx, campaign tx)
# ---------------------------------------------------------------------

def _safe_get(d: Dict[str, Any], path: List[str], default=None) -> Any:
    result = d
    for key in path:
        if not isinstance(result, dict) or key not in result:
            return default
        result = result[key]
    return result


# ------------------------- List Products ----------------------------

@mcp.tool(
    name="list_products",
    tags={"products", "search", "catalog"}
)
async def list_products(
    ctx: Context,
    filters: Annotated[
        Optional[Dict],
        {"description": "Product filters using field paths and condition operators. Must be valid JSON object with nested structure."}
    ] = None,
    page: Annotated[
        Optional[int],
        {"description": "Page number for pagination (omit for page 1, provide 2+ for subsequent pages)"}
    ] = None,
) -> str:
    """
    List products with optional filtering and pagination.
    
    Returns paginated product catalog with flexible filtering capabilities for 
    product discovery, inventory analysis, and catalog management.
    
    Parameters:
    - filters: Optional filter criteria using field paths and operators
    - page: Optional page number (default: 1, provide only for page 2+)
    
    Filter Structure:
    {
        "field_path": {
            "conditions": {
                "$operator": "value"
            }
        }
    }
    
    Supported Fields:
    - name: Product name (string)
    - source_id: External product identifier (string)  
    - price: Product price in cents (integer)
    - created_at: Creation date (ISO 8601)
    - metadata.<field>: Custom metadata fields (various types)
    
    Operators by Field Type:
    String fields (name, source_id, metadata):
    - $is, $is_not: Exact match
    - $contains, $starts_with: Partial match
    - $in: Match any from array
    
    Numeric fields (price, numeric metadata):
    - $more_than, $less_than: Comparison
    - $more_than_equal, $less_than_equal: Inclusive comparison
    
    Date fields (created_at):
    - $after, $before: Date comparison (ISO 8601 format)
    
    Pricing Rules:
    - All prices in cents (2000 = $20.00, 150 = $1.50)
    - Consistent across all Voucherify tools
    
    Examples:
    - list_products()  # All products, page 1
    - list_products(page=2)  # All products, page 2
    - list_products(
        filters={
            "metadata.category": {"conditions": {"$is": "Electronics"}},
            "price": {"conditions": {"$more_than": 5000}}
        }
      )
    - list_products(
        filters={
            "name": {"conditions": {"$contains": "Premium"}}, 
            "created_at": {"conditions": {"$after": "2025-01-01"}}
        },
        page=3
      )
    
    Returns:
    JSON object containing:
    - products: Array of product objects with full details
    - total: Total number of matching products
    - has_more: Boolean indicating if more pages available
    - Each product includes: id, name, source_id, price, metadata, timestamps
    
    Pagination:
    - 100 products per page
    - Results sorted by created_at descending (newest first)
    - Custom sorting not supported
    
    Raises:
    - ToolError: If filter structure invalid or unsupported operators used
    """
    try:

        params = dict_to_querystring({
            "page": page or 1,
            "limit": 100,
            "order": "-created_at",
            "filters":  filters or None,
        })
        response = await async_make_voucherify_request("GET", "/v1/products", params=params, ctx=ctx)
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        raise map_voucherify_error_to_tool_error(e, "listing products", ctx)


def main():
    """Main entry point for the Voucherify MCP server."""
    # CLI argument parsing for runtime transport override
    parser = argparse.ArgumentParser(description="Run Voucherify Read MCP server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "http", "stdio"],
        help="Transport to use for MCP (default reads MCP_TRANSPORT env or 'streamable-http')",
    )
    args = parser.parse_args()

    # Determine transport precedence: CLI arg > env var > default
    transport = args.transport or os.getenv("MCP_TRANSPORT", "streamable-http")
    # Accept 'http' alias for clarity
    if transport == "http":
        transport = "streamable-http"

    # Configure server logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting Voucherify Read API MCP Server...")
    logger.info(f"API Base URL: {VOUCHERIFY_API_BASE_URL}")
    logger.info(f"Transport: {transport}")

    # Run the MCP server with selected transport
    if transport == "streamable-http":
        mcp.run(transport=transport, port=10000)
    else:
        mcp.run(transport=transport)


# TODO consider removing this?
if __name__ == "__main__":
    main()