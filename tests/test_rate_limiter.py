import asyncio
import time

import pytest

from vinyl_detective.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_delays_second_call():
    rl = RateLimiter(calls_per_minute=60)  # 1 call/sec
    start = time.monotonic()
    await rl.wait()
    await rl.wait()
    elapsed = time.monotonic() - start
    assert 0.9 <= elapsed <= 1.2


@pytest.mark.asyncio
async def test_rate_limiter_high_rate():
    rl = RateLimiter(calls_per_minute=600)  # 10 calls/sec
    start = time.monotonic()
    for _ in range(5):
        await rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_rate_limiter_no_delay_after_interval():
    rl = RateLimiter(calls_per_minute=6000)  # 0.01s interval
    await rl.wait()
    await asyncio.sleep(0.02)  # wait longer than interval
    start = time.monotonic()
    await rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.01
