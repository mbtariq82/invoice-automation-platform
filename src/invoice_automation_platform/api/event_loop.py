"""Uvicorn loop factory compatible with psycopg on Windows."""

import asyncio
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()

    from uvicorn.loops.auto import auto_loop_factory

    return auto_loop_factory(use_subprocess=False)()
