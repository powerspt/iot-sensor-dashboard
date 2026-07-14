# -*- coding: utf-8 -*-
"""
방법 2 · 원격 서버 + 계정별 누적 대시보드  (pitchlab 등 서버에 배포)
------------------------------------------------------------------------
- 학생 ESP32(각자 집)  → POST /api/ingest  (헤더 X-API-Key)  → 사용자별 누적
- 학생 브라우저        → 로그인(세션)      → 자기 데이터만 조회

두 종류의 인증:
  · 장치 → 서버 : API 키 (학생마다 고유)
  · 사람 → 대시보드 : 아이디/비밀번호 로그인(세션)
모든 조회는 세션의 user_id 로 소유권을 확인 → 남의 데이터 접근 차단.

실행:  pip install flask   →   python 방법2_server.py
배포:  pitchlab 서버의 새 포트로 이 앱을 띄우고 방화벽에서 그 포트를 개방.
       (자세한 배포 체크리스트는 함께 제공된 HTML 가이드 참고)
"""
from flask import (Flask, request, jsonify, session, redirect,
                   url_for, Response, render_template_string, abort)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, datetime, secrets, os, functools

#  DB_PATH 환경변수로 저장 위치 지정 가능(Docker 볼륨 영속화용). 없으면 코드 옆에 생성.
DB = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "dashboard.db")
app = Flask(__name__)
# ⚠️ 배포 시 반드시 고정된 비밀 값으로 바꾸세요(환경변수 권장). 바뀌면 로그인이 풀립니다.
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-ME-이-값을-바꾸세요")


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS api_keys(
            key TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            label TEXT,
            created TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS readings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            sensor TEXT NOT NULL,
            value REAL NOT NULL)""")


# 앱을 import 하는 방식(gunicorn 등)에서도 테이블이 준비되도록 로드 시 1회 초기화
init_db()


def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrap


# ================= 계정 =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        if len(u) < 3 or len(p) < 4:
            return render_template_string(PAGE_AUTH, mode="register",
                   msg="아이디 3자 이상, 비밀번호 4자 이상")
        try:
            with db() as c:
                cur = c.execute("INSERT INTO users(username, password_hash) VALUES(?,?)",
                                (u, generate_password_hash(p)))
                uid = cur.lastrowid
                # 가입 시 API 키 1개 자동 발급
                c.execute("INSERT INTO api_keys(key, user_id, label, created) VALUES(?,?,?,?)",
                          ("stu_" + secrets.token_hex(12), uid, "기본 키",
                           datetime.datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            return render_template_string(PAGE_AUTH, mode="register",
                   msg="이미 있는 아이디입니다")
        session["user_id"] = uid
        session["username"] = u
        return redirect(url_for("dashboard"))
    return render_template_string(PAGE_AUTH, mode="register", msg="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if row and check_password_hash(row["password_hash"], p):
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            return redirect(url_for("dashboard"))
        return render_template_string(PAGE_AUTH, mode="login", msg="아이디/비밀번호 확인")
    return render_template_string(PAGE_AUTH, mode="login", msg="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


# ================= API 키 =================
@app.route("/keys/new", methods=["POST"])
@login_required
def keys_new():
    with db() as c:
        c.execute("INSERT INTO api_keys(key, user_id, label, created) VALUES(?,?,?,?)",
                  ("stu_" + secrets.token_hex(12), session["user_id"],
                   request.form.get("label", "추가 키"),
                   datetime.datetime.now().isoformat(timespec="seconds")))
    return redirect(url_for("dashboard"))


# ================= 장치 → 서버 : 수집 =================
@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    key = request.headers.get("X-API-Key", "")
    with db() as c:
        row = c.execute("SELECT user_id FROM api_keys WHERE key=?", (key,)).fetchone()
    if not row:
        return jsonify(ok=False, error="유효하지 않은 API 키"), 401
    data = request.get_json(force=True, silent=True) or {}
    sensor = str(data.get("sensor", "sensor"))
    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="value(숫자)가 필요합니다"), 400
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with db() as c:
        c.execute("INSERT INTO readings(user_id, ts, sensor, value) VALUES(?,?,?,?)",
                  (row["user_id"], ts, sensor, value))
    return jsonify(ok=True)


# ================= 브라우저 → 서버 : 내 데이터만 =================
@app.route("/api/my/series")
@login_required
def my_series():
    limit = min(int(request.args.get("limit", 120)), 2000)
    with db() as c:
        rows = c.execute("""SELECT ts, value FROM readings
                            WHERE user_id=? ORDER BY id DESC LIMIT ?""",
                         (session["user_id"], limit)).fetchall()
    rows = rows[::-1]
    return jsonify([{"ts": r["ts"], "value": r["value"]} for r in rows])


@app.route("/api/my/stats")
@login_required
def my_stats():
    with db() as c:
        r = c.execute("""SELECT COUNT(*) n, AVG(value) avg, MIN(value) mn, MAX(value) mx
                         FROM readings WHERE user_id=?""", (session["user_id"],)).fetchone()
        last = c.execute("""SELECT value FROM readings WHERE user_id=?
                            ORDER BY id DESC LIMIT 1""", (session["user_id"],)).fetchone()
    return jsonify(count=r["n"], avg=r["avg"], min=r["mn"], max=r["mx"],
                   last=(last["value"] if last else None))


@app.route("/export.csv")
@login_required
def export_csv():
    with db() as c:
        rows = c.execute("""SELECT ts, sensor, value FROM readings
                            WHERE user_id=? ORDER BY id""", (session["user_id"],)).fetchall()
    lines = ["time,sensor,value"] + [f'{r["ts"]},{r["sensor"]},{r["value"]}' for r in rows]
    return Response("\n".join(lines), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=my_data.csv"})


@app.route("/dashboard")
@login_required
def dashboard():
    with db() as c:
        keys = c.execute("SELECT key, label FROM api_keys WHERE user_id=? ORDER BY created",
                         (session["user_id"],)).fetchall()
    return render_template_string(PAGE_DASH, username=session["username"],
                                  keys=[dict(k) for k in keys])


# ================= 페이지(템플릿) =================
PAGE_AUTH = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ '회원가입' if mode=='register' else '로그인' }} · 센서 대시보드</title>
<style>body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:#f6f7fb;color:#1b1f33;display:flex;min-height:100vh;align-items:center;justify-content:center}
.box{background:#fff;border:1px solid #e6e7f0;border-radius:16px;padding:28px;width:340px;box-shadow:0 10px 30px rgba(30,27,75,.08)}
h1{font-size:20px;margin:0 0 16px}input{width:100%;padding:11px;margin:6px 0;border:1px solid #cbcfe0;border-radius:10px;font-size:15px}
button{width:100%;background:#4f46e5;color:#fff;border:0;border-radius:10px;padding:12px;font-weight:700;font-size:15px;margin-top:8px;cursor:pointer}
.msg{color:#be123c;font-size:13.5px;min-height:18px;margin:4px 0}a{color:#4338ca;font-size:13.5px}</style></head><body>
<form class="box" method="post">
<h1>{{ '회원가입' if mode=='register' else '로그인' }} · 센서 대시보드</h1>
<input name="username" placeholder="아이디" autocomplete="username">
<input name="password" type="password" placeholder="비밀번호" autocomplete="current-password">
<div class="msg">{{ msg }}</div>
<button type="submit">{{ '가입하기' if mode=='register' else '로그인' }}</button>
<p style="text-align:center;margin:14px 0 0">
{% if mode=='register' %}이미 계정이 있나요? <a href="/login">로그인</a>
{% else %}처음이신가요? <a href="/register">회원가입</a>{% endif %}</p>
</form></body></html>"""

