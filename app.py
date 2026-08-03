from flask import Flask, render_template_string
import psutil, subprocess, time, os, json, urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
PORT = 8080
REFRESH_SECONDS = 10

def _parse_git_repos(raw):
    repos = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        name, path = item.split(":", 1)
        repos.append({"name": name.strip(), "path": os.path.expanduser(path.strip())})
    return repos

# Git 저장소/로그 경로는 .env 파일에서 읽습니다. (.env.example 참고)
GIT_REPOS = _parse_git_repos(os.environ.get("GIT_REPOS", ""))
GIT_ACTIVITY_LOG = os.path.expanduser(os.environ.get("GIT_ACTIVITY_LOG", "~/macmini-dashboard-git.log"))

_prev_net = psutil.net_io_counters()
_prev_disk = psutil.disk_io_counters()
_prev_time = time.time()
_day = datetime.now().date().isoformat()
_day_recv = _prev_net.bytes_recv
_day_sent = _prev_net.bytes_sent

HTML = r"""
<!doctype html><html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=1024,initial-scale=1,maximum-scale=1">
<meta http-equiv="refresh" content="{{ refresh }}">
<title>Mac mini M4</title>
<style>
html,body{margin:0;background:#090b0f;color:#f1f3f6;font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
body{padding:22px 24px}*{box-sizing:border-box}
.header,.card{background:#11151b;border:1px solid #252b34;border-radius:14px}
.header{height:70px;padding:0 20px;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.title{font-size:27px;font-weight:700}.sub{color:#8e98a7;font-size:12px;margin-top:5px}.online{color:#61d98b;font-size:14px}.dot{display:inline-block;width:9px;height:9px;background:#61d98b;border-radius:50%;margin-right:6px}
.clock{text-align:center;font-size:25px;font-weight:600}.clock small{display:block;color:#7f8896;font-size:11px;font-weight:400}.refresh{color:#63b8ff;font-size:12px;text-align:right}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}.card{padding:15px}.label{font-size:12px;color:#8e98a7;letter-spacing:1px;margin-bottom:7px}.big{font-size:28px;font-weight:700}
.bar{height:7px;background:#292f38;border-radius:5px;margin-top:10px;overflow:hidden}.fill{height:100%;background:#4da3ff}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mini{background:#0d1015;border-radius:9px;padding:9px}.mini-label{font-size:10px;color:#778191}.mini-value{font-size:17px;margin-top:4px}
.mid{display:grid;grid-template-columns:1.1fr 1.3fr 1fr;gap:16px;margin-bottom:16px}.bottom{display:grid;grid-template-columns:1fr 1fr 1.5fr;gap:16px;margin-bottom:16px}
.row{height:32px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #222730;font-size:13px}.row:last-child{border:0}.name{max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.value{color:#b9c2ce}.ok{color:#61d98b}.warn{color:#f0c865}
.gitrow{display:grid;grid-template-columns:1.1fr .7fr 1.2fr;gap:8px;min-height:32px;align-items:center;border-bottom:1px solid #222730;font-size:13px}
.activity-row{display:grid;grid-template-columns:70px 55px 105px 1fr 65px 65px;gap:8px;min-height:31px;align-items:center;border-bottom:1px solid #222730;font-size:12px}
.badge{border-radius:5px;padding:3px 5px;text-align:center;font-size:10px;font-weight:700}.push{background:#493274;color:#d9bfff}.pull{background:#15486b;color:#9bd7ff}
.footer{text-align:right;color:#667080;font-size:11px;margin-top:5px}
@media(max-width:800px){.metrics{grid-template-columns:1fr 1fr}.mid,.bottom{grid-template-columns:1fr}.header{height:auto;padding:14px}}
</style></head><body>

<div class="header">
<div><div class="title">MAC MINI M4 <span class="online"><span class="dot"></span>ONLINE</span></div><div class="sub">Uptime {{ uptime }}</div></div>
<div class="clock">{{ now }}<small>{{ date }}</small></div><div class="refresh">AUTO REFRESH<br><b>{{ refresh }}s</b></div>
</div>

<div class="metrics">
<div class="card"><div class="label">CPU</div><div class="big">{{ cpu }}%</div><div class="bar"><div class="fill" style="width:{{ cpu }}%"></div></div><div class="sub">Load {{ load1 }} / {{ load5 }} / {{ load15 }}</div></div>
<div class="card"><div class="label">MEMORY</div><div class="big">{{ mem }}%</div><div class="bar"><div class="fill" style="width:{{ mem }}%"></div></div><div class="sub">{{ mem_used }} / {{ mem_total }} · Swap {{ swap }}</div></div>
<div class="card"><div class="label">STORAGE</div><div class="big">{{ disk }}%</div><div class="bar"><div class="fill" style="width:{{ disk }}%"></div></div><div class="sub">{{ disk_used }} used · {{ disk_free }} free</div></div>
<div class="card"><div class="label">NETWORK</div><div class="two"><div class="mini"><div class="mini-label">DOWNLOAD</div><div class="mini-value">↓ {{ down }}</div></div><div class="mini"><div class="mini-label">UPLOAD</div><div class="mini-value">↑ {{ up }}</div></div></div><div class="sub">Today ↓ {{ day_down }} · ↑ {{ day_up }}</div></div>
</div>

<div class="mid">
<div class="card"><div class="label">TOP PROCESSES · CPU</div>{% for p in processes %}<div class="row"><span class="name">{{ p.name }}</span><span class="value">{{ p.cpu }}% · {{ p.mem }}%</span></div>{% endfor %}</div>
<div class="card"><div class="label">DOCKER CONTAINERS</div>{% if docker is none %}<div class="row"><span class="warn">Docker unavailable</span></div>{% elif docker %}{% for d in docker %}<div class="row"><span class="name"><span class="{{ 'ok' if d.running else 'warn' }}">●</span> {{ d.name }}</span><span class="{{ 'ok' if d.running else 'warn' }}">{{ d.status }}</span></div>{% endfor %}{% else %}<div class="row"><span class="warn">No containers</span></div>{% endif %}</div>
<div class="card"><div class="label">CLAUDE USAGE</div>{% if claude_ok %}<div class="sub" style="margin-bottom:4px">Session {{ claude_session_pct }}%{% if claude_session_reset %} · resets {{ claude_session_reset }}{% endif %}</div><div class="bar"><div class="fill" style="width:{{ claude_session_pct }}%"></div></div><div class="sub" style="margin:10px 0 4px">Week {{ claude_week_pct }}%{% if claude_week_reset %} · resets {{ claude_week_reset }}{% endif %}</div><div class="bar"><div class="fill" style="width:{{ claude_week_pct }}%"></div></div>{% else %}<div class="row"><span class="warn">사용량 정보 없음</span></div>{% endif %}</div>
</div>

<div class="bottom">
<div class="card"><div class="label">DISK I/O</div><div class="row"><span>READ</span><span class="value">{{ read }}</span></div><div class="row"><span>WRITE</span><span class="value">{{ write }}</span></div></div>
<div class="card"><div class="label">SYSTEM</div><div class="row"><span>Uptime</span><span class="value">{{ uptime }}</span></div><div class="row"><span>Load Average</span><span class="value">{{ load1 }}</span></div><div class="row"><span>Processes</span><span class="value">{{ process_count }}</span></div></div>
<div class="card"><div class="label">GIT STATUS · {{ git_status|length }} REPOS</div>{% if git_status %}{% for g in git_status %}<div class="gitrow"><span>{{ g.name }}</span><span>{{ g.branch }}</span><span class="{{ 'ok' if g.clean else 'warn' }}">{{ g.state }}</span></div>{% endfor %}{% else %}<div class="sub">GIT_REPOS에 저장소 경로를 추가하세요.</div>{% endif %}</div>
</div>

<div class="card"><div class="label">GIT ACTIVITY · RECENT {{ activities|length }}</div>
{% if activities %}{% for a in activities %}<div class="activity-row"><span>{{ a.time }}</span><span class="badge {{ 'push' if a.action == 'PUSH' else 'pull' }}">{{ a.action }}</span><span>{{ a.repo }}</span><span class="name">{{ a.message }}</span><span>{{ a.commit }}</span><span>{{ a.branch }}</span></div>{% endfor %}
{% else %}<div class="sub">아직 기록된 Git pull/push 활동이 없습니다.</div>{% endif %}</div>

<div class="footer">Mac mini dashboard · Flask · refresh {{ refresh }}s</div>
</body></html>
"""

