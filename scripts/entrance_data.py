"""Fit Factory entrance screen: pull Downtown group classes + rosters (today + tomorrow, Toronto time)
from Mariana Tek and write entrance/data.json. Runs on GitHub Actions every 10 minutes.
Without an MT_TOKEN secret it publishes the class schedule only (no member data).
If an MT_TOKEN secret is added later, it also adds first-timers and milestones (first name + last initial)."""
import json, os, sys, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
TZ = ZoneInfo("America/Toronto"); BASE = "https://fitfactory.marianatek.com/api"
MILESTONES = {10, 25, 50, 100, 250, 500, 750, 1000}
OPT_OUT_TAG = "no screen"   # MT user tag; anyone tagged this is never shown
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "entrance", "data.json")
def token():
    return os.environ.get("MT_TOKEN","").strip()
def get(url, auth=None):
    h = {"Accept":"application/vnd.api+json" if auth else "application/json"}
    if auth: h["Authorization"] = "Bearer "+auth
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r: return json.load(r)
def pretty(name):
    out=[]
    for part in name.split(" - "):
        words=[]
        for w in part.split():
            words.append(w if w.startswith("[") else w.capitalize() if not w.isupper() or len(w)>3 or w in ("ABS","WOD") else w)
        out.append(" ".join(words))
    s=" · ".join(out).replace("Hyrox","HYROX").replace("Wod","WOD").replace("&","&")
    return s
def short(u):
    f=(u.get("first_name") or "").strip().split(" ")[0].capitalize(); l=(u.get("last_name") or "").strip()
    return (f+" "+l[0].upper()+".") if f and l else f
def main(days):
    tok = token(); today = dt.datetime.now(TZ).date(); out = {"generated": dt.datetime.now(TZ).isoformat(timespec="minutes"), "names": bool(tok), "days": []}
    for i in range(days):
        d = today + dt.timedelta(days=i)
        cl = get(f"{BASE}/customer/v1/classes?location=48718&min_start_date={d}&max_start_date={d}&page_size=200")["results"]
        day = {"date": str(d), "classes": []}
        for c in sorted(cl, key=lambda c: c["start_datetime"]):
            n = c["name"]; tags = [t["slug"] for t in c.get("class_tags",[])]
            if "PSC" in n.upper() or "REFINED" in n.upper() or "psc" in tags: continue
            start = dt.datetime.fromisoformat(c["start_datetime"].replace("Z","+00:00")).astimezone(TZ)
            if start.date()!=d: continue
            res = get(f"{BASE}/reservations?class_session={c['id']}&include=user,user.tags&page_size=200", tok) if tok else {"data": [], "included": []}
            users = {u["id"]: u for u in res.get("included",[]) if u["type"]=="users"}
            tagnames = {t["id"]: t["attributes"].get("name","").lower() for t in res.get("included",[]) if t["type"] in ("tags","user_tags")}
            ms, ft = [], []
            for r in res["data"]:
                a = r["attributes"]
                if a["reservation_type"]!="standard" or a["reserved_for_guest"] or "cancel" in a["status"] or a["status"]=="removed": continue
                rel = r["relationships"]["user"]["data"]
                if not rel or rel["id"] not in users: continue
                ua = users[rel["id"]]["attributes"]
                utags = [tagnames.get(t["id"],"") for t in users[rel["id"]].get("relationships",{}).get("tags",{}).get("data",[]) or []]
                if OPT_OUT_TAG in utags: continue
                done = ua.get("completed_class_count") or 0
                nth = done + (0 if a.get("check_in_date") else 1)
                name = short(ua)
                if not name: continue
                if done == 0 and not a.get("check_in_date"): ft.append(name); continue
                if nth in MILESTONES: ms.append({"n": nth, "name": name})
                j = ua.get("date_joined")
                if j:
                    jd = dt.datetime.fromisoformat(j.replace("Z","+00:00")).astimezone(TZ).date()
                    yrs = d.year - jd.year
                    if yrs >= 1 and (jd.month, jd.day) == (d.month, d.day): ms.append({"n": yrs, "name": name, "yr": True})
            coach = (c.get("instructors") or [{}])[0].get("name","").split(" ")[0]
            day["classes"].append({"sod": start.hour*3600+start.minute*60, "dur": (c.get("class_type") or {}).get("duration") or 60, "start": start.isoformat(), "time": start.strftime("%-I:%M %p"), "name": pretty(n), "coach": coach,
                                   "booked": sum(1 for r in res["data"] if r["attributes"]["reservation_type"]=="standard" and "cancel" not in r["attributes"]["status"] and r["attributes"]["status"]!="removed"),
                                   "ms": sorted(ms, key=lambda m: -m["n"]), "ft": ft})
        out["days"].append(day)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    if old.get("days") == out["days"] and old.get("names") == out["names"]:
        print("no change"); return
    with open(OUT,"w") as f: json.dump(out, f, ensure_ascii=False, separators=(",",":"))
    print("updated")
    for day in out["days"]:
        print(day["date"])
        for c in day["classes"]: print(f"  {c['time']:>8}  {c['name']:<40} {c['coach']:<8} booked {c['booked']:>2}  milestones {len(c['ms'])}  first-timers {len(c['ft'])}")
if __name__ == "__main__": main(int(sys.argv[1]) if len(sys.argv)>1 else 2)
