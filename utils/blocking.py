"""Run synchronous database work off the bot's event loop."""

import asyncio


async def run_blocking(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)
