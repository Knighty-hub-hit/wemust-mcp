"""WeMust client: CAS login + read-only signed API access.

Targets the public MUST WeMust student portal and its sub-apps. The login
replicates what the browser does (RSA-encrypted credentials to the CAS server),
using only the Python standard library. All calls are read-only (GET, plus the
single POST that login itself requires).

IMPORTANT: this never prints the password, cookies, or tokens.
"""
import os
import re
import ssl
import json
import base64
import hashlib
import datetime
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar

# --- MUST infrastructure (public hostnames, not personal data) ---
LOGIN = "https://login.must.edu.mo"
STUDENT = "https://student-wmweb.must.edu.mo"

TRANSCRIPT_HOST = "transcript-web.must.edu.mo"
TRANSCRIPT_BASE = "/x-transcript-api"
TRANSCRIPT_SALT = "wm-transcript"
TRANSCRIPT_SVC = "https://transcript-web.must.edu.mo/transcript-inquiry"

TT_HOST = "classtimetable-coes-wmweb.must.edu.mo"
TT_BASE = "/x-class-timetable-api"
TT_SALT = "wm_eas_course_enrollment"
TT_SVC = "https://classtimetable-coes-wmweb.must.edu.mo/my-class-timetable-student"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17 Safari/605.1.15")


class WeMustError(Exception):
    pass


class LoginFailed(WeMustError):
    pass


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _parse_spki(b64):
    """Parse an X.509 SubjectPublicKeyInfo (RSA) and return (n, e)."""
    d = base64.b64decode(b64)
    i = 0

    def rdlen(data, i):
        l = data[i]; i += 1
        if l & 0x80:
            n = l & 0x7f
            l = int.from_bytes(data[i:i + n], "big"); i += n
        return l, i

    assert d[i] == 0x30; i += 1; _, i = rdlen(d, i)
    assert d[i] == 0x30; i += 1; al, i = rdlen(d, i); i += al
    assert d[i] == 0x03; i += 1; _, i = rdlen(d, i)
    assert d[i] == 0x00; i += 1
    assert d[i] == 0x30; i += 1; _, i = rdlen(d, i)
    assert d[i] == 0x02; i += 1; nl, i = rdlen(d, i)
    n = int.from_bytes(d[i:i + nl], "big"); i += nl
    assert d[i] == 0x02; i += 1; el, i = rdlen(d, i)
    e = int.from_bytes(d[i:i + el], "big"); i += el
    return n, e


def _rsa_pkcs1_b64(n, e, msg):
    """RSA/ECB/PKCS1 v1.5 encrypt (JSEncrypt-compatible), stdlib only."""
    k = (n.bit_length() + 7) // 8
    m = msg.encode("utf-8")
    ps_len = k - 3 - len(m)
    if ps_len < 8:
        raise ValueError("message too long for RSA key")
    ps = bytearray()
    while len(ps) < ps_len:
        b = os.urandom(1)[0]
        if b:
            ps.append(b)
    eb = b"\x00\x02" + bytes(ps) + b"\x00" + m
    c = pow(int.from_bytes(eb, "big"), e, n)
    return base64.b64encode(c.to_bytes(k, "big")).decode("ascii")


def _strip_html(s):
    if not s:
        return ""
    import html as _html
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = _html.unescape(s).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _hhmm(t):
    m = re.search(r"(\d{1,2}):(\d{2})", str(t or ""))
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2))) if m else ""


def _datepart(t):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(t or ""))
    return m.group(0) if m else (str(t or "")[:10])


