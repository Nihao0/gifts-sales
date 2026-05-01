"""Shared pytest fixtures."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock

from app.models.base import Base
from app.models.gift import Gift
from app.storage.gift_repo import GiftRepository
from app.storage.job_repo import JobRepository


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def mock_tg():
    client = AsyncMock()
    return client


@pytest_asyncio.fixture
async def gift_repo(db_session):
    return GiftRepository(db_session)


@pytest_asyncio.fixture
async def job_repo(db_session):
    return JobRepository(db_session)


@pytest_asyncio.fixture
async def sample_gift(gift_repo, db_session) -> Gift:
    from app.schemas.gift import GiftCreateSchema

    schema = GiftCreateSchema(
        telegram_gift_id="test_saved_id_001",
        msg_id=42,
        collectible_id=123456,
        slug="CoolRocket-001",
        title="Cool Rocket",
        availability_issued=100,
        availability_total=1000,
        is_for_sale=False,
    )
    gift = await gift_repo.upsert(schema)
    await db_session.commit()
    return gift
