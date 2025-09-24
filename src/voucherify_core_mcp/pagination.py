# utils.py
"""
Utils for Voucherify Core API FastMCP Server
"""

from fastmcp import Context
from typing import Optional, Dict, Any, List
import json
from .client import async_make_voucherify_request

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


def _build_export_payload(
    fields: Optional[List[str]],
    order: Optional[str],
    filters_json: Optional[str],
    order_in_parameters: bool = True,
    response_format: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Helper that builds request payload for Voucherify Export endpoints.

    Args:
        fields: list of CSV column names to include.
        order: ordering string (e.g. "-created_at").
        filters_json: JSON-encoded string with deep filters.
        order_in_parameters: when False, `order` is placed at root level.
        response_format: "CSV" | "JSON" if supported by endpoint.
    """
    payload: Dict[str, Any] = {}
    params: Dict[str, Any] = {}

    if fields:
        params["fields"] = fields

    if order:
        if order_in_parameters:
            params["order"] = order
        else:
            payload["order"] = order

    if filters_json:
        try:
            params["filters"] = json.loads(filters_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in filters: {e}")

    if response_format:
        params["response_format"] = response_format

    if params:
        payload["parameters"] = params

    return payload

def _add_if(params: Dict[str, Any], key: str, value: Optional[Any]) -> None:
    if value is not None:
        params[key] = value


async def _auto_paginate_timestamp(
    ctx: Optional[Context],
    endpoint: str,
    base_params: Dict[str, Any],
    data_key: str,
    cursor_field: str,
    limit: int,
    auto_paginate: bool,
    max_items: Optional[int],
) -> Dict[str, Any]:
    if ctx:
        ctx.info(f"Auto-paginate {endpoint} on {cursor_field}")
    all_items: List[Any] = []
    has_more = True
    more_starting_after = None
    params = base_params.copy()
    params["limit"] = limit
    total_fetched = 0
    while has_more and (max_items is None or total_fetched < max_items):
        response = await async_make_voucherify_request("GET", endpoint, params=params, ctx=ctx)
        data = response.json()
        items = _safe_get(data, [data_key], [])
        if max_items is not None:
            items = items[: max_items - total_fetched]
        all_items.extend(items)
        total_fetched += len(items)
        has_more = _safe_get(data, ["has_more"], False)
        if not has_more or not auto_paginate:
            break
        if items:
            last = items[-1]
            more_starting_after = _safe_get(last, [cursor_field], None)
            if more_starting_after:
                params["starting_after"] = more_starting_after
            else:
                has_more = False
        else:
            has_more = False
    result: Dict[str, Any] = {
        "object": "list",
        "data_ref": data_key,
        data_key: all_items,
        "has_more": has_more,
    }
    if has_more and more_starting_after:
        result["more_starting_after"] = more_starting_after
    return result


async def _auto_paginate_id(
    ctx: Optional[Context],
    endpoint: str,
    base_params: Dict[str, Any],
    data_key: str,
    limit: int,
    auto_paginate: bool,
    max_items: Optional[int],
) -> Dict[str, Any]:
    if ctx:
        ctx.info(f"Auto-paginate {endpoint} with ID cursor")
    all_items: List[Any] = []
    has_more = True
    params = base_params.copy()
    params["limit"] = limit
    total_fetched = 0
    while has_more and (max_items is None or total_fetched < max_items):
        response = await async_make_voucherify_request("GET", endpoint, params=params, ctx=ctx)
        data = response.json()
        items = _safe_get(data, [data_key], [])
        if max_items is not None:
            items = items[: max_items - total_fetched]
        all_items.extend(items)
        total_fetched += len(items)
        has_more = _safe_get(data, ["has_more"], False)
        cursor = _safe_get(data, ["more_starting_after"], None)
        if not has_more or not auto_paginate:
            break
        if cursor:
            params["starting_after_id"] = cursor
        else:
            has_more = False
    result: Dict[str, Any] = {
        "object": "list",
        "data_ref": data_key,
        data_key: all_items,
        "has_more": has_more,
    }
    if has_more and params.get("starting_after_id"):
        result["more_starting_after"] = params["starting_after_id"]
    return result


async def _auto_paginate_pages(
    ctx: Optional[Context],
    endpoint: str,
    base_params: Dict[str, Any],
    data_key: str,
    limit: int,
    auto_paginate: bool,
    max_items: Optional[int],
    page_param: str = "page"
) -> Dict[str, Any]:
    if not auto_paginate:
        response = await async_make_voucherify_request("GET", endpoint, params=base_params, ctx=ctx)
        return response.json()
    
    if ctx:
        ctx.info(f"Auto-paginate {endpoint} with page-based pagination")
    
    all_items: List[Any] = []
    has_more = True
    params = base_params.copy()
    params["limit"] = limit
    current_page = params.get(page_param) or 1
    params[page_param] = current_page
    total_fetched = 0
    
    while has_more and (max_items is None or total_fetched < max_items):
        response = await async_make_voucherify_request("GET", endpoint, params=params, ctx=ctx)
        data = response.json()
        items = _safe_get(data, [data_key], [])
        
        if not items:
            has_more = False
            break
            
        if max_items is not None:
            items = items[: max_items - total_fetched]
            
        all_items.extend(items)
        total_fetched += len(items)
        
        # Stop if we got fewer items than requested (last page)
        if len(items) < limit:
            has_more = False
            break
            
        # Stop if we've reached max_items
        if max_items is not None and total_fetched >= max_items:
            has_more = True
            break
            
        # Move to next page
        current_page += 1
        params[page_param] = current_page
    
    result: Dict[str, Any] = {
        "object": "list",
        "data_ref": data_key,
        data_key: all_items,
        "has_more": has_more,
    }
    
    return result