PAGE_DASH = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>내 센서 대시보드</title>
<style>:root{--ink:#1b1f33;--muted:#5f6478;--line:#e6e7f0;--brand:#4f46e5}
*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:#f6f7fb;color:var(--ink)}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:20px 24px;display:flex;justify-content:space-between;align-items:center}
header h1{margin:0;font-size:20px}header a{color:#d9f2f7;font-size:14px;text-decoration:none}
.wrap{max-width:960px;margin:0 auto;padding:20px}
.keybox{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:16px}
.keybox code{background:#eef0fb;color:#33307a;padding:3px 8px;border-radius:6px;font-family:Consolas,monospace}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px}
@media(max-width:720px){.cards{grid-template-columns:repeat(2,1fr)}}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.card .k{font-size:12.5px;color:var(--muted);font-weight:700}.card .v{font-size:24px;font-weight:800;margin-top:4px}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px}
canvas{width:100%;height:auto;display:block}
.bar{display:flex;gap:12px;align-items:center;margin-top:14px}
button{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:9px 15px;font-weight:700;cursor:pointer}
#status{color:var(--muted);font-size:13px}</style></head><body>
<header><h1>📈 내 센서 대시보드</h1><div><b>{{ username }}</b> 님 · <a href="/logout">로그아웃</a></div></header>
<div class="wrap">
  <div class="keybox"><b>내 API 키</b> (ESP32 코드의 <code>API_KEY</code>에 붙여넣기)
    {% for k in keys %}<div style="margin-top:8px"><code>{{ k.key }}</code> <span style="color:#5f6478;font-size:13px">— {{ k.label }}</span></div>{% endfor %}
    <form method="post" action="/keys/new" style="margin-top:10px"><button type="submit">+ 새 키 발급</button></form>
  </div>
  <div class="cards" id="cards"></div>
  <div class="panel"><canvas id="chart" width="900" height="320"></canvas></div>
  <div class="bar"><button onclick="location.href='/export.csv'">⬇ 내 데이터 CSV</button><span id="status">연결 중…</span></div>
</div>
<script>
function card(k,v){return '<div class="card"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>';}
function fmt(x){return (x==null)?'-':(Math.round(x*10)/10);}
function renderCards(s){document.getElementById('cards').innerHTML=
  card('현재값',fmt(s.last))+card('평균',fmt(s.avg))+card('최소',fmt(s.min))+card('최대',fmt(s.max))+card('샘플 수',s.count);}
function drawChart(v){var c=document.getElementById('chart'),ctx=c.getContext('2d');var W=c.width,H=c.height,pad=40;
  ctx.clearRect(0,0,W,H);
  if(v.length<2){ctx.fillStyle='#9aa3b2';ctx.font='16px sans-serif';ctx.fillText('데이터를 기다리는 중…',pad,H/2);return;}
  var mn=Math.min.apply(null,v),mx=Math.max.apply(null,v),rng=(mx-mn)||1;
  ctx.strokeStyle='#e2e6f0';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad,H-pad);ctx.lineTo(W-10,H-pad);ctx.moveTo(pad,10);ctx.lineTo(pad,H-pad);ctx.stroke();
  ctx.strokeStyle='#4f46e5';ctx.lineWidth=2;ctx.beginPath();
  v.forEach(function(val,i){var x=pad+(W-pad-10)*(i/(v.length-1));var y=(H-pad)-(H-pad-10)*((val-mn)/rng);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
  ctx.stroke();ctx.fillStyle='#5f6478';ctx.font='12px sans-serif';ctx.fillText(String(Math.round(mx)),6,16);ctx.fillText(String(Math.round(mn)),6,H-pad);}
async function refresh(){try{
  var s=await (await fetch('/api/my/stats')).json();
  var series=await (await fetch('/api/my/series?limit=120')).json();
  renderCards(s);drawChart(series.map(function(p){return p.value;}));
  document.getElementById('status').textContent='최근 갱신 '+new Date().toLocaleTimeString();
}catch(e){document.getElementById('status').textContent='대기…';}}
setInterval(refresh,2000);refresh();
</script></body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))   # 배포 시 PORT 환경변수로 지정
    print(f"서버 시작: 0.0.0.0:{port}  (배포 시 방화벽에서 이 포트를 개방)")
    app.run(host="0.0.0.0", port=port, debug=False)
