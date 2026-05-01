"""Unit tests for PricingService — pure math, no network calls."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pricing import PricingService


def make_svc(ton_to_stars_rate: float | None = None) -> PricingService:
    settings = MagicMock()
    settings.ton_to_stars_rate = ton_to_stars_rate
    return PricingService(tg=AsyncMock(), settings=settings)


class TestTonToStars:
    def test_basic(self):
        svc = make_svc()
        assert svc.ton_to_stars(1.0, rate=100.0) == 100
        assert svc.ton_to_stars(2.5, rate=100.0) == 250

    def test_truncates_not_rounds(self):
        svc = make_svc()
        assert svc.ton_to_stars(1.999, rate=100.0) == 199
        assert svc.ton_to_stars(0.001, rate=100.0) == 0

    def test_zero_ton(self):
        svc = make_svc()
        assert svc.ton_to_stars(0.0, rate=100.0) == 0

    def test_fractional_rate(self):
        svc = make_svc()
        assert svc.ton_to_stars(1.0, rate=1.5) == 1
        assert svc.ton_to_stars(10.0, rate=1.5) == 15


class TestStarsToTon:
    def test_basic(self):
        svc = make_svc()
        assert svc.stars_to_ton(100, rate=100.0) == pytest.approx(1.0)

    def test_zero_rate_raises(self):
        svc = make_svc()
        with pytest.raises(ValueError, match="rate must be > 0"):
            svc.stars_to_ton(100, rate=0)

    def test_roundtrip(self):
        svc = make_svc()
        rate = 150.0
        ton = 3.5
        stars = svc.ton_to_stars(ton, rate)
        recovered = svc.stars_to_ton(stars, rate)
        # Roundtrip may lose < 1 Star worth due to truncation
        assert recovered <= ton
        assert abs(recovered - ton) < 1 / rate + 1e-9


class TestMakeStarsAmount:
    def test_amount_and_nanos(self):
        svc = make_svc()
        sa = svc.make_stars_amount(50)
        assert sa.amount == 50
        assert sa.nanos == 0

    def test_zero(self):
        svc = make_svc()
        sa = svc.make_stars_amount(0)
        assert sa.amount == 0


class TestSettingsOverride:
    def test_cached_rate_from_settings(self):
        svc = make_svc(ton_to_stars_rate=333.0)
        import asyncio

        rate = asyncio.get_event_loop().run_until_complete(svc.get_stars_per_ton())
        assert rate == 333.0
