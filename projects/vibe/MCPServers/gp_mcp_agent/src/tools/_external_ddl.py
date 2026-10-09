def _fetch_gp_external_ddl(schema, table):
    from gp_mcp_agent.src.db import db_manager

    ext_rows = db_manager.fetch_all(
        """
        SELECT
            e.urilocation,
            e.execlocation,
            e.fmttype,
            e.fmtopts,
            e.options,
            e.command,
            e.encoding,
            e.writable,
            e.rejectlimit,
            e.logerrors
        FROM pg_catalog.pg_exttable e
        JOIN pg_catalog.pg_class c ON e.reloid = c.oid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema
          AND c.relname = :table
        """,
        {"schema": schema, "table": table},
    )
    if not ext_rows:
        return None

    info = ext_rows[0]
    lines = []

    locations = info.get("urilocation") or info.get("execlocation")
    if locations:
        quoted = ["'{0}'".format(loc.replace("'", "''")) for loc in locations]
        lines.append("LOCATION ({0})".format(", ".join(quoted)))

    if info.get("command"):
        lines.append("EXECUTE '{0}' ON ALL".format(
            str(info["command"]).replace("'", "''")
        ))

    fmttype = (info.get("fmttype") or "").strip()
    fmtopts = (info.get("fmtopts") or "").strip()
    if fmttype:
        fmt_map = {"c": "CSV", "t": "TEXT", "b": "CUSTOM"}
        fmt_name = fmt_map.get(fmttype.lower(), fmttype.upper())
        if fmtopts:
            lines.append("FORMAT '{0}' ({1})".format(fmt_name, fmtopts))
        else:
            lines.append("FORMAT '{0}'".format(fmt_name))

    encoding = info.get("encoding")
    if encoding is not None and str(encoding).strip() != "":
        lines.append("ENCODING '{0}'".format(encoding))

    options = info.get("options")
    if options:
        lines.append("OPTIONS ({0})".format(", ".join(options)))

    if info.get("logerrors"):
        lines.append("LOG ERRORS")

    rejectlimit = info.get("rejectlimit")
    if rejectlimit is not None and int(rejectlimit) > 0:
        lines.append("REJECT LIMIT {0}".format(rejectlimit))

    return "\n".join(lines) if lines else None
