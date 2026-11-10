import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram.error import Forbidden, RetryAfter

from bot.notifier import (
    TelegramRateLimiter,
    send_message_rate_limited,
    send_admin_alert,
    _last_admin_alerts,
)
from worker import ScraperWorker


@pytest.mark.anyio
async def test_rate_limiter_interval():
    limiter = TelegramRateLimiter(global_limit_per_second=50.0, per_chat_limit_seconds=0.05)
    start = asyncio.get_event_loop().time()
    await limiter.acquire(chat_id=100)
    await limiter.acquire(chat_id=100)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed >= 0.04


@pytest.mark.anyio
async def test_send_message_rate_limited_success():
    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock(return_value=True)

    result = await send_message_rate_limited(
        bot=bot_mock,
        chat_id=123,
        text="Test message",
    )
    assert result is True
    assert bot_mock.send_message.call_count == 1


@pytest.mark.anyio
async def test_send_message_rate_limited_handles_forbidden():
    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock(side_effect=Forbidden("Forbidden: bot was blocked by the user"))

    result = await send_message_rate_limited(
        bot=bot_mock,
        chat_id=999,
        text="Blocked user message",
    )
    assert result is False
    assert bot_mock.send_message.call_count == 1


@pytest.mark.anyio
async def test_send_message_rate_limited_handles_retry_after():
    bot_mock = MagicMock()
    # First call fails with RetryAfter(retry_after=0.1), second call succeeds
    retry_err = RetryAfter(retry_after=0.1)
    bot_mock.send_message = AsyncMock(side_effect=[retry_err, True])

    result = await send_message_rate_limited(
        bot=bot_mock,
        chat_id=123,
        text="Test retry",
        max_retries=2,
    )
    assert result is True
    assert bot_mock.send_message.call_count == 2


@pytest.mark.anyio
async def test_send_admin_alert_cooldown(monkeypatch):
    monkeypatch.setattr("bot.notifier.TELEGRAM_CHAT_ID", "12345678")
    _last_admin_alerts.clear()

    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock(return_value=True)

    # First alert should succeed
    res1 = await send_admin_alert("Test alert 1", alert_key="test_key", cooldown_seconds=60, bot_or_app=bot_mock)
    assert res1 is True

    # Immediate second alert with same key should be throttled (returns False without sending)
    res2 = await send_admin_alert("Test alert 2", alert_key="test_key", cooldown_seconds=60, bot_or_app=bot_mock)
    assert res2 is False
    assert bot_mock.send_message.call_count == 1


def test_scraper_worker_lifecycle():
    worker = ScraperWorker(interval_minutes=15)
    assert worker.running is True
    assert worker.interval_seconds == 15 * 60
    worker.stop()
    assert worker.running is False

