from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool

# Максимальная глубина цепочки «кто кого держит»
_MAX_CHAIN_DEPTH = 15

# Общий JOIN: кто держит lock (любая УЗ, без фильтра по usename)
_BLOCKING_JOIN = """
    FROM pg_catalog.pg_stat_activity blocked_act
    JOIN pg_catalog.pg_locks blocked_lk
      ON blocked_act.pid = blocked_lk.pid
     AND NOT blocked_lk.granted
    JOIN pg_catalog.pg_locks blocking_lk
      ON blocking_lk.locktype = blocked_lk.locktype
     AND blocking_lk.database IS NOT DISTINCT FROM blocked_lk.database
     AND blocking_lk.relation IS NOT DISTINCT FROM blocked_lk.relation
     AND blocking_lk.page IS NOT DISTINCT FROM blocked_lk.page
     AND blocking_lk.tuple IS NOT DISTINCT FROM blocked_lk.tuple
     AND blocking_lk.virtualxid IS NOT DISTINCT FROM blocked_lk.virtualxid
     AND blocking_lk.transactionid IS NOT DISTINCT FROM blocked_lk.transactionid
     AND blocking_lk.classid IS NOT DISTINCT FROM blocked_lk.classid
     AND blocking_lk.objid IS NOT DISTINCT FROM blocked_lk.objid
     AND blocking_lk.objsubid IS NOT DISTINCT FROM blocked_lk.objsubid
     AND blocking_lk.pid <> blocked_lk.pid
     AND blocking_lk.granted
    JOIN pg_catalog.pg_stat_activity blocking_act
      ON blocking_act.pid = blocking_lk.pid
    LEFT JOIN pg_catalog.pg_class cls
      ON cls.oid = blocked_lk.relation
    LEFT JOIN pg_catalog.pg_namespace ns
      ON ns.oid = cls.relnamespace
"""

_BLOCKING_SELECT = """
    SELECT
        blocked_act.pid AS blocked_pid,
        blocked_act.usename AS blocked_user,
        blocked_act.datname AS blocked_database,
        blocked_act.application_name AS blocked_application,
        blocked_act.client_addr AS blocked_client_addr,
        blocked_act.state AS blocked_state,
        blocked_act.query_start AS blocked_query_start,
        blocked_act.xact_start AS blocked_xact_start,
        left(blocked_act.query, 2000) AS blocked_query,
        blocking_act.pid AS blocking_pid,
        blocking_act.usename AS blocking_user,
        blocking_act.datname AS blocking_database,
        blocking_act.application_name AS blocking_application,
        blocking_act.client_addr AS blocking_client_addr,
        blocking_act.state AS blocking_state,
        blocking_act.query_start AS blocking_query_start,
        blocking_act.xact_start AS blocking_xact_start,
        left(blocking_act.query, 2000) AS blocking_query,
        blocked_lk.locktype AS locktype,
        blocked_lk.mode AS blocked_lock_mode,
        blocking_lk.mode AS blocking_lock_mode,
        blocked_lk.granted AS blocked_lock_granted,
        ns.nspname AS lock_schema,
        cls.relname AS lock_relation
"""


