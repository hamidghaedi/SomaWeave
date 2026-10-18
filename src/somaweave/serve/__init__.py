"""Serving SomaWeave to external agents (MCP). Thin wrappers around the CLI; no interpretation logic."""

from somaweave.serve.mcp_server import SomaWeaveRunner, build_server

__all__ = ["SomaWeaveRunner", "build_server"]