def fmt(n):
    n=float(n)
    for u in ["B","KB","MB","GB","TB"]:
        if n<1024 or u=="TB": return f"{n:.1f} {u}" if u!="B" else f"{n:.0f} B"
        n/=1024
def rate(n): return fmt(n)+"/s"
def duration(s):
    s=int(s); d,s=divmod(s,86400); h,s=divmod(s,3600); m,_=divmod(s,60)
    return f"{d}D {h:02d}H {m:02d}M"
def cmd(path,args):
    try:
        r=subprocess.run(["git","-C",path]+args,capture_output=True,text=True,timeout=2)
        return r.stdout.strip() if r.returncode==0 else ""
    except: return ""
_docker_bin=None
def _find_docker():
    # launchd로 실행하면 PATH가 최소 상태(/usr/bin:/bin:/usr/sbin:/sbin)라
    # /usr/local/bin 등에 있는 docker를 못 찾는 경우가 있어 절대경로를 직접 탐색.
    global _docker_bin
    if _docker_bin: return _docker_bin
    for p in ("/usr/local/bin/docker","/opt/homebrew/bin/docker","/usr/bin/docker"):
        if os.path.exists(p):
            _docker_bin=p; return p
    _docker_bin="docker"; return _docker_bin
def docker():
    try:
        r=subprocess.run([_find_docker(),"ps","-a","--format","{{.Names}}\t{{.Status}}"],capture_output=True,text=True,timeout=5)
        if r.returncode: return []
        out=[]
        for x in r.stdout.strip().splitlines():
            if "\t" in x:
                name,status=x.split("\t",1); running=status.lower().startswith("up")
                out.append({"name":name,"status":"UP" if running else status,"running":running})
        return out
    except: return None
