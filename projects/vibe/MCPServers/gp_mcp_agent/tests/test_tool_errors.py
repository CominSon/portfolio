import json
import unittest

from gp_mcp_agent.src.server.tool_registry import ToolRegistry
from gp_mcp_agent.src.utils.tool_errors import build_tool_error_payload, short_db_message


class TestToolErrors(unittest.TestCase):
    def test_short_db_message(self):
        exc = Exception(
            "(psycopg2.errors.UndefinedColumn) column \"relowner\" does not exist\n"
            "LINE 1: ... pg_namespace WHERE relowner =..."
        )
        short = short_db_message(exc)
        self.assertIn("relowner", short)

    def test_call_error_json(self):
        reg = ToolRegistry()
        result = reg.call_error(
            "run_select",
            "column relowner does not exist",
            error_type="DatabaseError",
            hint="use list_owned_objects",
        )
        self.assertTrue(result.get("isError"))
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["tool"], "run_select")
        self.assertEqual(payload["hint"], "use list_owned_objects")


    def test_call_error_with_retry_meta(self):
        reg = ToolRegistry()
        result = reg.call_error(
            "run_select",
            "operator does not exist: jsonb @? unknown",
            error_type="DatabaseError",
            hint="Перепишите SQL без @?",
            retry_meta={
                "retry_recommended": True,
                "agent_retry": {"max_attempts": 3, "instruction": "retry"},
                "suggested_sql_note": "use ->>",
            },
        )
        payload = json.loads(result["content"][0]["text"])
        self.assertTrue(result.get("isError"))
        self.assertTrue(payload["retry_recommended"])
        self.assertEqual(payload["agent_retry"]["max_attempts"], 3)
        self.assertIn("suggested_sql_note", payload)


if __name__ == "__main__":
    unittest.main()
