"""Command-line interface (opt-in features).

  python -m wemust.cli grades   # print YOUR OWN grades as a table (stays local)
  python -m wemust.cli sync     # run the optional Notion sync (no grades)

`grades` is the only place grade values are shown, and only on your terminal.
"""
import sys

from .config import Config, ConfigError
from .client import WeMustClient, WeMustError


def _client(cfg):
    return WeMustClient(cfg.require_username(), cfg.get_password)


def cmd_grades(cfg):
    c = _client(cfg)
    model = c.get_grades_raw()
    groups = model.get("transcriptDetailsVOList") or []
    if not groups:
        print("No grade records.")
        return 0

    def val(d, *keys):
        for k in keys:
            if d.get(k) not in (None, ""):
                return d[k]
        return ""

    for g in groups:
        label = val(g, "crsEnrolIntakeName", "crsEnrolIntake", "intakeName", "termName", "term")
        print("\n=== %s ===" % label)
        for k, v in g.items():
            if not isinstance(v, (list, dict)) and v not in (None, ""):
                print("  %s: %s" % (k, v))
        courses, cname = None, None
        for k, v in g.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if courses is None or len(v) > len(courses):
                    courses, cname = v, k
        if not courses:
            continue
        cols = list(courses[0].keys())
        widths = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in courses)) for c in cols}
        print("  [%s]" % cname)
        print("  " + " | ".join(str(c).ljust(widths[c]) for c in cols))
        print("  " + "-+-".join("-" * widths[c] for c in cols))
        for r in courses:
            print("  " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    return 0


def cmd_sync(cfg):
    from . import notion_sync
    return notion_sync.run(cfg)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else ""
    cfg = Config()
    try:
        if cmd == "grades":
            return cmd_grades(cfg)
        if cmd == "sync":
            return cmd_sync(cfg)
    except (WeMustError, ConfigError) as ex:
        print("error:", ex)
        return 1
    print("usage: python -m wemust.cli {grades|sync}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
