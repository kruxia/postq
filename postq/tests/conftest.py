import os

import pytest
from databases import Database


@pytest.fixture
async def database():
    # ensure that all database operations are isolated within each test case by rolling
    # back each test case's transaction
    database = Database(os.getenv('DATABASE_URL'))
    await database.connect()
    tx = await database.transaction()
    yield database
    await tx.rollback()
