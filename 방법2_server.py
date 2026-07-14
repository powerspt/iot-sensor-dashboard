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
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            org TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'approved',
            is_admin INTEGER NOT NULL DEFAULT 0)""")
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
        # 기존 DB 호환: 없는 컬럼 자동 추가 (기존 사용자는 승인됨 상태 유지)
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        for col, ddl in [("name", "TEXT NOT NULL DEFAULT ''"),
                         ("org", "TEXT NOT NULL DEFAULT ''"),
                         ("email", "TEXT NOT NULL DEFAULT ''"),
                         ("status", "TEXT NOT NULL DEFAULT 'approved'"),
                         ("is_admin", "INTEGER NOT NULL DEFAULT 0")]:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")


def seed_admin():
    """ADMIN_USER / ADMIN_PASSWORD 환경변수가 있으면 관리자 계정을 준비(.env로 하드코딩)."""
    u = os.environ.get("ADMIN_USER")
    p = os.environ.get("ADMIN_PASSWORD")
    if not u or not p:
        return
    with db() as c:
        row = c.execute("SELECT id FROM users WHERE username=?", (u,)).fetchone()
        if row:
            # .env 값을 기준으로 비밀번호 갱신 + 관리자·승인 유지
            c.execute("UPDATE users SET password_hash=?, is_admin=1, status='approved' WHERE id=?",
                      (generate_password_hash(p), row["id"]))
        else:
            cur = c.execute("""INSERT INTO users(username, password_hash, name, org, email, status, is_admin)
                               VALUES(?,?,?,?,?, 'approved', 1)""",
                            (u, generate_password_hash(p), "관리자", "", ""))
            c.execute("INSERT INTO api_keys(key, user_id, label, created) VALUES(?,?,?,?)",
                      ("stu_" + secrets.token_hex(12), cur.lastrowid, "admin 기본 키",
                       datetime.datetime.now().isoformat(timespec="seconds")))


# 앱을 import 하는 방식(gunicorn 등)에서도 준비되도록 로드 시 1회 초기화 + 관리자 시드
init_db()
seed_admin()


def admin_required(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            return ("관리자 전용 페이지입니다.", 403)
        return f(*a, **k)
    return wrap


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
        f = request.form
        u = (f.get("username") or "").strip()
        name = (f.get("name") or "").strip()
        org = (f.get("org") or "").strip()
        email = (f.get("email") or "").strip()
        p = f.get("password") or ""
        p2 = f.get("password2") or ""

        def again(msg):   # 입력값을 유지한 채 오류 표시
            return render_template_string(PAGE_AUTH, mode="register", msg=msg, form=f)

        if not name or not org or not email:
            return again("이름·소속·이메일을 모두 입력하세요")
        if "@" not in email or "." not in email:
            return again("이메일 형식을 확인하세요")
        if len(u) < 3:
            return again("아이디는 3자 이상")
        if len(p) < 4:
            return again("비밀번호는 4자 이상")
        if p != p2:
            return again("비밀번호가 서로 다릅니다. 다시 확인하세요")
        try:
            with db() as c:
                c.execute("""INSERT INTO users(username, password_hash, name, org, email, status, is_admin)
                             VALUES(?,?,?,?,?, 'pending', 0)""",
                          (u, generate_password_hash(p), name, org, email))
        except sqlite3.IntegrityError:
            return again("이미 있는 아이디입니다")
        # 승인 대기 — 자동 로그인하지 않음
        return render_template_string(PAGE_PENDING)
    return render_template_string(PAGE_AUTH, mode="register", msg="", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if row and check_password_hash(row["password_hash"], p):
            if row["status"] != "approved":
                return render_template_string(PAGE_AUTH, mode="login",
                       msg="관리자 승인 대기 중입니다. 승인 후 로그인하세요.", form=request.form)
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            session["is_admin"] = bool(row["is_admin"])
            return redirect(url_for("dashboard"))
        return render_template_string(PAGE_AUTH, mode="login",
               msg="아이디/비밀번호 확인", form=request.form)
    return render_template_string(PAGE_AUTH, mode="login", msg="", form={})


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
                                  keys=[dict(k) for k in keys],
                                  is_admin=session.get("is_admin", False))


def _new_key(c, uid, label="기본 키"):
    c.execute("INSERT INTO api_keys(key, user_id, label, created) VALUES(?,?,?,?)",
              ("stu_" + secrets.token_hex(12), uid, label,
               datetime.datetime.now().isoformat(timespec="seconds")))


@app.route("/admin")
@admin_required
def admin():
    with db() as c:
        pending = c.execute("""SELECT id, username, name, org, email
                               FROM users WHERE status='pending' ORDER BY id""").fetchall()
        members = c.execute("""
            SELECT u.id, u.username, u.name, u.org, u.is_admin,
                   COUNT(r.id) AS n, MAX(r.ts) AS last_ts,
                   (SELECT value FROM readings r2 WHERE r2.user_id = u.id
                    ORDER BY r2.id DESC LIMIT 1) AS last_v
            FROM users u LEFT JOIN readings r ON r.user_id = u.id
            WHERE u.status='approved'
            GROUP BY u.id ORDER BY u.username""").fetchall()
    return render_template_string(PAGE_ADMIN, username=session["username"],
                                  pending=[dict(r) for r in pending],
                                  members=[dict(r) for r in members],
                                  msg=request.args.get("msg", ""))


@app.route("/admin/approve", methods=["POST"])
@admin_required
def admin_approve():
    uid = request.form.get("user_id")
    with db() as c:
        c.execute("UPDATE users SET status='approved' WHERE id=?", (uid,))
        if not c.execute("SELECT 1 FROM api_keys WHERE user_id=?", (uid,)).fetchone():
            _new_key(c, uid)          # 승인 시 API 키 발급
    return redirect(url_for("admin", msg="승인했습니다."))


@app.route("/admin/reject", methods=["POST"])
@admin_required
def admin_reject():
    uid = request.form.get("user_id")
    with db() as c:
        # 관리자 계정은 삭제 금지
        if c.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()["is_admin"]:
            return redirect(url_for("admin", msg="관리자 계정은 삭제할 수 없습니다."))
        c.execute("DELETE FROM api_keys WHERE user_id=?", (uid,))
        c.execute("DELETE FROM readings WHERE user_id=?", (uid,))
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    return redirect(url_for("admin", msg="삭제(거절)했습니다."))


@app.route("/admin/create", methods=["POST"])
@admin_required
def admin_create():
    f = request.form
    u = (f.get("username") or "").strip()
    name = (f.get("name") or "").strip()
    org = (f.get("org") or "").strip()
    email = (f.get("email") or "").strip()
    p = f.get("password") or ""
    if len(u) < 3 or len(p) < 4 or not name:
        return redirect(url_for("admin", msg="아이디 3자·비밀번호 4자·이름은 필수입니다."))
    try:
        with db() as c:
            cur = c.execute("""INSERT INTO users(username, password_hash, name, org, email, status, is_admin)
                               VALUES(?,?,?,?,?, 'approved', 0)""",
                            (u, generate_password_hash(p), name, org, email))
            _new_key(c, cur.lastrowid)
    except sqlite3.IntegrityError:
        return redirect(url_for("admin", msg="이미 있는 아이디입니다."))
    return redirect(url_for("admin", msg=f"'{u}' 계정을 생성했습니다(승인됨)."))


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
{% if mode=='register' %}
<input name="name" placeholder="이름" value="{{ form.get('name','') }}" required>
<input name="org" placeholder="소속 (학교 / 반 등)" value="{{ form.get('org','') }}" required>
<input name="email" type="email" placeholder="이메일" value="{{ form.get('email','') }}" required>
{% endif %}
<input name="username" placeholder="아이디" value="{{ form.get('username','') }}" autocomplete="username" required>
<input name="password" type="password" placeholder="비밀번호 (4자 이상)" autocomplete="{{ 'new-password' if mode=='register' else 'current-password' }}" required>
{% if mode=='register' %}<input name="password2" type="password" placeholder="비밀번호 확인" autocomplete="new-password" required>{% endif %}
<div class="msg">{{ msg }}</div>
<button type="submit">{{ '가입 신청' if mode=='register' else '로그인' }}</button>
<p style="text-align:center;margin:14px 0 0">
{% if mode=='register' %}이미 계정이 있나요? <a href="/login">로그인</a>
{% else %}처음이신가요? <a href="/register">회원가입</a>{% endif %}</p>
</form></body></html>"""

