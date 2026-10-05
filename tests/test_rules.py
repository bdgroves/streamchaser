"""Offline tests for streamchaser's posting rules. Run: pytest -q tests"""
import importlib, json, os, sys
from types import SimpleNamespace as NS
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))


def rep(cur, d24=0.0, high=None, years=50, p25=20, p75=60, mean=40, roc=0.0, sid="x"):
    return NS(current=cur, delta_24h=d24, delta_1h=0, rate_of_change=roc, station_id=sid,
              stats=NS(high=high, years=years, p25=p25, p75=p75, mean=mean))


@pytest.fixture
def sc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for k in ("DRY_RUN", "POST_TO_X", "TWITTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BLUESKY_HANDLE", "h")
    for m in [m for m in sys.modules if m.startswith("streamchaser")]:
        sys.modules.pop(m)
    m = importlib.import_module("streamchaser.__main__")
    sent = []
    feed = {}
    monkeypatch.setattr(m, "build_report", lambda sid, name: feed.get(sid) or rep(30, sid=sid))
    monkeypatch.setattr(m, "generate_chart", lambda r, station_url: "c.png")
    monkeypatch.setattr(m, "post_to_bluesky", lambda t, c, r: sent.append(t))
    monkeypatch.setattr(m, "post_to_twitter", lambda t, c: sent.append("X:" + t))
    return m, feed, sent


def test_rules(sc):
    m, _, _ = sc
    # dam release peak / fast rise on a regulated reach: quiet
    assert m.notable(rep(482, d24=300, roc=40), free_flowing=False, big_river=True) is None
    # free-flowing doubled but still within normal: quiet
    assert m.notable(rep(50, d24=30), True, False) is None
    # free-flowing doubled and above normal: storm
    assert m.notable(rep(90, d24=50), True, False)[0] == "STORM"
    assert m.notable(rep(300, high=250), False, True)[0] == "RECORD"
    assert m.notable(rep(300, high=250, years=8), False, True) is None
    assert m.notable(rep(6000), False, True)[0] == "FLOOD"


def test_once_then_cooldown_and_x_standby(sc):
    m, feed, sent = sc
    feed["11284400"] = rep(90, d24=50, sid="11284400")      # Big Creek storm
    assert m.main() == 0 and len(sent) == 1 and "Big Creek" in sent[0]
    assert m.main() == 0 and len(sent) == 1                 # no hourly repeat
    feed["11264500"] = rep(9000, sid="11264500")            # Merced flood outranks
    m.main()
    assert len(sent) == 2 and sent[1].startswith("🔴 High water")
    assert not any(s.startswith("X:") for s in sent)        # X standing by
    assert "standing by" in open("logs/posts.jsonl").read()
