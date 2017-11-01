#!/usr/bin/env bash

set -e

SLEEP_INTERVAL_SEC=${SLEEP_INTERVAL_SEC:-1}

PGHOST=${PGHOST:-localhost}
PGUSER=${PGUSER:-postgres}

until psql -c 'select $$Postgres connection established.$$'; do
  >&2 echo "Postgres is unavailable - sleeping."
  sleep $SLEEP_INTERVAL_SEC
done

>&2 echo "Postgres is up."
