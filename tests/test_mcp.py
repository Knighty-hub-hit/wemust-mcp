"""Offline tests: the MCP server answers initialize and tools/list with no network.

Run with:  python -m unittest discover -s tests   (or: python tests/test_mcp.py)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wemust.config import Config
from wemust.mcp_server import ServerState, handle


def _state(env):
    return ServerState(Config(env=env))


class TestMcpOffline(unittest.TestCase):
    def test_initialize(self):
        st = _state({})
        resp = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, st)
        self.assertEqual(resp["id"], 1)
        self.assertIn("protocolVersion", resp["result"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "wemust-mcp")

    def test_initialized_notification_has_no_response(self):
        st = _state({})
        resp = handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, st)
        self.assertIsNone(resp)

    def test_tools_list_without_grades(self):
        st = _state({"WEMUST_USERNAME": "sample"})
        resp = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, st)
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(
            set(names),
            {
                "get_timetable",
                "get_notices",
                "get_messages",
                "get_calendar",
                "get_moodle_courses",
                "get_moodle_course",
                "get_moodle_deadlines",
                "get_moodle_assignment",
                "get_notice_detail",
                "get_notice_attachment_text",
                "get_notice_attachment_page",
            },
        )
        self.assertNotIn("get_grades", names)

    def test_tools_list_with_grades_enabled(self):
        st = _state({"WEMUST_USERNAME": "sample", "WEMUST_ENABLE_GRADES": "1"})
        resp = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, st)
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertIn("get_grades", names)

    def test_unknown_method(self):
        st = _state({})
        resp = handle({"jsonrpc": "2.0", "id": 4, "method": "no/such"}, st)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_ping(self):
        st = _state({})
        resp = handle({"jsonrpc": "2.0", "id": 5, "method": "ping"}, st)
        self.assertEqual(resp["result"], {})


if __name__ == "__main__":
    unittest.main()
