#!/bin/sh
set -eux

DATABASE_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}

until psql $DATABASE_URL -c '\l'; do
    >&2 echo "Waiting for postgres..."
    sleep 1
done

# upgrade the database
sqly migrate $(sqly migrations postq | tail -1)

exec "$@"