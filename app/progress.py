"""Request-local timing; never record prompts, credentials or tool arguments."""
import time
from functools import wraps
from contextvars import ContextVar
from contextlib import asynccontextmanager

sink = ContextVar("research_progress", default=None)


def measured(name):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            async with stage(name):
                return await function(*args, **kwargs)
        return wrapped
    return decorate


def emit(**event):
    callback = sink.get()
    if callback:
        callback(event)


@asynccontextmanager
async def stage(name):
    started = time.perf_counter()
    emit(stage=name, status="started")
    try:
        yield
    except BaseException:
        emit(stage=name, status="error", duration_ms=round((time.perf_counter()-started)*1000))
        raise
    else:
        emit(stage=name, status="completed", duration_ms=round((time.perf_counter()-started)*1000))