PAGE_PENDING = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>가입 신청 완료</title>
<style>body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:#f6f7fb;color:#1b1f33;display:flex;min-height:100vh;align-items:center;justify-content:center}
.box{background:#fff;border:1px solid #e6e7f0;border-radius:16px;padding:32px;width:380px;text-align:center;box-shadow:0 10px 30px rgba(30,27,75,.08)}
h1{font-size:22px;margin:0 0 10px}p{color:#5f6478;margin:6px 0}a{display:inline-block;margin-top:16px;color:#fff;background:#4f46e5;padding:11px 18px;border-radius:10px;text-decoration:none;font-weight:700}</style>
</head><body><div class="box">
<h1>✅ 가입 신청이 접수되었습니다</h1>
<p>관리자 <b>승인</b> 후 로그인할 수 있습니다.</p>
<p style="font-size:13.5px">승인되면 로그인해서 <b>내 API 키</b>를 확인하세요.</p>
<a href="/login">로그인 화면으로</a>
</div></body></html>"""

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
<header><h1>📈 내 센서 대시보드</h1><div><b>{{ username }}</b> 님 · {% if is_admin %}<a href="/admin">학급 현황</a> · {% endif %}<a href="/logout">로그아웃</a></div></header>
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

PAGE_ADMIN = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>관리자 · 회원/승인</title>
<style>*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:#f6f7fb;color:#1b1f33}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:20px 24px;display:flex;justify-content:space-between;align-items:center}
header h1{margin:0;font-size:20px}header a{color:#d9f2f7;font-size:14px;text-decoration:none}
.wrap{max-width:920px;margin:0 auto;padding:20px}
h2{font-size:17px;margin:24px 0 8px}
.panel{background:#fff;border:1px solid #e6e7f0;border-radius:14px;padding:6px 4px;box-shadow:0 4px 14px rgba(30,27,75,.05)}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #eef0f5;padding:10px 14px;text-align:left;font-size:14px;vertical-align:middle}
th{background:#f7f7ff;color:#4338ca;font-weight:700}tr:last-child td{border-bottom:0}
.tag{font-size:11px;font-weight:800;color:#5b21b6;background:#ede9fe;border-radius:8px;padding:2px 8px;margin-left:6px}
.muted{color:#9aa3b2}.badge-n{font-size:12px;background:#fef3c7;color:#92400e;border-radius:999px;padding:2px 9px;font-weight:800;margin-left:6px}
button{border:0;border-radius:8px;padding:7px 12px;font-weight:700;font-size:13px;cursor:pointer}
.ok{background:#16a34a;color:#fff}.no{background:#e11d48;color:#fff;margin-left:6px}
.msg{background:#e0f2fe;border:1px solid #bae0f7;color:#075985;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:14px}
form.inline{display:inline}
.create{display:grid;grid-template-columns:repeat(5,1fr) auto;gap:8px;padding:14px}
.create input{padding:9px;border:1px solid #cbcfe0;border-radius:8px;font-size:13.5px;width:100%}
@media(max-width:760px){.create{grid-template-columns:1fr 1fr}}</style></head><body>
<header><h1>🛠 관리자 · 회원/승인</h1>
<div><b>{{ username }}</b> 님 · <a href="/dashboard">내 대시보드</a> · <a href="/logout">로그아웃</a></div></header>
<div class="wrap">
{% if msg %}<div class="msg">{{ msg }}</div>{% endif %}

<h2>승인 대기 {% if pending %}<span class="badge-n">{{ pending|length }}</span>{% endif %}</h2>
<div class="panel"><table>
<tr><th>이름</th><th>소속</th><th>이메일</th><th>아이디</th><th style="width:150px">처리</th></tr>
{% for u in pending %}<tr>
<td>{{ u.name }}</td><td>{{ u.org }}</td><td>{{ u.email }}</td><td>{{ u.username }}</td>
<td>
<form class="inline" method="post" action="/admin/approve"><input type="hidden" name="user_id" value="{{ u.id }}"><button class="ok">승인</button></form>
<form class="inline" method="post" action="/admin/reject"><input type="hidden" name="user_id" value="{{ u.id }}"><button class="no">거절</button></form>
</td></tr>{% else %}<tr><td colspan="5" class="muted">대기 중인 신청이 없습니다.</td></tr>{% endfor %}
</table></div>

<h2>회원 직접 생성 (즉시 승인)</h2>
<div class="panel"><form class="create" method="post" action="/admin/create">
<input name="name" placeholder="이름" required>
<input name="org" placeholder="소속">
<input name="email" type="email" placeholder="이메일">
<input name="username" placeholder="아이디(3자+)" required>
<input name="password" type="password" placeholder="비밀번호(4자+)" required>
<button class="ok" type="submit">생성</button>
</form></div>

<h2>회원 목록 · 수집 현황 <span class="muted" style="font-size:13px">(총 {{ members|length }}명)</span></h2>
<div class="panel"><table>
<tr><th>이름</th><th>소속</th><th>아이디</th><th>샘플 수</th><th>최근값</th><th>최근 시각</th></tr>
{% for m in members %}<tr>
<td>{{ m.name or '-' }}{% if m.is_admin %}<span class="tag">admin</span>{% endif %}</td>
<td>{{ m.org or '-' }}</td><td>{{ m.username }}</td>
<td>{{ m.n }}</td>
<td>{{ '%.1f'|format(m.last_v) if m.last_v is not none else '-' }}</td>
<td>{{ m.last_ts or '-' }}</td>
</tr>{% endfor %}
</table></div>
</div></body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))   # 배포 시 PORT 환경변수로 지정
    print(f"서버 시작: 0.0.0.0:{port}  (배포 시 방화벽에서 이 포트를 개방)")
    app.run(host="0.0.0.0", port=port, debug=False)
