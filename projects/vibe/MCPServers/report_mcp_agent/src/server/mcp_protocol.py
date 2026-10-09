# -*- coding: utf-8 -*-
"""MCP STDIO транспорт: NDJSON и Content-Length."""

import json
import logging
import sys
from enum import Enum

from typing import Any, Dict, Optional

logger = logging.getLogger("report_mcp.protocol")


class TransportFormat(str, Enum):
    NDJSON = "ndjson"
    CONTENT_LENGTH = "content-length"


class StdioTransport(object):
    def __init__(self):
        self._format = None  # type: Optional[TransportFormat]
        self._stdin = sys.stdin.buffer
        self._stdout = sys.stdout.buffer

    @property
    def format(self):
        return self._format

    def read_message(self):
        first_line = self._read_line()
        if first_line is None:
            return None

        stripped = first_line.strip()
        if not stripped:
            return self.read_message()

        if stripped.lower().startswith(b"content-length:"):
            self._format = TransportFormat.CONTENT_LENGTH
            body = self._read_content_length_body(first_line, stripped)
        elif stripped.startswith(b"{"):
            self._format = TransportFormat.NDJSON
            body = stripped
        else:
            logger.warning("Неизвестный формат, пробуем NDJSON: %r", stripped[:80])
            self._format = TransportFormat.NDJSON
            body = stripped

        try:
            message = json.loads(body.decode("utf-8"))
            logger.debug(
                "← %s id=%s",
                message.get("method", "response"),
                message.get("id"),
            )
            return message
        except ValueError as exc:
            raise ValueError("Некорректный JSON: {0}".format(exc))

    def write_message(self, message):
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        body_bytes = body.encode("utf-8")
        fmt = self._format or TransportFormat.NDJSON

        if fmt == TransportFormat.CONTENT_LENGTH:
            header = "Content-Length: {0}\r\n\r\n".format(len(body_bytes)).encode("ascii")
            self._stdout.write(header)
            self._stdout.write(body_bytes)
        else:
            self._stdout.write(body_bytes)
            self._stdout.write(b"\n")

        self._stdout.flush()

    def _read_line(self):
        line = self._stdin.readline()
        if not line:
            return None
        return line

    def _read_content_length_body(self, first_line, stripped):
        headers = {}
        key, _, value = stripped.decode("utf-8").partition(":")
        headers[key.strip().lower()] = value.strip()

        while True:
            line = self._read_line()
            if line is None:
                raise EOFError("Неожиданный EOF при чтении заголовков")
            if line in (b"\r\n", b"\n", b""):
                break
            text = line.decode("utf-8").strip()
            if not text:
                break
            if ":" in text:
                h_key, h_val = text.split(":", 1)
                headers[h_key.strip().lower()] = h_val.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise ValueError("Content-Length отсутствует или равен 0")

        body = self._stdin.read(content_length)
        if len(body) < content_length:
            raise EOFError(
                "Ожидалось {0} байт, получено {1}".format(content_length, len(body))
            )
        return body


def make_success(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id, message, code=-32000, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