def git_status():
    out=[]
    for repo in GIT_REPOS:
        p=repo["path"]
        if not os.path.isdir(os.path.join(p,".git")): continue
        branch=cmd(p,["branch","--show-current"]) or "detached"
        modified=bool(cmd(p,["status","--porcelain"]))
        state="MODIFIED" if modified else "CLEAN"
        ahead=behind=""
        upstream=cmd(p,["rev-list","--left-right","--count",f"{branch}...@{{u}}"])
        if upstream:
            try: ahead,behind=upstream.split()
            except: pass
        if ahead and behind and (ahead!="0" or behind!="0"): state=f"{ahead} ahead / {behind} behind"
        out.append({"name":repo["name"],"branch":branch,"clean":state=="CLEAN","state":state})
    return out
def _fmt_reset(iso_ts):
    if not iso_ts: return ""
    try: dt=datetime.fromisoformat(iso_ts.replace("Z","+00:00")).astimezone()
    except: return ""
    t=dt.strftime("%I:%M%p").lstrip("0").lower()
    if dt.date()==datetime.now().astimezone().date(): return t
    return f"{dt.strftime('%b')} {dt.day} {t}"
def _read_claude_token():
    # 1) 파일 기반(~/.claude/.credentials.json), 2) macOS Keychain 순으로 시도.
    cred_path=os.path.expanduser("~/.claude/.credentials.json")
    try:
        if os.path.exists(cred_path):
            with open(cred_path,encoding="utf-8") as f: cred=json.load(f)
            token=(cred.get("claudeAiOauth") or {}).get("accessToken") or cred.get("accessToken")
            if token: return token
    except: pass
    try:
        r=subprocess.run(["security","find-generic-password","-s","Claude Code-credentials","-w"],capture_output=True,text=True,timeout=3)
        if r.returncode==0 and r.stdout.strip():
            cred=json.loads(r.stdout.strip())
            return (cred.get("claudeAiOauth") or {}).get("accessToken") or cred.get("accessToken")
    except: pass
    return None
