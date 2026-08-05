from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from app.clients.stocktracker import StockTrackerClient


EXPECTED_TOOLS = {"get_stock_snapshot", "get_revenue_history"}


async def check_connection(stock_code: str) -> None:
    load_dotenv()
    base_url = os.getenv("STOCKTRACKER_BASE_URL", "http://localhost:8080").rstrip("/")
    api_key = os.getenv("STOCKTRACKER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("STOCKTRACKER_API_KEY is required in .env")

    client = StockTrackerClient(base_url, api_key)
    try:
        tool_names = await client.list_tool_names()
        missing = EXPECTED_TOOLS.difference(tool_names)
        if missing:
            raise RuntimeError(f"MCP server is missing tools: {sorted(missing)}")

        snapshot = await client.get_snapshot(stock_code)
        print(f"MCP tools: {', '.join(sorted(tool_names))}")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the Python MCP Client against the Java StockTracker MCP Server."
    )
    parser.add_argument("--stock-code", default="2330")
    args = parser.parse_args()
    asyncio.run(check_connection(args.stock_code))


if __name__ == "__main__":
    main()
