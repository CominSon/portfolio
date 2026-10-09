#!/usr/bin/env python3
"""Интеграционный тест MCP STDIO без подключения к БД."""

import json
import subprocess
import sys
from os import path

PROJECT_ROOT = path.abspath(path.join(path.dirname(__file__), "..", ".."))


def _frame_content_length(message):
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = "Content-Length: {0}\r\n\r\n".format(len(body)).encode("ascii")
    return header + body


def _frame_ndjson(message):
    return json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"


def _read_response(proc, use_cl):
    if use_cl:
        headers = {}
        while True:
            line = proc.stdout.readline()
            if not line:
                raise EOFError("EOF")
            text = line.decode("utf-8").strip()
            if not text:
                break
            key, val = text.split(":", 1)
            headers[key.strip().lower()] = val.strip()
        length = int(headers["content-length"])
        body = proc.stdout.read(length)
    else:
        line = proc.stdout.readline()
        body = line

    return json.loads(body.decode("utf-8"))


def _run_handshake(use_cl):
    fmt = "Content-Length" if use_cl else "NDJSON"
    print("=== Тест транспорта: {0} ===".format(fmt))

    proc = subprocess.Popen(
        [sys.executable, "-m", "gp_mcp_agent"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT,
    )

    frame = _frame_content_length if use_cl else _frame_ndjson

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1"},
        },
    }
    proc.stdin.write(frame(init_req))
    proc.stdin.flush()

    init_resp = _read_response(proc, use_cl)
    assert "result" in init_resp, init_resp
    assert init_resp["result"]["protocolVersion"]
    print("  initialize: OK")

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    proc.stdin.write(frame(initialized))
    proc.stdin.flush()

    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    proc.stdin.write(frame(tools_req))
    proc.stdin.flush()

    tools_resp = _read_response(proc, use_cl)
    tools = tools_resp["result"]["tools"]
    names = set(t["name"] for t in tools)
    expected = set([
        "healthcheck", "run_select", "explain",
        "search_tables", "get_columns", "get_table_ddl", "get_function",
        "compare_tables", "list_sessions",
        "find_blocking", "find_functions_for_table", "compare_field_values",
        "build_full_lineage", "get_procedure_schedule",
        "list_owned_objects", "export_query_csv",
    ])
    assert expected <= names, names
    print("  tools/list: OK ({0} tools)".format(len(tools)))

    ping_req = {"jsonrpc": "2.0", "id": 3, "method": "ping"}
    proc.stdin.write(frame(ping_req))
    proc.stdin.flush()
    ping_resp = _read_response(proc, use_cl)
    assert "result" in ping_resp
    print("  ping: OK")

    proc.stdin.close()
    proc.wait(timeout=5)
    print("  завершение: exit={0}\n".format(proc.returncode))


if __name__ == "__main__":
    _run_handshake(use_cl=False)
    _run_handshake(use_cl=True)
    print("Все тесты протокола пройдены.")