class WeMustClient:
    """A logged-in, read-only WeMust session for a single user's own account."""

    def __init__(self, username, password_provider):
        """password_provider: zero-arg callable returning the password string."""
        self._username = username
        self._password_provider = password_provider
        self._logged_in = False
        self._apps = set()
        self.cj = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=ctx),
        )
        self.op.addheaders = []

    # --- low level ---
    def _req(self, url, data=None, headers=None, method=None):
        h = {"User-Agent": UA}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        return self.op.open(req, timeout=30)

    def login(self):
        """Log in through CAS. Never retries on failure (5 wrong passwords lock
        the account for 1 hour)."""
        if self._logged_in:
            return
        pw = self._password_provider()  # in-memory only
        service = urllib.parse.quote(STUDENT + "/", safe="")
        r = self._req(LOGIN + "/login?service=" + service)
        html = r.read().decode("utf-8", "replace")
        m_exec = re.search(r'name="execution"\s+value="([^"]+)"', html)
        m_key = re.search(r'publicKey\s*=\s*"([^"]+)"', html)
        if not m_exec or not m_key:
            raise LoginFailed("could not parse CAS login page")
        has_captcha = ('name="capcha"' in html and 'capcha?r=' in html
                       and 'id="capchaInput"' in html)
        if has_captcha:
            # A captcha means earlier failures; do NOT submit (avoid lockout).
            raise LoginFailed("CAS is showing a captcha; refusing to submit to avoid lockout.")
        n, e = _parse_spki(m_key.group(1))
        enc_user = _rsa_pkcs1_b64(n, e, self._username)
        enc_pw = _rsa_pkcs1_b64(n, e, pw)
        del pw
        form = urllib.parse.urlencode({
            "username": enc_user, "password": enc_pw, "capcha": "",
            "privacyPolicyId": "on", "execution": m_exec.group(1),
            "_eventId": "submit", "geolocation": "",
        }).encode()
        r2 = self._req(LOGIN + "/login?service=" + service, data=form,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
        r2.read()
        if self._initial_state().get("appLoggedIn") is not True:
            # Single attempt only. Caller must not loop.
            raise LoginFailed("login did not establish a session (wrong credentials?). "
                              "Not retrying to avoid account lockout.")
        self._logged_in = True

    # --- signed requests ---
    def _sign(self, params, salt):
        p = {k: v for k, v in (params or {}).items() if v is not None}
        p["lang"] = "zh_MO"
        p["nonce"] = _md5(os.urandom(16).hex())
        pairs = sorted((k, (v[0] if isinstance(v, (list, tuple)) else v)) for k, v in p.items())
        p["signature"] = _md5("".join("%s=%s" % (k, v) for k, v in pairs) + salt)
        return p

    def _get_json(self, url):
        try:
            r = self._req(url, headers={"X-Requested-With": "XMLHttpRequest",
                                        "Accept": "application/json"})
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body.strip().startswith(("{", "[")) else body)
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8", "replace")
            try:
                body = json.loads(body)
            except Exception:
                pass
            return ex.code, body

    def api(self, base, path, salt, params=None):
        """Signed GET against the main student portal host."""
        q = urllib.parse.urlencode(self._sign(params, salt), doseq=True)
        return self._get_json(STUDENT + base + path + "?" + q)

    def _ensure_app(self, service_url):
        host = urllib.parse.urlparse(service_url).netloc
        if host in self._apps:
            return
        self._req(service_url)  # CAS single-sign-on sets this sub-app's session cookie
        self._apps.add(host)

    def sub_get(self, host, base, path, salt, params=None, service_url=None):
        """Signed GET against a sub-app host (reusing the CAS SSO session)."""
        if service_url:
            self._ensure_app(service_url)
        q = urllib.parse.urlencode(self._sign(params, salt), doseq=True)
        url = "https://" + host + base.rstrip("/") + "/" + path.lstrip("/") + "?" + q
        return self._get_json(url)

    def _initial_state(self):
        st, body = self.api("/x-self-api", "/initial-state", "oa-home")
        return body.get("model", {}) if isinstance(body, dict) else {}

    # --- high level, structured, read-only features ---
    def get_notices(self, days=7, limit=20):
        self.login()
        st, body = self.api("/x-info-portal-api", "/article-portals", "wm-info-portal",
                            {"offsetStart": 1, "maxPageItems": max(1, min(limit, 50))})
        articles = body.get("data", []) if isinstance(body, dict) else []
        st2, tbody = self.api("/x-info-portal-api", "/article-portals/top-notice", "wm-info-portal")
        tmodel = tbody.get("model") if isinstance(tbody, dict) else None
        tops = tmodel if isinstance(tmodel, list) else ([tmodel] if isinstance(tmodel, dict) else [])
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        seen, top_ids = {}, set()
        for t in tops:
            if isinstance(t, dict) and t.get("id") is not None:
                seen[t["id"]] = t; top_ids.add(t["id"])
        for a in articles:
            if not isinstance(a, dict):
                continue
            d = _datepart(a.get("postDate"))
            try:
                keep = datetime.date.fromisoformat(d) >= cutoff
            except Exception:
                keep = True
            if keep and a.get("id") not in seen:
                seen[a["id"]] = a
        out = []
        for a in sorted(seen.values(),
                        key=lambda x: (_datepart(x.get("postDate")), _hhmm(x.get("postTime"))),
                        reverse=True):
            import html as _html
            url = None
            if a.get("id") is not None and a.get("category"):
                url = ("https://infoportal-web.must.edu.mo/detail?id=%s&category=%s&locale=zh_MO"
                       % (a["id"], urllib.parse.quote(str(a["category"]))))
            out.append({
                "id": a.get("id"),
                "title": _html.unescape(a.get("title") or ""),
                "source": _html.unescape(a.get("sourceGroupName") or ""),
                "date": _datepart(a.get("postDate")),
                "time": _hhmm(a.get("postTime")),
                "importance": a.get("importanceLevel") or "NORMAL",
                "top": a.get("id") in top_ids,
                "url": url,
                "snippet": _strip_html(a.get("content"))[:120],
            })
        return out

    def get_messages(self):
        self.login()
        st, body = self.api("/x-student-api", "/message-webs/remind/popup/pc", "oa-home")
        model = body.get("model") if isinstance(body, dict) else None
        if not model:
            return {"unread": 0, "current": None}
        import html as _html
        return {
            "unread": model.get("remindCount") or 0,
            "current": {
                "title": _html.unescape(model.get("title") or ""),
                "snippet": _strip_html(model.get("cnContent") or model.get("enContent"))[:200],
            },
        }

    def get_calendar(self, days=7):
        self.login()
        today = datetime.date.today()
        start = today.isoformat()
        end = (today + datetime.timedelta(days=max(0, days - 1))).isoformat()
        st, body = self.api("/x-schedule-api", "/events/events/by-date", "wm_oa_schedule_new",
                            {"startTime": start, "endTime": end, "dataSource": 1})
        model = body.get("model") if isinstance(body, dict) else None
        out = []
        if isinstance(model, list):
            for day in model:
                evs = day.get("events", []) if isinstance(day, dict) else []
                items = []
                for ev in evs:
                    items.append({
                        "start": _hhmm(ev.get("startTime") or ev.get("tempStartTime")),
                        "end": _hhmm(ev.get("endTime") or ev.get("tempEndTime")),
                        "title": _strip_html(ev.get("title") or ev.get("subject") or ""),
                        "place": _strip_html(ev.get("address") or ev.get("place") or ""),
                    })
                if items:
                    out.append({"date": _datepart(day.get("date")), "events": items})
        return {"start": start, "end": end, "days": out}

    # --- timetable (class schedule) ---
    def _tt_weekday(self, date):
        return self.sub_get(TT_HOST, TT_BASE, "/lessons/terms/coes/dates/%s/week-day" % date,
                            TT_SALT, {"date": date}, service_url=TT_SVC)

    def _tt_student(self, term_code, start_date, end_date):
        return self.sub_get(TT_HOST, TT_BASE, "/lessons/student-webs", TT_SALT,
                            {"termCode": term_code, "startDate": start_date, "endDate": end_date},
                            service_url=TT_SVC)

    @staticmethod
    def _fmt_class(row):
        return {
            "date": _datepart(row.get("lessonDate")),
            "start": _hhmm(row.get("lessonStartTime")),
            "end": _hhmm(row.get("lessonEndTime")),
            "courseCode": (row.get("courseCode") or "").strip(),
            "courseName": _strip_html(row.get("courseName") or row.get("courseEnName") or ""),
            "room": _strip_html(row.get("roomChnDesc") or row.get("classroomCode") or ""),
            "teacher": _strip_html(row.get("teacherName") or row.get("teacherEnName") or ""),
            "online": bool(row.get("online")),
            "onlineUrl": row.get("onlineUrl") or None,
        }

    def get_timetable(self, scope="week", start=None, end=None):
        """scope: 'today' | 'week' | 'range' (range requires start & end, YYYY-MM-DD)."""
        self.login()
        d = datetime.date.today()
        if scope == "range":
            if not (start and end):
                raise WeMustError("scope='range' requires start and end (YYYY-MM-DD)")
            st, wd = self._tt_weekday(start)
            info = wd.get("model") if isinstance(wd, dict) else {}
            term = info.get("clIntake") if isinstance(info, dict) else None
            s, e = start, end
        else:
            st, wd = self._tt_weekday(d.isoformat())
            info = wd.get("model") if isinstance(wd, dict) else {}
            term = info.get("clIntake") if isinstance(info, dict) else None
            s = (info.get("clStartDate") if isinstance(info, dict) else None) \
                or (d - datetime.timedelta(days=d.weekday())).isoformat()
            e = (info.get("clEndDate") if isinstance(info, dict) else None) \
                or (d + datetime.timedelta(days=6 - d.weekday())).isoformat()
        st2, body = self._tt_student(term, s, e)
        rows = body.get("model") if isinstance(body, dict) else None
        rows = rows if isinstance(rows, list) else []
        classes = [self._fmt_class(r) for r in rows if isinstance(r, dict)]
        if scope == "today":
            today = d.isoformat()
            classes = [c for c in classes if c["date"] == today]
        classes.sort(key=lambda c: (c["date"], c["start"]))
        return {"scope": scope, "term": term, "start": s, "end": e, "classes": classes}

    # --- grades (opt-in only; values stay local unless the caller exposes them) ---
    def get_grades_raw(self):
        self.login()
        st, body = self.sub_get(TRANSCRIPT_HOST, TRANSCRIPT_BASE, "/transcripts",
                                TRANSCRIPT_SALT, service_url=TRANSCRIPT_SVC)
        if not isinstance(body, dict):
            raise WeMustError("unexpected transcript response")
        return body.get("model") or {}