def claude_subscription_usage():
    # Claude Code의 /usage와 같은 데이터. 2분 이내 로컬 캐시(~/.claude/.usage-cache)가
    # 있으면 그걸 쓰고, 없으면 credentials 파일/macOS Keychain의 OAuth 토큰으로 비공식 API를 호출.
    # (Anthropic 공식 문서화된 API가 아니라 향후 Claude Code 업데이트로 깨질 수 있음)
    cache_path=os.path.expanduser("~/.claude/.usage-cache")
    data=None
    try:
        if os.path.exists(cache_path) and (time.time()-os.path.getmtime(cache_path))<120:
            with open(cache_path,encoding="utf-8") as f: data=json.load(f)
    except: data=None
    if data is None:
        try:
            token=_read_claude_token()
            if token:
                req=urllib.request.Request("https://api.anthropic.com/api/oauth/usage",headers={
                    "Accept":"application/json","Content-Type":"application/json",
                    "User-Agent":"claude-code/2.1.42","Authorization":f"Bearer {token}",
                    "anthropic-beta":"oauth-2025-04-20"})
                with urllib.request.urlopen(req,timeout=3) as resp: raw=resp.read().decode("utf-8")
                data=json.loads(raw)
                try:
                    with open(cache_path,"w",encoding="utf-8") as f: f.write(raw)
                except: pass
        except: data=None
    result={"ok":False,"session_pct":0,"session_reset":"","week_pct":0,"week_reset":""}
    if data:
        try:
            fh=data.get("five_hour") or {}; sd=data.get("seven_day") or {}
            result["ok"]=True
            result["session_pct"]=round(fh.get("utilization",0))
            result["session_reset"]=_fmt_reset(fh.get("resets_at"))
            result["week_pct"]=round(sd.get("utilization",0))
            result["week_reset"]=_fmt_reset(sd.get("resets_at"))
        except: pass
    return result
def activities():
    if not os.path.exists(GIT_ACTIVITY_LOG): return []
    out=[]
    try:
        lines=open(GIT_ACTIVITY_LOG,encoding="utf-8").readlines()[-4:]
        for line in reversed(lines):
            p=line.rstrip().split("|",5)
            if len(p)==6:
                t,a,r,b,c,m=p; out.append({"time":t,"action":a,"repo":r,"branch":b,"commit":c,"message":m})
    except: pass
    return out

@app.route("/")
def home():
    global _prev_net,_prev_disk,_prev_time,_day,_day_recv,_day_sent
    cpu=psutil.cpu_percent(interval=.15); mem=psutil.virtual_memory(); disk=psutil.disk_usage("/"); swap=psutil.swap_memory()
    now=time.time(); net=psutil.net_io_counters(); dio=psutil.disk_io_counters(); elapsed=max(now-_prev_time,.1)
    today=datetime.now().date().isoformat()
    if today!=_day: _day=today; _day_recv=net.bytes_recv; _day_sent=net.bytes_sent
    down=max(net.bytes_recv-_prev_net.bytes_recv,0)/elapsed; up=max(net.bytes_sent-_prev_net.bytes_sent,0)/elapsed
    read=max(dio.read_bytes-_prev_disk.read_bytes,0)/elapsed if dio else 0
    write=max(dio.write_bytes-_prev_disk.write_bytes,0)/elapsed if dio else 0
    _prev_net,_prev_disk,_prev_time=net,dio,now
    ps=[]
    for p in psutil.process_iter(["name","cpu_percent","memory_percent"]):
        try:
            i=p.info; ps.append({"name":i["name"] or "unknown","cpu":round(i["cpu_percent"] or 0,1),"mem":round(i["memory_percent"] or 0,1)})
        except: pass
    ps.sort(key=lambda x:x["cpu"],reverse=True); loads=os.getloadavg(); cu=claude_subscription_usage()
    return render_template_string(HTML,refresh=REFRESH_SECONDS,cpu=round(cpu,1),mem=round(mem.percent,1),mem_used=fmt(mem.used),mem_total=fmt(mem.total),swap=f"{fmt(swap.used)} / {fmt(swap.total)}",disk=round(disk.percent,1),disk_used=fmt(disk.used),disk_free=fmt(disk.free),down=rate(down),up=rate(up),day_down=fmt(max(net.bytes_recv-_day_recv,0)),day_up=fmt(max(net.bytes_sent-_day_sent,0)),read=rate(read),write=rate(write),processes=ps[:5],docker=docker(),git_status=git_status(),activities=activities(),uptime=duration(time.time()-psutil.boot_time()),load1=f"{loads[0]:.2f}",load5=f"{loads[1]:.2f}",load15=f"{loads[2]:.2f}",process_count=len(psutil.pids()),now=datetime.now().strftime("%H:%M:%S"),date=datetime.now().strftime("%Y-%m-%d (%a)"),claude_ok=cu["ok"],claude_session_pct=cu["session_pct"],claude_session_reset=cu["session_reset"],claude_week_pct=cu["week_pct"],claude_week_reset=cu["week_reset"])

if __name__=="__main__":
    print(f"Mac mini Dashboard: http://localhost:{PORT}")
    app.run(host="192.168.2.1",port=PORT,threaded=True)
