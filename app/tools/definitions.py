from __future__ import annotations

from typing import Any


STOCK_SNAPSHOT_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "get_stock_snapshot",
    "description": (
        "取得一檔台灣上市或上櫃股票的即時成交價、開盤價、昨收與今日漲跌幅。"
        "回答任何當下股價數字前都必須使用此工具。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "四位數台股代碼，例如台積電為 2330。",
                "pattern": "^[0-9]{4}$",
            }
        },
        "required": ["stock_code"],
    },
}

REVENUE_HISTORY_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "get_revenue_history",
    "description": "取得指定台股最近數月的月營收，適合用於基本面趨勢整理。",
    "parameters": {
        "type": "object",
        "properties": {
            "stock_code": {
                "type": "string",
                "description": "四位數台股代碼。",
                "pattern": "^[0-9]{4}$",
            },
            "months": {
                "type": "integer",
                "description": "需要的月份數，介於 1 到 24，預設 12。",
                "minimum": 1,
                "maximum": 24,
            },
        },
        "required": ["stock_code"],
    },
}

NEWS_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_news",
    "description": (
        "搜尋最近的公開新聞，回傳標題、媒體、發布時間與來源網址。"
        "使用者詢問近期事件、新聞或股價變動背景時使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "適合新聞搜尋的繁體中文關鍵字。",
                "minLength": 2,
                "maxLength": 120,
            },
            "days": {
                "type": "integer",
                "description": "搜尋最近幾天，介於 1 到 30，預設 7。",
                "minimum": 1,
                "maximum": 30,
            },
            "max_results": {
                "type": "integer",
                "description": "最多回傳幾則新聞，介於 1 到 10，預設 5。",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
}


def build_tools() -> list[dict[str, Any]]:
    return [
        NEWS_SEARCH_TOOL,
        STOCK_SNAPSHOT_TOOL,
        REVENUE_HISTORY_TOOL,
    ]
