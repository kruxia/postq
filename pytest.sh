#!/bin/sh
set -eu

# Ensure that there is a clean 'testing' database
psql ${DATABASE_URL} -q -c "DROP DATABASE IF EXISTS ${POSTGRES_DB}_test"
psql ${DATABASE_URL} -q -c "CREATE DATABASE ${POSTGRES_DB}_test"

# switch the environment to the test database
DATABASE_URL=${DATABASE_URL}_test

# migrate the test database
alembic upgrade head

# Run the pytest command
pytest $@