class FindBlockingTool(BaseTool):
    name = "find_blocking"
    description = (
        "Кто блокирует сессию по pid (любая УЗ: и жертва, и блокирующий могут быть "
        "чужими). Цепочка блокировок, ожидающие lock'и, кого блокирует этот pid. "
        "Без pid — все ожидающие сессии УЗ {0}.".format(settings.GP_BACKEND_USER)
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "pid": {
                    "type": "integer",
                    "description": (
                        "PID процесса, который ждёт (заблокирован). "
                        "Поиск блокирующих без привязки к УЗ запрашивающего."
                    ),
                },
            },
        }

    def execute(self, arguments):
        pid = arguments.get("pid")

        if pid is not None:
            return self._analyze_pid(int(pid))

        rows = self._blocking_pairs_where(
            "blocked_act.usename = :username",
            {"username": settings.GP_BACKEND_USER},
        )
        return {
            "mode": "user_waiters",
            "backend_user": settings.GP_BACKEND_USER,
            "waiting_sessions": rows,
            "count": len(rows),
            "note": (
                "Для чужого pid укажите параметр pid — анализ по любой УЗ."
            ),
        }

    def _analyze_pid(self, pid):
        session_rows = db_manager.fetch_all(
            """
            SELECT
                pid,
                usename,
                datname,
                application_name,
                client_addr,
                backend_start,
                state,
                query_start,
                xact_start,
                left(query, 2000) AS query
            FROM pg_catalog.pg_stat_activity
            WHERE pid = :pid
            """,
            {"pid": pid},
        )

        session = session_rows[0] if session_rows else None

        waiting_locks = db_manager.fetch_all(
            """
            SELECT
                locktype,
                mode,
                granted,
                relation,
                page,
                tuple,
                virtualxid,
                transactionid
            FROM pg_catalog.pg_locks
            WHERE pid = :pid
              AND NOT granted
            ORDER BY locktype, mode
            """,
            {"pid": pid},
        )

        direct_blockers = self._blocking_pairs_where(
            "blocked_act.pid = :pid",
            {"pid": pid},
        )

        blocking_chain = self._build_blocking_chain(pid, direct_blockers)

        blocked_by_target = self._blocking_pairs_where(
            "blocking_act.pid = :pid",
            {"pid": pid},
        )

        summary = self._make_summary(pid, session, direct_blockers, blocking_chain)

        return {
            "mode": "by_pid",
            "target_pid": pid,
            "summary": summary,
            "session": session,
            "session_found": session is not None,
            "ungranted_locks": waiting_locks,
            "direct_blockers": direct_blockers,
            "direct_blocker_count": len(direct_blockers),
            "blocking_chain": blocking_chain,
            "sessions_blocked_by_target_pid": blocked_by_target,
            "blocked_by_target_count": len(blocked_by_target),
            "note": (
                "blocked_user / blocking_user — любые УЗ. "
                "blocking_chain — цепочка вверх (кто держит lock у кого). "
                "Пустой direct_blockers при state=active может означать ожидание "
                "ресурса не через row-lock (сеть, dispatch, external)."
            ),
        }

    @staticmethod
    def _blocking_pairs_where(extra_where, params):
        sql = _BLOCKING_SELECT + _BLOCKING_JOIN + " WHERE " + extra_where
        return db_manager.fetch_all(sql, params)

    @staticmethod
    def _build_blocking_chain(start_pid, direct_blockers):
        chain = []
        seen_blocking_pids = set()

        for row in direct_blockers:
            chain.append(_chain_link(1, row))

        if not direct_blockers:
            return chain

        current_pids = []
        for row in direct_blockers:
            bp = row.get("blocking_pid")
            if bp is not None and bp not in seen_blocking_pids:
                seen_blocking_pids.add(bp)
                current_pids.append(bp)

        level = 2
        while current_pids and level <= _MAX_CHAIN_DEPTH:
            next_pids = []
            for blocked_pid in current_pids:
                upper = FindBlockingTool._blocking_pairs_where(
                    "blocked_act.pid = :pid",
                    {"pid": blocked_pid},
                )
                for row in upper:
                    chain.append(_chain_link(level, row))
                    bp = row.get("blocking_pid")
                    if bp is not None and bp not in seen_blocking_pids:
                        seen_blocking_pids.add(bp)
                        next_pids.append(bp)
            current_pids = next_pids
            level += 1

        return chain

    @staticmethod
    def _make_summary(pid, session, direct_blockers, blocking_chain):
        if not session:
            return (
                "PID {0} не найден в pg_stat_activity "
                "(завершился или нет прав на просмотр).".format(pid)
            )

        state = session.get("state")
        user = session.get("usename")

        if not direct_blockers:
            if waiting_locks_hint(state):
                return (
                    "PID {0} (user={1}, state={2}): в pg_locks нет ungranted lock "
                    "с классическим блокирующим backend — возможно ожидание "
                    "не lock'а (dispatch, I/O, внешний источник).".format(
                        pid, user, state
                    )
                )
            return (
                "PID {0} (user={1}, state={2}): явных блокирующих backend не найдено."
                .format(pid, user, state)
            )

        blockers = []
        for row in direct_blockers:
            blockers.append(
                "pid {0} (user={1})".format(
                    row.get("blocking_pid"),
                    row.get("blocking_user"),
                )
            )

        chain_tail = ""
        if len(blocking_chain) > len(direct_blockers):
            last = blocking_chain[-1]
            chain_tail = (
                " Цепочка до {0} уровней; корневой блокирующий: pid {1} (user={2})."
                .format(
                    last.get("level"),
                    last.get("blocking_pid"),
                    last.get("blocking_user"),
                )
            )

        return (
            "PID {0} (user={1}) блокируют: {2}.{3}"
            .format(pid, user, "; ".join(blockers), chain_tail)
        )


def _chain_link(level, row):
    return {
        "level": level,
        "blocked_pid": row.get("blocked_pid"),
        "blocked_user": row.get("blocked_user"),
        "blocking_pid": row.get("blocking_pid"),
        "blocking_user": row.get("blocking_user"),
        "locktype": row.get("locktype"),
        "lock_schema": row.get("lock_schema"),
        "lock_relation": row.get("lock_relation"),
        "blocked_lock_mode": row.get("blocked_lock_mode"),
        "blocking_lock_mode": row.get("blocking_lock_mode"),
        "blocked_query": row.get("blocked_query"),
        "blocking_query": row.get("blocking_query"),
    }


def waiting_locks_hint(state):
    return state in ("active", "idle in transaction", "waiting")
