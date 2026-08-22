import asyncio

import pytest

from app.core.execution import StageTimeoutError, run_with_timeout


def test_run_with_timeout_returns_successful_result() -> None:
    assert asyncio.run(run_with_timeout(asyncio.sleep(0, result="done"), timeout_seconds=1, stage="test")) == "done"


def test_run_with_timeout_raises_typed_timeout() -> None:
    with pytest.raises(StageTimeoutError) as error:
        asyncio.run(run_with_timeout(asyncio.sleep(0.05), timeout_seconds=0.001, stage="test.timeout"))
    assert error.value.stage == "test.timeout"


def test_run_with_timeout_preserves_unexpected_exception() -> None:
    async def fail() -> None:
        raise ValueError("unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        asyncio.run(run_with_timeout(fail(), timeout_seconds=1, stage="test.error"))
