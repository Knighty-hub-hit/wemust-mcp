import time
import unittest
from unittest.mock import Mock

from wemust.client import WeMustError
from wemust.moodle import AssignmentPage, CoursePage, MoodleClient


class TestMoodle(unittest.TestCase):
    def test_assignment_instructions_images_and_no_submission_panel(self):
        p = AssignmentPage()
        p.feed(
            '<div id="intro"><p>Solve x + 1 = 2</p><img src="/pluginfile.php/2/q.png?token=secret" alt="diagram" />'
            '<script>secret</script><a href="/pluginfile.php/2/q.pdf?forcedownload=1">PDF</a></div>'
            '<div class="submissionstatustable">private grade</div>'
        )
        self.assertIn("Solve x + 1 = 2", p.text)
        self.assertNotIn("private grade", p.text)
        self.assertNotIn("secret", "\n".join(p.text))
        self.assertEqual(len(p.files), 2)
        self.assertNotIn("token", p.files[0]["url"])

    def test_assignment_not_linked_is_rejected(self):
        c = Mock()
        m = MoodleClient(c)
        m.course = Mock(return_value={"activities_and_resources": []})
        with self.assertRaises(WeMustError):
            m.assignment(1, 2)
        c._req.assert_not_called()

    def test_only_view_links_and_no_session_keys(self):
        p = CoursePage()
        p.feed(
            '<script>secret</script><a href="/mod/resource/view.php?id=42&amp;sesskey=secret">Slides</a>'
            '<a href="/mod/assign/view.php?id=9">Assignment</a>'
            '<a href="https://other.test/mod/resource/view.php?id=2">External</a>'
            '<a href="/course/delete.php?id=1">Delete</a>'
        )
        self.assertEqual(len(p.links), 2)
        self.assertEqual(
            p.links[0]["url"], "https://moodle.must.edu.mo/mod/resource/view.php?id=42"
        )
        self.assertNotIn("secret", "\n".join(p.text))

    def test_unenrolled_course_never_fetched(self):
        client = Mock()
        moodle = MoodleClient(client)
        moodle.courses = Mock(return_value={"courses": [{"id": 1}]})
        with self.assertRaises(WeMustError):
            moodle.course(2)
        client._req.assert_not_called()

    def test_mutating_ajax_is_rejected(self):
        client = Mock()
        with self.assertRaises(WeMustError):
            MoodleClient(client).ajax("core_course_delete_courses", {})
        client._req.assert_not_called()

    def test_deadlines_use_macau_timezone_and_omit_action_urls(self):
        moodle = MoodleClient(Mock())
        moodle.ajax = Mock(
            return_value={
                "events": [
                    {
                        "id": 1,
                        "name": "Homework",
                        "timesort": int(time.time()) + 3600,
                        "course": {"fullname": "Programming"},
                        "deleteurl": "secret",
                        "description": "private html",
                    }
                ]
            }
        )
        result = moodle.deadlines(7)
        self.assertTrue(result["events"][0]["time"].endswith("+08:00"))
        self.assertNotIn("deleteurl", result["events"][0])
        self.assertNotIn("description", result["events"][0])


if __name__ == "__main__":
    unittest.main()
