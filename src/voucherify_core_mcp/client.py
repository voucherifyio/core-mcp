# voucherify_client.py
"""
Voucherify API Client

This module provides a centralized way to interact with the Voucherify API.
It handles authentication, request formatting, and error handling.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from fastmcp import Context

from ._version import __version__

# Load environment variables from .env file

()

# Configure module logger
logger = logging.getLogger(__name__)

# Custom exception for Voucherify API errors
class VoucherifyError(Exception):
    """Single exception for all Voucherify API errors with structured data."""

    def __init__(
        self,
        message: str,
        error_type: str,
        details: Optional[str] = None,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.error_type = error_type  # 'http', 'timeout', 'connection', 'unexpected'
        self.details = details
        self.status_code = status_code
        self.response_text = response_text
        self.original_error = original_error
        super().__init__(message)

# Configuration - Use environment variables with fallback to hardcoded values
VOUCHERIFY_API_BASE_URL = os.getenv("VOUCHERIFY_API_BASE_URL", "https://api.voucherify.io")

def _build_auth_headers(ctx: Optional[Context]) -> Dict[str, str]:
    """
    Build Voucherify authentication headers for this request.

    Priority:
    1) Incoming FastMCP HTTP headers: "x-app-id" and "x-app-token" (case-insensitive)
    2) Environment variables: VOUCHERIFY_APP_ID and VOUCHERIFY_APP_TOKEN
    """
    # Defaults from environment
    app_id = os.getenv("VOUCHERIFY_APP_ID")
    app_token = os.getenv("VOUCHERIFY_APP_TOKEN")

    # Try to override from incoming HTTP headers if available on ctx
    try:
        incoming_headers: Optional[Dict[str, Any]] = None

        # Common locations on various FastMCP Context implementations
        if ctx is not None:
            # Starlette-like request on context
            request = getattr(ctx, "request", None)
            if request is not None:
                candidate = getattr(request, "headers", None)
                if candidate:
                    incoming_headers = dict(candidate)

        if incoming_headers:
            # Normalize keys to lower-case for case-insensitive lookup
            lower_headers = {str(k).lower(): v for k, v in incoming_headers.items()}
            app_id = lower_headers.get("x-app-id") or app_id
            app_token = lower_headers.get("x-app-token") or app_token
    except Exception as e:
        # Do not fail header construction due to context inspection issues
        logger.debug(f"Could not read incoming headers from context: {e}")

    return {
        "Content-Type": "application/json",
        "X-App-Id": app_id or "",
        "X-App-Token": app_token or "",
        "X-Voucherify-Channel": f"mcp-core:{__version__}",
    }

def log(ctx: Optional[Context], level: str, msg: str) -> None:
    """
    Log a message either through the context or the module logger.
    
    Args:
        ctx: Optional MCP context for logging
        level: Log level ('info', 'warning', 'error', 'debug')
        msg: Message to log
    """
    if ctx:
        if level == 'info':
            ctx.info(msg)
        elif level == 'warning':
            ctx.warning(msg)
        elif level == 'error':
            ctx.error(msg)
        elif level == 'debug':
            ctx.debug(msg)
    else:
        if level == 'info':
            logger.info(msg)
        elif level == 'warning':
            logger.warning(msg)
        elif level == 'error':
            logger.error(msg)
        elif level == 'debug':
            logger.debug(msg)


async def async_make_voucherify_request(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
    timeout: int = 30
) -> httpx.Response:
    """
    Make authenticated ASYNC request to Voucherify API with proper error handling.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint path (e.g., '/v1/products')
        params: URL query parameters
        json_data: JSON request body
        ctx: MCP context for logging
        timeout: Request timeout in seconds

    Returns:
        httpx.Response object

    Raises:
        VoucherifyError: For all API errors with structured error information
    """
    if not endpoint.startswith('/'):
        endpoint = '/' + endpoint

    url = f"{VOUCHERIFY_API_BASE_URL}{endpoint}"

    log(ctx, 'info', f"Making {method} request to {url}")
    if params:
        log(ctx, 'debug', f"Request params: {params}")

    try:
        headers = _build_auth_headers(ctx)
        if not headers.get("X-App-Id") or not headers.get("X-App-Token"):
            log(ctx, 'warning', "Voucherify credentials are missing or incomplete; request may fail.")

        timeout_conf = httpx.Timeout(timeout)
        async with httpx.AsyncClient(timeout=timeout_conf) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            )

        log(ctx, 'info', f"Response status: {response.status_code}")

        # Raise for HTTP status codes
        response.raise_for_status()
        return response

    except httpx.TimeoutException as e:
        error_msg = f"Request timeout after {timeout} seconds: {str(e)}"
        log(ctx, 'error', error_msg)
        raise VoucherifyError(
            message=error_msg,
            error_type="timeout",
            details=str(e),
            original_error=e
        )
    except httpx.ConnectError as e:
        error_msg = f"Connection error: {str(e)}"
        log(ctx, 'error', error_msg)
        raise VoucherifyError(
            message=error_msg,
            error_type="connection",
            details=str(e),
            original_error=e
        )
    except httpx.HTTPStatusError as e:
        resp = e.response
        error_msg = f"HTTP error {resp.status_code}: {resp.text}"
        log(ctx, 'error', error_msg)
        raise VoucherifyError(
            message=error_msg,
            error_type="http",
            status_code=resp.status_code,
            response_text=resp.text,
            original_error=e
        )
    except httpx.RequestError as e:
        error_msg = f"Unexpected request error: {str(e)}"
        log(ctx, 'error', error_msg)
        raise VoucherifyError(
            message=error_msg,
            error_type="unexpected",
            details=str(e),
            original_error=e
        )
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log(ctx, 'error', error_msg)
        raise VoucherifyError(
            message=error_msg,
            error_type="unexpected",
            details=str(e),
            original_error=e
        )
