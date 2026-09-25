#!/bin/bash
set -euo pipefail
cd /opt/paperclip
database=${1:?Database name required}
[[ "$database" =~ ^[a-zA-Z0-9_]+$ ]] || exit 2
# Only the final SHA256 leaves the pipe; never write table contents to a log.
docker compose exec -T db psql -X -A -t -U paperclip -d "$database" -v ON_ERROR_STOP=1 <<'SQL' | sha256sum | cut -d ' ' -f 1
SELECT format('SELECT %L, COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), %L::jsonb) FROM %I.%I t;', schemaname || '.' || tablename, '[]', schemaname, tablename)
FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY schemaname, tablename
\gexec
SQL
