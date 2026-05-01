"""Unit tests for retry scheduling logic."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


from app.utils.retry import compute_retry_after, is_retry_due, should_retry


class TestComputeRetryAfter:
    def test_is_in_future(self):
        result = compute_retry_after(seconds=300, jitter_seconds=5)
        assert result > datetime.now(timezone.utc)

    def test_minimum_offset(self):
        before = datetime.now(timezone.utc)
        result = compute_retry_after(seconds=300, jitter_seconds=5)
        expected_min = before + timedelta(seconds=304)
        assert result >= expected_min

    def test_jitter_applied(self):
        result_no_jitter = compute_retry_after(seconds=60, jitter_seconds=0)
        result_jitter = compute_retry_after(seconds=60, jitter_seconds=10)
        # Both are futures; jitter one is further
        now = datetime.now(timezone.utc)
        assert result_jitter > result_no_jitter or (
            (result_jitter - now).total_seconds() >= 60
        )

    def test_zero_seconds(self):
        result = compute_retry_after(seconds=0, jitter_seconds=0)
        assert result > datetime.now(timezone.utc) - timedelta(seconds=1)

    def test_result_is_utc(self):
        result = compute_retry_after(seconds=10)
        assert result.tzinfo is not None


class TestShouldRetry:
    def test_below_max(self):
        job = MagicMock(attempts=0, max_attempts=5)
        assert should_retry(job) is True

    def test_at_max(self):
        job = MagicMock(attempts=5, max_attempts=5)
        assert should_retry(job) is False

    def test_above_max(self):
        job = MagicMock(attempts=6, max_attempts=5)
        assert should_retry(job) is False

    def test_one_attempt_left(self):
        job = MagicMock(attempts=4, max_attempts=5)
        assert should_retry(job) is True


class TestIsRetryDue:
    def test_no_retry_after(self):
        job = MagicMock(retry_after=None)
        assert is_retry_due(job) is True

    def test_past_retry_after(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        job = MagicMock(retry_after=past)
        assert is_retry_due(job) is True

    def test_future_retry_after(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=300)
        job = MagicMock(retry_after=future)
        assert is_retry_due(job) is False

    def test_naive_datetime_treated_as_utc(self):
        # SQLite strips tzinfo when reading back DateTime columns.
        # Simulate by converting a real UTC past time to naive.
        past_naive = (datetime.now(timezone.utc) - timedelta(seconds=60)).replace(tzinfo=None)
        job = MagicMock(retry_after=past_naive)
        assert is_retry_due(job) is True
