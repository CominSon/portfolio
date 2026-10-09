"""Совместимые запросы к pg_stat_activity (старый и новый Greenplum)."""

from gp_mcp_agent.src.db import db_manager

_HAS_WAIT_EVENTS = None


def _probe_wait_event_columns():
    global _HAS_WAIT_EVENTS
    if _HAS_WAIT_EVENTS is not None:
        return _HAS_WAIT_EVENTS
    rows = db_manager.fetch_all(
        """
        SELECT 1
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'pg_catalog'
          AND c.relname = 'pg_stat_activity'
          AND a.attname = 'wait_event_type'
          AND a.attnum > 0
          AND NOT a.attisdropped
        LIMIT 1
        """
    )
    _HAS_WAIT_EVENTS = bool(rows)
    return _HAS_WAIT_EVENTS


def fetch_user_sessions(username, state_filter_sql):
    wait_cols = (
        "wait_event_type,\n                wait_event,"
        if _probe_wait_event_columns()
        else "NULL::text AS wait_event_type,\n                NULL::text AS wait_event,"
    )

    sql = """
        SELECT
            pid,
            state,
            usename,
            datname,
            query_start,
            xact_start,
            application_name,
            client_addr,
            {wait_cols}
            left(query, 2000) AS query
        FROM pg_catalog.pg_stat_activity
        WHERE usename = :username
          AND pid <> pg_catalog.pg_backend_pid()
          AND {state_filter}
        ORDER BY state, query_start NULLS LAST
    """.format(wait_cols=wait_cols, state_filter=state_filter_sql)

    rows = db_manager.fetch_all(sql, {"username": username})
    source = "pg_stat_activity(with_wait_events)" if _HAS_WAIT_EVENTS else "pg_stat_activity(legacy)"
    return rows, source
