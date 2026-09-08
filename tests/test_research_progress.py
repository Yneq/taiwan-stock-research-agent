import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.research import research
from app.progress import measured, sink
from app.schemas.research import ResearchRequest


@pytest.mark.asyncio
async def test_stream_reports_before_result_and_retains_json_contract():
    release = asyncio.Event()

    class Orchestrator:
        model = "test"

        @measured("Gemini")
        async def research(self, question):
            await release.wait()
            return SimpleNamespace(answer="done", traces=[], citations=[])

    request = Request({"type": "http", "headers": [(b"accept", b"application/x-ndjson")],
                       "app": SimpleNamespace(state=SimpleNamespace(orchestrator=Orchestrator()))})
    response = await research(ResearchRequest(question="test"), request, None)
    stream = response.body_iterator
    first = json.loads(await asyncio.wait_for(anext(stream), 1))
    assert first["status"] == "started"
    assert not release.is_set()
    release.set()
    events = [json.loads(event) async for event in stream]
    assert events[-1]["type"] == "result"
    assert events[-1]["data"]["answer"] == "done"
    assert any(e.get("stage") == "Gemini" and e.get("duration_ms") is not None for e in events)
    assert sink.get() is None


@pytest.mark.asyncio
async def test_disconnecting_cancels_research():
    cancelled = asyncio.Event()

    class Orchestrator:
        model = "test"

        async def research(self, question):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    request = Request({"type": "http", "headers": [(b"accept", b"application/x-ndjson")],
                       "app": SimpleNamespace(state=SimpleNamespace(orchestrator=Orchestrator()))})
    response = await research(ResearchRequest(question="test"), request, None)
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_concurrent_progress_is_request_local():
    @measured("test")
    async def operation():
        await asyncio.sleep(0)

    async def run():
        events = []
        token = sink.set(events.append)
        try:
            await operation()
        finally:
            sink.reset(token)
        return events

    a, b = await asyncio.gather(run(), run())
    assert len(a) == len(b) == 2
    assert a is not b
