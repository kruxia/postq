import os

import asyncpg
import pytest


@pytest.fixture
async def database(scope='session'):
    # ensure that all database operations are isolated within each test case by rolling
    # back each test case's transaction
    database = await asyncpg.create_pool(
        dsn=os.getenv('DATABASE_URL'), min_size=1, max_size=1
    )
    yield database


@pytest.fixture
async def connection(database):
    connection = await database.acquire()
    trx = connection.transaction()
    await trx.start()
    yield connection
    await trx.rollback()
