from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CASES_PATH = Path(__file__).with_name("cases.json")


def request_research(base_url: str, question: str) -> dict[str, Any]:
    body = json.dumps({"question": question}, ensure_ascii=False).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/research",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def score_case(case: dict[str, Any], response: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    actual_tools = {trace["tool"] for trace in response.get("tool_calls", [])}
    expected_tools = set(case.get("expected_tools", []))
    missing = expected_tools - actual_tools
    if missing:
        failures.append(f"missing tools: {', '.join(sorted(missing))}")
    if case.get("expected_tools") == [] and actual_tools:
        failures.append(f"unexpected tools: {', '.join(sorted(actual_tools))}")
    if case.get("requires_citations") and not response.get("citations"):
        failures.append("missing citations")

    expected_arguments = case.get("expected_arguments", {})
    if expected_arguments:
        all_arguments = [trace.get("arguments", {}) for trace in response.get("tool_calls", [])]
        for key, value in expected_arguments.items():
            if not any(arguments.get(key) == value for arguments in all_arguments):
                failures.append(f"missing argument {key}={value}")

    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic FinScope tool-use evals")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()

    cases = json.loads(CASES_PATH.read_text())
    runnable = [case for case in cases if not case.get("simulated_failure")]
    if arguments.limit:
        runnable = runnable[: arguments.limit]

    passed = 0
    for case in runnable:
        try:
            response = request_research(arguments.base_url, case["question"])
            ok, failures = score_case(case, response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            ok, failures = False, [f"request failed: {exc}"]
        label = "PASS" if ok else "FAIL"
        print(f"[{label}] {case['id']}")
        for failure in failures:
            print(f"       {failure}")
        passed += int(ok)

    total = len(runnable)
    print(f"\nResult: {passed}/{total} ({passed / total:.0%})" if total else "No cases")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
