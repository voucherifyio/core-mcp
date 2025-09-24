"""
Voucherify MCP Server

A Model Context Protocol (MCP) server for integrating with Voucherify services.
Provides read-only tools for accessing campaigns, customers, vouchers, products, and more.
"""

from .server import mcp

__author__ = "Voucherify Dev Team"
__email__ = "support@voucherify.io"

__all__ = [
    "mcp"
]
