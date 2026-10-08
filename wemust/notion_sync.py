"""Optional Notion sync (no grades).

Overwrites a Notion page's body each run with: last-sync time, today's class
timetable, this week's timetable, recent announcements, in-site messages, and
the personal calendar. Grades are never fetched or written here.

Requires WEMUST_NOTION_PAGE_ID and a Notion integration token (Keychain
`wemust-notion`/`notion`, or WEMUST_NOTION_TOKEN).
"""
import json
import time
import datetime
import urllib.request
import urllib.error

from .config import ConfigError
from .client import WeMustClient

NOTION_API = "https://api.notion.com/v1"
NOTION_VER = "2022-06-28"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _macau_now():
    return datetime.datetime.utcfromtimestamp(time.time() + 8 * 3600)


def _rt(text, link=None, bold=False):
    o = {"type": "text", "text": {"content": (text or "")[:1900]}}
    if link:
        o["text"]["link"] = {"url": link}
    if bold:
        o["annotations"] = {"bold": True}
    return o


def _para(richs):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": richs if isinstance(richs, list) else [_rt(richs)]}}


def _h2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [_rt(text)]}}


def _bullet(richs):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": richs if isinstance(richs, list) else [_rt(richs)]}}


class Notion:
    def __init__(self, token):
        self._h = {"Authorization": "Bearer " + token, "Notion-Version": NOTION_VER,
                   "Content-Type": "application/json"}

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(NOTION_API + path, data=data, headers=self._h, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=30)
            b = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(b) if b.strip() else {})
        except urllib.error.HTTPError as ex:
            b = ex.read().decode("utf-8", "replace")
            try:
                b = json.loads(b)
            except Exception:
                pass
            return ex.code, b

    def list_children(self, block_id):
        out, cursor = [], None
        while True:
            q = "?page_size=100" + (("&start_cursor=" + cursor) if cursor else "")
            st, body = self._req("GET", "/blocks/%s/children%s" % (block_id, q))
            if st != 200:
                raise RuntimeError("notion list_children %s" % st)
            out.extend(body.get("results", []))
            if body.get("has_more"):
                cursor = body.get("next_cursor")
            else:
                break
        return out

    def clear_body(self, page_id):
        for ch in self.list_children(page_id):
            self._req("DELETE", "/blocks/%s" % ch["id"])

    def append(self, block_id, children):
        for i in range(0, len(children), 90):
            st, body = self._req("PATCH", "/blocks/%s/children" % block_id,
                                 {"children": children[i:i + 90]})
            if st != 200:
                raise RuntimeError("notion append %s" % st)


def _timetable_blocks(tt, today_only):
    classes = tt.get("classes", []) if isinstance(tt, dict) else []
    if today_only:
        today = _macau_now().date().isoformat()
        rows = [c for c in classes if c.get("date") == today]
        if not rows:
            return [_para("今天没课")]
        return [_bullet([_rt(_fmt_line(c), link=c.get("onlineUrl"))]) for c in rows]
    if not classes:
        return [_para("本周暂无课表。")]
    bydate = {}
    for c in classes:
        bydate.setdefault(c.get("date", ""), []).append(c)
    out = []
    for d in sorted(bydate):
        try:
            label = WEEKDAYS[datetime.date.fromisoformat(d).weekday()]
        except Exception:
            label = ""
        out.append(_bullet([_rt(("%s %s" % (label, d[5:])).strip(), bold=True)]))
        for c in bydate[d]:
            out.append(_bullet([_rt("  " + _fmt_line(c), link=c.get("onlineUrl"))]))
    return out


def _fmt_line(c):
    span = c.get("start", "")
    if c.get("end"):
        span += "\u2013" + c["end"]
    head = (c.get("courseCode", "") + " " + c.get("courseName", "")).strip()
    line = "  ".join(p for p in [span, head] if p)
    tail = [x for x in [("@" + c["room"]) if c.get("room") else "", c.get("teacher", "")] if x]
    if tail:
        line += "  \u00b7 " + " \u00b7 ".join(tail)
    if c.get("online"):
        line += "  \u00b7 线上"
    return line


def run(cfg):
    token, page_id = cfg.require_notion()
    c = WeMustClient(cfg.require_username(), cfg.get_password)
    try:
        notices = c.get_notices(days=7, limit=30)
        messages = c.get_messages()
        calendar = c.get_calendar(days=7)
        timetable = c.get_timetable(scope="week")
    except Exception as ex:
        _write_failure(token, page_id, "读取 WeMust 数据出错（%s）" % type(ex).__name__)
        print("sync failed:", type(ex).__name__)
        return 1

    stamp = _macau_now().strftime("%Y-%m-%d %H:%M")
    blocks = [_para([_rt("最后同步：%s（澳门时间）" % stamp, bold=True)])]
    blocks.append(_h2("今日课表")); blocks += _timetable_blocks(timetable, True)
    blocks.append(_h2("本周课表")); blocks += _timetable_blocks(timetable, False)
    blocks.append(_h2("WeMust 通知"))
    if notices:
        for a in notices:
            marker = ""
            if a.get("importance") == "VERY_IMPORTANT":
                marker = "‼️ "
            elif a.get("importance") == "IMPORTANT":
                marker = "❗ "
            if a.get("top"):
                marker = "📌 " + marker
            richs = ([_rt(marker)] if marker else []) + [_rt(a.get("title") or "(无标题)",
                                                             link=a.get("url"), bold=True)]
            tail = " · ".join(x for x in [a.get("source", ""),
                                          (a.get("date", "") + " " + a.get("time", "")).strip()] if x)
            if tail:
                richs.append(_rt("  — " + tail))
            if a.get("snippet"):
                richs.append(_rt("  （" + a["snippet"] + "）"))
            blocks.append(_bullet(richs))
    else:
        blocks.append(_para("近 7 天暂无新通知。"))
    blocks.append(_h2("站内消息"))
    if messages.get("current"):
        richs = [_rt(messages["current"].get("title") or "(消息)", bold=True)]
        if messages["current"].get("snippet"):
            richs.append(_rt("  — " + messages["current"]["snippet"]))
        blocks.append(_bullet(richs))
        if (messages.get("unread") or 0) > 1:
            blocks.append(_para("共有 %d 条未读提醒，详见 WeMust。" % messages["unread"]))
    else:
        blocks.append(_para("暂无未读站内消息。"))
    blocks.append(_h2("近 7 天日程"))
    if calendar.get("days"):
        for day in calendar["days"]:
            blocks.append(_bullet([_rt(day.get("date", ""), bold=True)]))
            for ev in day.get("events", []):
                span = ev.get("start", "")
                if ev.get("end"):
                    span += "\u2013" + ev["end"]
                line = " ".join(x for x in [span, ev.get("title", ""),
                                            ("@" + ev["place"]) if ev.get("place") else ""] if x)
                blocks.append(_bullet([_rt("  " + line)]))
    else:
        blocks.append(_para("近 7 天暂无日程。"))

    n = Notion(token)
    n.clear_body(page_id)
    n.append(page_id, blocks)
    print("sync ok: notices=%d, timetable_classes=%d" % (len(notices),
                                                         len(timetable.get("classes", []))))
    return 0


def _write_failure(token, page_id, note):
    try:
        n = Notion(token)
        n.clear_body(page_id)
        n.append(page_id, [
            _para([_rt("最后同步：%s（澳门时间）" % _macau_now().strftime("%Y-%m-%d %H:%M"), bold=True)]),
            _para([_rt("WeMust 今天同步失败：%s" % note)]),
        ])
    except Exception:
        pass
