"""Read-only Moodle integration, sharing the student's CAS session."""

import datetime
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from .client import WeMustError

BASE = "https://moodle.must.edu.mo"


class AssignmentPage(HTMLParser):
    """Read teacher instructions and attachments, excluding submission/grade panels."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.text = []
        self.files = []
        self.found = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        active = self.stack[-1][1] if self.stack else False
        active = (
            active
            or a.get("id") == "intro"
            or bool(
                {"activity-description", "introattachments"}
                & set(a.get("class", "").split())
            )
        )
        if tag in ("script", "style"):
            active = False
        if active:
            self.found = True
            url = (
                a.get("src") if tag == "img" else a.get("href") if tag == "a" else None
            )
            if url:
                p = urlsplit(urljoin(BASE, url))
                if (
                    p.scheme == "https"
                    and p.netloc == "moodle.must.edu.mo"
                    and p.path.startswith("/pluginfile.php/")
                ):
                    self.files.append(
                        {
                            "url": BASE + p.path,
                            "kind": "image" if tag == "img" else "attachment",
                            "name": a.get("alt") or p.path.rsplit("/", 1)[-1],
                        }
                    )
            if tag == "img" and a.get("alt"):
                self.text.append("[Image: " + a["alt"] + "]")
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append((tag, active))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if self.stack and self.stack[-1][1] and text.strip():
            self.text.append(text.strip())


class CoursePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.anchor = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "a":
            self.anchor = [urljoin(BASE, attrs.get("href", "")), []]

    def handle_data(self, text):
        if not self.skip and text.strip():
            self.text.append(text.strip())
            if self.anchor is not None:
                self.anchor[1].append(text.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "a" and self.anchor is not None:
            url, parts = self.anchor
            p = urlsplit(url)
            if p.scheme == "https" and p.netloc == "moodle.must.edu.mo":
                # Only resource/activity viewing links; never actions or session keys.
                if re.fullmatch(r"/mod/[a-z]+/view.php", p.path):
                    item_id = parse_qs(p.query).get("id", [""])[0]
                    if item_id.isdigit():
                        self.links.append(
                            {
                                "name": " ".join(parts),
                                "url": BASE + p.path + "?id=" + item_id,
                            }
                        )
            self.anchor = None


class MoodleClient:
    def __init__(self, client):
        self.client = client
        self._key = None

    def ensure_session(self):
        if self._key:
            return
        self.client.login()
        r = self.client._req(
            "https://login.must.edu.mo/login?service="
            "https%3A%2F%2Fmoodle.must.edu.mo%2Flogin%2Findex.php"
        )
        page = r.read().decode("utf-8", "replace")
        m = re.search(r'"sesskey"\s*:\s*"([^"]+)"', page)
        if urlsplit(r.geturl()).netloc != "moodle.must.edu.mo" or not m:
            raise WeMustError("Moodle SSO did not establish a session.")
        self._key = m.group(1)

    def ajax(self, method, args):
        allowed = {
            "core_course_get_enrolled_courses_by_timeline_classification",
            "core_calendar_get_action_events_by_timesort",
        }
        if method not in allowed:
            raise WeMustError("Moodle method is not in the read-only allowlist.")
        self.ensure_session()
        r = self.client._req(
            BASE + "/lib/ajax/service.php?sesskey=" + self._key,
            data=json.dumps(
                [{"index": 0, "methodname": method, "args": args}]
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        result = json.loads(r.read())[0]
        if result.get("error"):
            raise WeMustError("Moodle read interface returned an error: " + method)
        return result["data"]

    def courses(self):
        courses = []
        for offset in range(0, 1000, 100):
            data = self.ajax(
                "core_course_get_enrolled_courses_by_timeline_classification",
                {"classification": "all", "limit": 100, "offset": offset},
            )
            batch = data.get("courses", [])
            courses.extend(
                {
                    k: c.get(k)
                    for k in ("id", "fullname", "shortname", "startdate", "enddate")
                }
                for c in batch
            )
            if len(batch) < 100:
                return {"courses": courses, "truncated": False}
        return {"courses": courses, "truncated": True}

    def course(self, course_id):
        course_id = int(course_id)
        if course_id <= 0:
            raise WeMustError("course_id must be positive.")
        # Restrict reading to courses returned for the authenticated student.
        if course_id not in {c["id"] for c in self.courses()["courses"]}:
            raise WeMustError("Course is not in your enrolled course list.")
        r = self.client._req(BASE + "/course/view.php?id=" + str(course_id))
        if urlsplit(r.geturl()).path.startswith("/login"):
            raise WeMustError("Moodle session expired; restart the MCP server.")
        parser = CoursePage()
        parser.feed(r.read().decode("utf-8", "replace"))
        text = "\n".join(parser.text)
        return {
            "course_id": course_id,
            "url": BASE + "/course/view.php?id=" + str(course_id),
            "page_text": text[:40000],
            "truncated": len(text) > 40000,
            "activities_and_resources": list(
                {x["url"]: x for x in parser.links}.values()
            ),
            "note": "Visible course page text and resource links; file contents are not downloaded.",
        }

    def assignment(self, course_id, activity_id):
        activity_id = int(activity_id)
        if activity_id <= 0:
            raise WeMustError(
                "activity_id must be positive (the id in /mod/assign/view.php?id=...)."
            )
        url = BASE + "/mod/assign/view.php?id=" + str(activity_id)
        course = self.course(course_id)
        item = next(
            (x for x in course["activities_and_resources"] if x["url"] == url), None
        )
        if item is None:
            raise WeMustError(
                "Assignment link was not found on your enrolled course page."
            )
        r = self.client._req(url)
        if (
            urlsplit(r.geturl()).netloc != "moodle.must.edu.mo"
            or urlsplit(r.geturl()).path != "/mod/assign/view.php"
        ):
            raise WeMustError(
                "Assignment page redirected; unable to read instructions."
            )
        parser = AssignmentPage()
        parser.feed(r.read().decode("utf-8", "replace"))
        text = "\n".join(parser.text)
        return {
            "course_id": int(course_id),
            "activity_id": activity_id,
            "name": item["name"],
            "url": url,
            "instructions": text[:60000],
            "truncated": len(text) > 60000,
            "description_region_found": parser.found,
            "files_and_images": list({x["url"]: x for x in parser.files}.values()),
            "note": "Teacher instructions only. Images and attachment contents are not extracted. Empty instructions do not prove no questions exist.",
        }

    def deadlines(self, days=30):
        days = int(days)
        if not 1 <= days <= 365:
            raise WeMustError("days must be between 1 and 365.")
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        data = self.ajax(
            "core_calendar_get_action_events_by_timesort", {"limitnum": 30}
        )
        events = []
        zone = datetime.timezone(datetime.timedelta(hours=8))
        for e in data.get("events", []):
            t = e.get("timesort") or e.get("timestart")
            if not t or not now <= int(t) <= now + days * 86400:
                continue
            events.append(
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "course": (e.get("course") or {}).get("fullname"),
                    "time": datetime.datetime.fromtimestamp(t, zone).isoformat()
                    if t
                    else None,
                    "event_type": e.get("eventtype"),
                    "activity_type": e.get("modulename"),
                }
            )
        return {
            "days": days,
            "timezone": "Asia/Macau",
            "events": events,
            "possibly_truncated": len(data.get("events", [])) >= 30,
            "note": "Moodle action-calendar events only; not all assignments necessarily appear here.",
        }
