import asyncio

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.db import make_engine


def test_file_sqlite_engine_never_blocks_on_pool_checkout(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    assert isinstance(engine.pool, NullPool)
    sessions = sessionmaker(bind=engine)

    async def request_holding_session():
        with sessions() as s:
            s.execute(text("select 1"))
            await asyncio.sleep(0.05)

    async def run():
        await asyncio.wait_for(asyncio.gather(*(request_holding_session() for _ in range(40))), timeout=10)

    asyncio.run(run())
