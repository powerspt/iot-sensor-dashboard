# v2_server.py
# -*- coding: utf-8 -*-
"""
방법 2 · 원격 서버 + 계정별 누적 대시보드  (원격 서버에 배포)
------------------------------------------------------------------------
- 학생 ESP32(각자 집)  → POST /api/ingest  (헤더 X-API-Key)  → 사용자별 누적
- 학생 브라우저        → 로그인(세션)      → 자기 데이터만 조회

두 종류의 인증:
  · 장치 → 서버 : API 키 (학생마다 고유)
  · 사람 → 대시보드 : 아이디/비밀번호 로그인(세션)
모든 조회는 세션의 user_id 로 소유권을 확인 → 남의 데이터 접근 차단.

실행:  pip install flask   →   python v2_server.py
배포:  pitchlab 서버의 새 포트로 이 앱을 띄우고 방화벽에서 그 포트를 개방.
       (자세한 배포 체크리스트는 함께 제공된 HTML 가이드 참고)
"""
from flask import (Flask, request, jsonify, session, redirect,
                   url_for, Response, render_template_string, abort, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, datetime, secrets, os, functools, math

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
            value REAL NOT NULL,
            epoch_ms INTEGER)""")
        # 기존 DB 호환: users 없는 컬럼 자동 추가 (기존 사용자는 승인됨 유지)
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        for col, ddl in [("name", "TEXT NOT NULL DEFAULT ''"),
                         ("org", "TEXT NOT NULL DEFAULT ''"),
                         ("email", "TEXT NOT NULL DEFAULT ''"),
                         ("status", "TEXT NOT NULL DEFAULT 'approved'"),
                         ("is_admin", "INTEGER NOT NULL DEFAULT 0")]:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        # readings: epoch_ms(밀리초 정밀 시간) 없으면 추가 + 기존 행 ts로 보정
        rcols = [r[1] for r in c.execute("PRAGMA table_info(readings)").fetchall()]
        if "epoch_ms" not in rcols:
            c.execute("ALTER TABLE readings ADD COLUMN epoch_ms INTEGER")
            c.execute("UPDATE readings SET epoch_ms = CAST(strftime('%s', ts) AS INTEGER)*1000 "
                      "WHERE epoch_ms IS NULL")
        # 조회 성능용 인덱스
        c.execute("CREATE INDEX IF NOT EXISTS idx_readings_uq "
                  "ON readings(user_id, sensor, epoch_ms)")


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
            return redirect(url_for("home"))
        return render_template_string(PAGE_AUTH, mode="login",
               msg="아이디/비밀번호 확인", form=request.form)
    return render_template_string(PAGE_AUTH, mode="login", msg="", form={})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template_string(PAGE_HOME, username=session["username"],
                                  is_admin=session.get("is_admin", False))


BASE_DIR = os.path.dirname(__file__)

# 교재를 서버에서 서빙할 때만 붙이는 이동 버튼(원본 교재 파일은 건드리지 않음)
TEXTBOOK_NAV = """
<div style="position:fixed;bottom:16px;right:16px;z-index:2147483000;display:flex;gap:8px;font-family:system-ui,'Malgun Gothic',sans-serif">
  <a href="/" style="background:#334155;color:#fff;text-decoration:none;font-weight:700;font-size:13.5px;padding:10px 14px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,.22)">🏠 메인</a>
  <a href="/dashboard" style="background:#4338ca;color:#fff;text-decoration:none;font-weight:700;font-size:13.5px;padding:10px 14px;border-radius:12px;box-shadow:0 4px 14px rgba(0,0,0,.22)">📈 대시보드</a>
</div>
"""


@app.route("/textbook")
@login_required
def textbook():
    p = os.path.join(BASE_DIR, "textbook.html")
    if not os.path.exists(p):
        return "교재 파일(textbook.html)이 서버에 없습니다.", 404
    with open(p, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("</body>", TEXTBOOK_NAV + "</body>", 1)   # 이동 버튼 주입
    return Response(html, mimetype="text/html; charset=utf-8")


@app.route("/media/<path:fn>")
@login_required
def media(fn):
    return send_from_directory(os.path.join(BASE_DIR, "media"), fn)


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
    now = datetime.datetime.now()
    ts = now.isoformat(timespec="milliseconds")     # 사람이 읽는 시간(밀리초)
    epoch_ms = int(now.timestamp() * 1000)          # 정밀 시간(집계·필터용)
    with db() as c:
        c.execute("INSERT INTO readings(user_id, ts, sensor, value, epoch_ms) VALUES(?,?,?,?,?)",
                  (row["user_id"], ts, sensor, value, epoch_ms))
    return jsonify(ok=True)


# ================= 브라우저 → 서버 : 내 데이터만 =================
def _target_uid():
    """조회 대상 사용자 id. 관리자만 ?uid= 로 다른 회원을 볼 수 있고, 그 외에는 항상 본인."""
    uid = request.args.get("uid")
    if uid and session.get("is_admin"):
        try:
            return int(uid)
        except ValueError:
            pass
    return session["user_id"]


def _where():
    """요청 파라미터(sensor, from, to)로 WHERE 절과 값 목록 구성."""
    clauses = ["user_id=?"]
    params = [_target_uid()]
    sensor = request.args.get("sensor")
    if sensor:
        clauses.append("sensor=?"); params.append(sensor)
    fr, to = request.args.get("from"), request.args.get("to")
    if fr:
        clauses.append("epoch_ms>=?"); params.append(int(fr))
    if to:
        clauses.append("epoch_ms<=?"); params.append(int(to))
    return " AND ".join(clauses), params


@app.route("/api/my/sensors")
@login_required
def my_sensors():
    with db() as c:
        rows = c.execute("SELECT DISTINCT sensor FROM readings WHERE user_id=? ORDER BY sensor",
                         (_target_uid(),)).fetchall()
    return jsonify([r["sensor"] for r in rows])


@app.route("/api/my/series")
@login_required
def my_series():
    where, params = _where()
    bucket = int(request.args.get("bucket", 0) or 0)     # ms, 0=원본
    limit = min(int(request.args.get("limit", 500)), 5000)
    with db() as c:
        if bucket > 0:                                   # 집계(구간 평균)
            q = (f"SELECT (epoch_ms/{bucket}) AS b, AVG(value) AS v, MAX(epoch_ms) AS t "
                 f"FROM readings WHERE {where} AND epoch_ms IS NOT NULL "
                 f"GROUP BY b ORDER BY b DESC LIMIT ?")
        else:                                            # 원본
            q = (f"SELECT epoch_ms AS t, value AS v FROM readings WHERE {where} "
                 f"ORDER BY id DESC LIMIT ?")
        rows = c.execute(q, (*params, limit)).fetchall()[::-1]
    return jsonify([{"t": r["t"], "v": r["v"]} for r in rows])


@app.route("/api/my/stats")
@login_required
def my_stats():
    where, params = _where()
    th = request.args.get("th")
    with db() as c:
        r = c.execute(f"""SELECT COUNT(*) n, AVG(value) avg, MIN(value) mn, MAX(value) mx,
                          AVG(value*value) sq, MIN(epoch_ms) t0, MAX(epoch_ms) t1
                          FROM readings WHERE {where}""", params).fetchone()
        last2 = c.execute(f"SELECT value FROM readings WHERE {where} ORDER BY id DESC LIMIT 2",
                          params).fetchall()
        over = None
        if th not in (None, ""):
            op = "<" if request.args.get("thdir") == "under" else ">"   # 미만/초과
            o = c.execute(f"SELECT COUNT(*) c FROM readings WHERE {where} AND value{op}?",
                          (*params, float(th))).fetchone()
            over = o["c"]
    avg = r["avg"]
    std = None
    if r["n"] and avg is not None and r["sq"] is not None:
        std = math.sqrt(max(r["sq"] - avg * avg, 0.0))       # 표준편차
    last = last2[0]["value"] if len(last2) >= 1 else None
    prev = last2[1]["value"] if len(last2) >= 2 else None     # 직전 값(증감 계산용)
    return jsonify(count=r["n"], avg=avg, min=r["mn"], max=r["mx"], std=std,
                   last=last, prev=prev, first_ms=r["t0"], last_ms=r["t1"], over=over)


@app.route("/export.csv")
@login_required
def export_csv():
    where, params = _where()
    with db() as c:
        rows = c.execute(f"SELECT ts, sensor, value FROM readings WHERE {where} ORDER BY id",
                         params).fetchall()
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
                                  is_admin=session.get("is_admin", False),
                                  view_uid=None, view_name="")


@app.route("/admin/view/<int:uid>")
@admin_required
def admin_view(uid):
    """관리자가 특정 회원이 수집한 데이터를 대시보드로 열람."""
    with db() as c:
        u = c.execute("SELECT username, name, org FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        return "존재하지 않는 회원입니다.", 404
    label = (u["name"] or u["username"])
    if u["org"]:
        label += f" ({u['org']})"
    return render_template_string(PAGE_DASH, username=session["username"],
                                  keys=[], is_admin=True,
                                  view_uid=uid, view_name=label)


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


@app.route("/admin/delete", methods=["POST"])
@admin_required
def admin_delete():
    """계정 삭제 (승인 대기 거절 · 회원 삭제 공통). 관리자 계정은 보호."""
    uid = request.form.get("user_id")
    with db() as c:
        r = c.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not r:
            return redirect(url_for("admin", msg="이미 없는 계정입니다."))
        if r["is_admin"]:
            return redirect(url_for("admin", msg="관리자 계정은 삭제할 수 없습니다."))
        c.execute("DELETE FROM api_keys WHERE user_id=?", (uid,))
        c.execute("DELETE FROM readings WHERE user_id=?", (uid,))
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    return redirect(url_for("admin", msg="계정을 삭제했습니다(데이터 포함)."))


@app.route("/admin/reset_password", methods=["POST"])
@admin_required
def admin_reset_password():
    """비밀번호 초기화 — 임시 비밀번호를 새로 만들어 화면에 표시(관리자가 학생에게 전달)."""
    uid = request.form.get("user_id")
    temp = secrets.token_urlsafe(6)                 # 임시 비밀번호(8자 안팎)
    with db() as c:
        row = c.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            return redirect(url_for("admin", msg="이미 없는 계정입니다."))
        c.execute("UPDATE users SET password_hash=? WHERE id=?",
                  (generate_password_hash(temp), uid))
    return redirect(url_for("admin",
                    msg=f"'{row['username']}' 임시 비밀번호: {temp}  (학생에게 전달 후 변경 안내)"))


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

PAGE_HOME = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>2026 IoT 캠프 · 홈</title>
<style>
:root{--ink:#1b1f33;--muted:#5f6478;--line:#e6e7f0;--brand:#4f46e5;--bg:#f6f7fb;--card:#fff}
body.dark{--ink:#e7e9f5;--muted:#98a2c4;--line:#2a2f45;--bg:#0f1220;--card:#1a1e2e}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;flex-direction:column;font-family:"Malgun Gothic",system-ui,sans-serif;background:var(--bg);color:var(--ink);transition:background .2s,color .2s}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
header h1{margin:0;font-size:20px}header a{color:#eaf6ff;font-size:14px;text-decoration:none;margin-left:6px}
.htool{display:flex;align-items:center;gap:10px;font-size:14px}
.iconbtn{background:rgba(255,255,255,.16);color:#fff;border:0;border-radius:9px;padding:6px 10px;cursor:pointer;font-weight:700;font-size:13px}
main{flex:1;display:flex;align-items:center;justify-content:center;padding:24px}
.hub{display:flex;gap:24px;flex-wrap:wrap;justify-content:center;width:100%;max-width:720px}
.tile{flex:1 1 280px;max-width:330px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:44px 28px;text-align:center;text-decoration:none;color:var(--ink);box-shadow:0 8px 30px rgba(30,27,75,.07);transition:transform .12s,box-shadow .12s,border-color .12s}
.tile:hover{transform:translateY(-4px);box-shadow:0 14px 40px rgba(30,27,75,.14);border-color:var(--brand)}
.tile .emoji{font-size:56px;line-height:1}
.tile .t{font-size:22px;font-weight:800;margin-top:14px}
.tile .d{font-size:14px;color:var(--muted);margin-top:8px}
</style></head><body>
<header><h1>📡 2026 IoT 캠프</h1>
  <div class="htool"><b>{{ username }}</b> 님
    <button class="iconbtn" id="darkBtn" title="다크 모드">🌓</button>
    {% if is_admin %}<a href="/admin">회원 관리</a>{% endif %}
    <a href="/logout">로그아웃</a></div></header>
<main>
  <div class="hub">
    <a class="tile" href="/textbook"><div class="emoji">📘</div><div class="t">교재 보러 가기</div><div class="d">WiFi 데이터 수집 · Arduino D1 R32</div></a>
    <a class="tile" href="/dashboard"><div class="emoji">📈</div><div class="t">센서 대시보드</div><div class="d">내 데이터 실시간 · 누적 조회</div></a>
  </div>
</main>
<script>
var b=document.getElementById('darkBtn');
function sd(on){document.body.classList.toggle('dark',on);localStorage.setItem('dash_dark',on?'1':'0');}
b.addEventListener('click',function(){sd(!document.body.classList.contains('dark'));});
if(localStorage.getItem('dash_dark')==='1')sd(true);
</script>
</body></html>"""

PAGE_DASH = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>내 센서 대시보드</title>
<style>
:root{--ink:#1b1f33;--muted:#5f6478;--line:#e6e7f0;--brand:#4f46e5;--bg:#f6f7fb;--card:#fff;--soft:#eef0fb}
body.dark{--ink:#e7e9f5;--muted:#98a2c4;--line:#2a2f45;--bg:#0f1220;--card:#1a1e2e;--soft:#232842}
*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:var(--bg);color:var(--ink);transition:background .2s,color .2s}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
header h1{margin:0;font-size:20px}header a{color:#eaf6ff;font-size:14px;text-decoration:none;margin-left:6px}
.htool{display:flex;align-items:center;gap:10px;font-size:14px}
.iconbtn{background:rgba(255,255,255,.16);color:#fff;border:0;border-radius:9px;padding:6px 10px;cursor:pointer;font-weight:700;font-size:13px}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
.keybox{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:16px}
.keybox code{background:var(--soft);color:var(--brand);padding:3px 8px;border-radius:6px;font-family:Consolas,monospace}
.mini{background:var(--soft);color:var(--brand);border:1px solid var(--line);border-radius:7px;padding:2px 9px;font-size:12px;font-weight:700;cursor:pointer;margin-left:6px}
.ctrl{display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 16px;margin-bottom:14px}
.ctrl label{font-size:13px;color:var(--muted);font-weight:700;display:flex;gap:6px;align-items:center}
.ctrl select,.ctrl input{padding:7px 9px;border:1px solid var(--line);border-radius:8px;font-size:13.5px;background:var(--card);color:var(--ink)}
.health{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.pill{display:inline-flex;align-items:center;gap:7px;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:7px 14px;font-size:13px;font-weight:700;color:var(--muted)}
.pill b{color:var(--ink)}
.dot{width:9px;height:9px;border-radius:50%;background:#94a3b8;display:inline-block}
.dot.on{background:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.18)}
.dot.off{background:#dc2626;box-shadow:0 0 0 3px rgba(220,38,38,.18)}
.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:16px}
@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:560px){.cards{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 15px}
.card .k{font-size:12.5px;color:var(--muted);font-weight:700}.card .v{font-size:22px;font-weight:800;margin-top:4px}
.up{color:#16a34a;font-size:14px}.down{color:#dc2626;font-size:14px}.flat{color:var(--muted);font-size:14px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}
canvas{width:100%;height:auto;display:block;cursor:crosshair}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px}
.legend span{display:flex;align-items:center;gap:5px}
.legend i.sw{width:12px;height:3px;border-radius:2px;display:inline-block}
.bar{display:flex;gap:12px;align-items:center;margin-top:14px;flex-wrap:wrap}
button.act{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:9px 15px;font-weight:700;cursor:pointer}
#status{color:var(--muted);font-size:13px}</style></head><body>
<header><h1>📈 내 센서 대시보드</h1>
  <div class="htool"><b>{{ username }}</b> 님
    <button class="iconbtn" id="darkBtn" title="다크 모드">🌓</button>
    <a href="/">홈</a>{% if is_admin %}<a href="/admin">회원 관리</a>{% endif %}
    <a href="/logout">로그아웃</a></div></header>
<div class="wrap">
  {% if view_uid %}
  <div class="keybox" style="background:#fffbeb;border-color:#fcd34d">👤 <b>관리자 보기</b> — <b>{{ view_name }}</b> 님이 수집한 데이터입니다.
    <a href="/admin" style="color:#92400e;font-weight:700;margin-left:6px">← 회원 관리로</a></div>
  {% else %}
  <div class="keybox"><b>내 API 키</b> <span style="color:var(--muted);font-size:13px">(ESP32 코드의 <code>API_KEY</code>에 붙여넣기)</span>
    {% for k in keys %}<div style="margin-top:8px"><code>{{ k.key }}</code> <span style="color:var(--muted);font-size:13px">— {{ k.label }}</span><button class="mini" onclick="copyKey('{{ k.key }}',this)">복사</button></div>{% endfor %}
    <form method="post" action="/keys/new" style="margin-top:10px"><button class="act" type="submit">+ 새 키 발급</button></form>
  </div>
  {% endif %}
  <div class="ctrl">
    <label>센서 <select id="sensor"></select></label>
    <label>범위 <select id="range">
      <option value="recent">최근</option><option value="1h">최근 1시간</option>
      <option value="24h">최근 24시간</option><option value="today">오늘</option>
      <option value="date">기간 지정</option><option value="month">월 지정</option>
      <option value="all">전체</option>
    </select></label>
    <label id="lfrom" style="display:none">시작 <input type="datetime-local" id="from"></label>
    <label id="lto" style="display:none">종료 <input type="datetime-local" id="to"></label>
    <input type="month" id="month" style="display:none">
    <label>집계 <select id="bucket">
      <option value="0">원본</option><option value="1000">1초</option>
      <option value="10000">10초</option><option value="30000">30초</option>
      <option value="60000">1분</option><option value="300000">5분</option>
      <option value="3600000">1시간</option><option value="86400000">1일</option>
    </select></label>
    <label>보기 <select id="view"><option value="line">라인</option><option value="overlay">겹쳐보기</option><option value="multi">나눠보기</option><option value="hist">분포</option></select></label>
    <label title="겹쳐보기에서 센서별 척도를 0~100%로 맞춤"><input type="checkbox" id="norm"> 정규화</label>
    <label>임계값 <input type="number" id="th" step="any" placeholder="예: 3000" style="width:92px">
      <select id="thdir"><option value="over">초과</option><option value="under">미만</option></select></label>
    <label><input type="checkbox" id="ma"> 이동평균</label>
    <label>자동 <select id="auto">
      <option value="0">끄기</option><option value="1000">1초</option>
      <option value="2000" selected>2초</option><option value="5000">5초</option><option value="10000">10초</option>
    </select></label>
    <button class="act" id="refreshBtn" type="button">↻ 새로고침</button>
  </div>
  <div class="health" id="health"></div>
  <div class="cards" id="cards"></div>
  <div class="panel"><canvas id="chart" width="900" height="330"></canvas>
    <div class="legend" id="legend">
      <span><i class="sw" style="background:#6366f1"></i>값</span>
      <span><i class="sw" style="background:#f59e0b"></i>이동평균</span>
      <span><i class="sw" style="background:#dc2626"></i>임계선</span>
      <span>● <span style="color:#0ea5e9">최소</span> · <span style="color:#f97316">최대</span> · <span style="color:#6366f1">현재</span></span>
    </div>
  </div>
  <div class="bar"><button class="act" onclick="location.href='/export.csv?'+qs()">⬇ CSV 내보내기</button><span id="status">연결 중…</span></div>
</div>
<script>
var $=function(id){return document.getElementById(id);};
var elS=$('sensor'),elR=$('range'),elB=$('bucket'),elFrom=$('from'),elTo=$('to'),elMonth=$('month'),
    elTh=$('th'),elThdir=$('thdir'),elMA=$('ma'),elAuto=$('auto'),elView=$('view'),elNorm=$('norm'),chart=$('chart'),lastSeries=[],geo=null;
var VIEW_UID={% if view_uid %}{{ view_uid }}{% else %}null{% endif %};   // 관리자가 특정 회원을 볼 때만 값이 있음
var PALETTE=['#6366f1','#0ea5e9','#f97316','#16a34a','#e11d48','#a855f7','#eab308','#14b8a6'],
    STATIC_LEGEND='',HIST_LEGEND='<span>막대 = 빈도</span><span><i class="sw" style="background:#f97316"></i>평균</span>';
function fmt(x){return (x==null)?'-':(Math.round(x*10)/10);}
function getTh(){var v=parseFloat(elTh.value);return isNaN(v)?null:v;}
function tlabel(ms){return new Date(ms).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
function dtLocal(ms){var d=new Date(ms);function p(n){return (n<10?'0':'')+n;}
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes());}
function ago(ms){var s=Math.round((Date.now()-ms)/1000);if(s<0)s=0;
  if(s<60)return s+'초 전';if(s<3600)return Math.round(s/60)+'분 전';if(s<86400)return Math.round(s/3600)+'시간 전';return Math.round(s/86400)+'일 전';}
function copyKey(k,btn){function ok(){btn.textContent='복사됨';setTimeout(function(){btn.textContent='복사';},1200);}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(k).then(ok,function(){});}}
function card(k,v,extra){return '<div class="card"><div class="k">'+k+'</div><div class="v">'+v+(extra||'')+'</div></div>';}
function deltaHTML(cur,prev){if(cur==null||prev==null)return '';var d=cur-prev,a=Math.abs(Math.round(d*10)/10);
  if(a<1e-9)return ' <span class="flat">→0</span>';return ' <span class="'+(d>0?'up':'down')+'">'+(d>0?'▲':'▼')+a+'</span>';}
function renderCards(s){$('cards').innerHTML=
  card('현재값',fmt(s.last),deltaHTML(s.last,s.prev))+card('평균',fmt(s.avg))+card('표준편차',fmt(s.std))
  +card('최소',fmt(s.min))+card('최대',fmt(s.max))+card('샘플 수',s.count);}
function renderHealth(s){var h='';
  if(s.last_ms){var age=Date.now()-s.last_ms,on=age<15000;
    h+='<span class="pill"><span class="dot '+(on?'on':'off')+'"></span>'+(on?'수신 중':'수신 없음')+' <b>'+ago(s.last_ms)+'</b></span>';}
  else h+='<span class="pill"><span class="dot"></span>데이터 없음</span>';
  if(s.count>1&&s.first_ms&&s.last_ms&&s.last_ms>s.first_ms){var pm=s.count/((s.last_ms-s.first_ms)/60000);
    h+='<span class="pill">수집 속도 <b>'+(pm>=10?Math.round(pm):Math.round(pm*10)/10)+' 개/분</b></span>';}
  var th=getTh();
  if(th!=null&&s.over!=null){var pct=s.count?Math.round(s.over/s.count*100):0,word=(elThdir.value==='under')?'미만':'초과';
    h+='<span class="pill">임계('+th+') '+word+' <b>'+s.over+'회</b> ('+pct+'%)</span>';}
  $('health').innerHTML=h;}
function C(){var d=document.body.classList.contains('dark');
  return {line:'#6366f1',area:d?'rgba(99,102,241,.20)':'rgba(99,102,241,.12)',grid:d?'#2a3050':'#eceef7',
    txt:d?'#98a2c4':'#5f6478',mn:'#0ea5e9',mx:'#f97316',th:'#dc2626',ma:'#f59e0b',tip:d?'#0b0e17':'#111827'};}
function movavg(a,w){var out=[],s=0;for(var i=0;i<a.length;i++){s+=a[i];if(i>=w)s-=a[i-w];out.push(s/Math.min(i+1,w));}return out;}
function rr(ctx,x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();}
function outlierInfo(vs){if(vs.length<3)return {n:0,mean:null,sd:0};var m=0;vs.forEach(function(v){m+=v;});m/=vs.length;
  var s=0;vs.forEach(function(v){s+=(v-m)*(v-m);});s=Math.sqrt(s/vs.length);var n=0;
  if(s>0)vs.forEach(function(v){if(Math.abs(v-m)>2.5*s)n++;});return {n:n,mean:m,sd:s};}
function seriesUrl(nm){var p=new URLSearchParams(qs());p.set('sensor',nm);return '/api/my/series?'+p.toString();}
function sensorsUrl(){return '/api/my/sensors'+(VIEW_UID?('?uid='+VIEW_UID):'');}  // 관리자 열람 시 대상 회원
function sensorLegend(maps){var v=maps.filter(function(m){return m.pts&&m.pts.length;});
  if(!v.length)return '<span>데이터 없음</span>';
  return v.map(function(m,i){return '<span><i class="sw" style="background:'+PALETTE[i%PALETTE.length]+'"></i>'+m.name+'</span>';}).join('');}
function drawOverlay(maps){var ctx=chart.getContext('2d'),W=chart.width,H=chart.height,pL=50,pR=16,pT=28,pB=30,c=C();
  ctx.clearRect(0,0,W,H);geo=null;var norm=elNorm.checked;
  var v=maps.filter(function(m){return m.pts&&m.pts.length>=2;});
  if(!v.length){ctx.fillStyle=c.txt;ctx.font='15px sans-serif';ctx.fillText('데이터가 없습니다',pL,H/2);return;}
  var t0=Infinity,t1=-Infinity,lo=Infinity,hi=-Infinity;
  v.forEach(function(m){m.vs=m.pts.map(function(p){return p.v;});t0=Math.min(t0,m.pts[0].t);t1=Math.max(t1,m.pts[m.pts.length-1].t);
    if(norm){var a=Math.min.apply(null,m.vs),b=Math.max.apply(null,m.vs),rg=(b-a)||1;m.nv=m.vs.map(function(x){return (x-a)/rg;});}
    else{lo=Math.min(lo,Math.min.apply(null,m.vs));hi=Math.max(hi,Math.max.apply(null,m.vs));}});
  if(norm){lo=0;hi=1;}var rng=(hi-lo)||1;if(!norm){lo-=rng*0.08;hi+=rng*0.08;rng=hi-lo;}var tr=(t1-t0)||1;
  function X(t){return pL+(W-pL-pR)*((t-t0)/tr);}function Y(val){return (H-pB)-(H-pB-pT)*((val-lo)/rng);}
  ctx.strokeStyle=c.grid;ctx.lineWidth=1;ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='right';
  for(var g=0;g<=4;g++){var yy=pT+(H-pB-pT)*g/4,val=hi-rng*g/4;ctx.beginPath();ctx.moveTo(pL,yy);ctx.lineTo(W-pR,yy);ctx.stroke();
    ctx.fillText(norm?(Math.round((1-g/4)*100)+'%'):String(Math.round(val*10)/10),pL-6,yy+4);}
  v.forEach(function(m,idx){var col=PALETTE[idx%PALETTE.length],arr=norm?m.nv:m.vs;
    ctx.beginPath();for(var i=0;i<arr.length;i++){var x=X(m.pts[i].t),y=Y(arr[i]);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
    ctx.strokeStyle=col;ctx.lineWidth=1.8;ctx.stroke();});
  ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='left';ctx.fillText(tlabel(t0),pL,H-8);
  ctx.textAlign='right';ctx.fillText(tlabel(t1),W-pR,H-8);ctx.textAlign='left';}
function drawMulti(maps){var ctx=chart.getContext('2d'),W=chart.width,H=chart.height,c=C();
  ctx.clearRect(0,0,W,H);geo=null;
  var v=maps.filter(function(m){return m.pts&&m.pts.length>=2;});
  if(!v.length){ctx.fillStyle=c.txt;ctx.font='15px sans-serif';ctx.fillText('데이터가 없습니다',20,H/2);return;}
  var n=v.length,cols=Math.ceil(Math.sqrt(n)),rows=Math.ceil(n/cols),gw=W/cols,gh=H/rows,pad=12;
  v.forEach(function(m,idx){var cx=(idx%cols)*gw,cy=Math.floor(idx/cols)*gh,col=PALETTE[idx%PALETTE.length];
    var vs=m.pts.map(function(p){return p.v;}),mn=Math.min.apply(null,vs),mx=Math.max.apply(null,vs),rg=(mx-mn)||1;
    var x0=cx+pad+30,y0=cy+24,pw=gw-pad*2-30,ph=gh-pad*2-24;
    ctx.strokeStyle=c.grid;ctx.lineWidth=1;ctx.strokeRect(x0,y0,pw,ph);
    ctx.beginPath();for(var i=0;i<vs.length;i++){var x=x0+pw*(i/(vs.length-1)),y=y0+ph-ph*((vs[i]-mn)/rg);i?ctx.lineTo(x,y):ctx.moveTo(x,y);}
    ctx.strokeStyle=col;ctx.lineWidth=1.6;ctx.stroke();
    ctx.fillStyle=col;ctx.beginPath();ctx.arc(x0+pw,y0+ph-ph*((vs[vs.length-1]-mn)/rg),3,0,7);ctx.fill();
    ctx.fillStyle=c.txt;ctx.font='12px sans-serif';ctx.textAlign='left';ctx.fillText(m.name,cx+pad,cy+16);
    ctx.font='10px sans-serif';ctx.fillText(String(Math.round(mx*10)/10),x0-28,y0+8);ctx.fillText(String(Math.round(mn*10)/10),x0-28,y0+ph);});}
function drawHist(series,s){var ctx=chart.getContext('2d'),W=chart.width,H=chart.height,pL=50,pR=16,pT=16,pB=34,c=C();
  ctx.clearRect(0,0,W,H);geo=null;var vs=(series||[]).map(function(p){return p.v;});
  if(vs.length<2){ctx.fillStyle=c.txt;ctx.font='15px sans-serif';ctx.fillText('데이터가 없습니다',pL,H/2);return;}
  var mn=Math.min.apply(null,vs),mx=Math.max.apply(null,vs);if(mx===mn)mx=mn+1;
  var bins=Math.min(20,Math.max(6,Math.round(Math.sqrt(vs.length)))),counts=[],bw=(mx-mn)/bins,i;
  for(i=0;i<bins;i++)counts.push(0);
  vs.forEach(function(val){var bi=Math.min(bins-1,Math.floor((val-mn)/bw));counts[bi]++;});
  var cmax=Math.max.apply(null,counts)||1,pw=W-pL-pR;
  ctx.strokeStyle=c.grid;ctx.lineWidth=1;ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='right';
  for(var g=0;g<=4;g++){var yy=pT+(H-pB-pT)*g/4,cval=Math.round(cmax*(1-g/4));ctx.beginPath();ctx.moveTo(pL,yy);ctx.lineTo(W-pR,yy);ctx.stroke();ctx.fillText(String(cval),pL-6,yy+4);}
  for(i=0;i<bins;i++){var bx=pL+pw*(i/bins),bwid=pw/bins-2,bh=(H-pB-pT)*(counts[i]/cmax);
    ctx.fillStyle='#6366f1';ctx.globalAlpha=.85;ctx.fillRect(bx+1,(H-pB)-bh,bwid,bh);ctx.globalAlpha=1;}
  if(s&&s.avg!=null){var ax=pL+pw*((s.avg-mn)/((mx-mn)||1));ctx.strokeStyle=c.mx;ctx.lineWidth=1.5;ctx.setLineDash([5,3]);
    ctx.beginPath();ctx.moveTo(ax,pT);ctx.lineTo(ax,H-pB);ctx.stroke();ctx.setLineDash([]);}
  ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='left';ctx.fillText(String(Math.round(mn*10)/10),pL,H-10);
  ctx.textAlign='center';ctx.fillText('값 구간 · 빈도',W/2,H-10);
  ctx.textAlign='right';ctx.fillText(String(Math.round(mx*10)/10),W-pR,H-10);ctx.textAlign='left';}
function drawChart(pts,hover){var ctx=chart.getContext('2d'),W=chart.width,H=chart.height,pL=50,pR=16,pT=16,pB=30,c=C();
  ctx.clearRect(0,0,W,H);geo=null;
  if(!pts||pts.length<2){ctx.fillStyle=c.txt;ctx.font='15px sans-serif';ctx.fillText('데이터가 없습니다',pL,H/2);return;}
  var vs=pts.map(function(p){return p.v;});
  var mn=Math.min.apply(null,vs),mx=Math.max.apply(null,vs);
  var th=getTh(),lo=mn,hi=mx;if(th!=null){lo=Math.min(lo,th);hi=Math.max(hi,th);}
  var rng=(hi-lo)||1;lo-=rng*0.08;hi+=rng*0.08;rng=hi-lo;
  function X(i){return pL+(W-pL-pR)*(i/(vs.length-1));}
  function Y(v){return (H-pB)-(H-pB-pT)*((v-lo)/rng);}
  ctx.strokeStyle=c.grid;ctx.lineWidth=1;ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='right';
  for(var g=0;g<=4;g++){var yy=pT+(H-pB-pT)*g/4,val=hi-rng*g/4;
    ctx.beginPath();ctx.moveTo(pL,yy);ctx.lineTo(W-pR,yy);ctx.stroke();
    ctx.fillText(String(Math.round(val*10)/10),pL-6,yy+4);}
  ctx.beginPath();ctx.moveTo(X(0),Y(vs[0]));for(var i=1;i<vs.length;i++)ctx.lineTo(X(i),Y(vs[i]));
  ctx.lineTo(X(vs.length-1),H-pB);ctx.lineTo(X(0),H-pB);ctx.closePath();ctx.fillStyle=c.area;ctx.fill();
  ctx.beginPath();for(var j=0;j<vs.length;j++){var x=X(j),y=Y(vs[j]);j?ctx.lineTo(x,y):ctx.moveTo(x,y);}
  ctx.strokeStyle=c.line;ctx.lineWidth=2;ctx.stroke();
  if(elMA.checked){var w=Math.max(2,Math.round(vs.length/20)),ma=movavg(vs,w);
    ctx.beginPath();for(var k=0;k<ma.length;k++){var ax=X(k),ay=Y(ma[k]);k?ctx.lineTo(ax,ay):ctx.moveTo(ax,ay);}
    ctx.strokeStyle=c.ma;ctx.lineWidth=1.6;ctx.setLineDash([5,3]);ctx.stroke();ctx.setLineDash([]);}
  if(th!=null){var ty=Y(th);ctx.strokeStyle=c.th;ctx.lineWidth=1.3;ctx.setLineDash([6,4]);
    ctx.beginPath();ctx.moveTo(pL,ty);ctx.lineTo(W-pR,ty);ctx.stroke();ctx.setLineDash([]);}
  function dot(i,col){ctx.beginPath();ctx.arc(X(i),Y(vs[i]),3.6,0,7);ctx.fillStyle=col;ctx.fill();}
  dot(vs.indexOf(mn),c.mn);dot(vs.indexOf(mx),c.mx);dot(vs.length-1,c.line);
  var oi=outlierInfo(vs);                                   // 이상치(평균±2.5σ) 빨간 링
  if(oi.sd>0){ctx.strokeStyle=c.th;ctx.lineWidth=2;for(var q=0;q<vs.length;q++){if(Math.abs(vs[q]-oi.mean)>2.5*oi.sd){ctx.beginPath();ctx.arc(X(q),Y(vs[q]),5.5,0,7);ctx.stroke();}}}
  ctx.fillStyle=c.txt;ctx.font='11px sans-serif';ctx.textAlign='left';ctx.fillText(tlabel(pts[0].t),pL,H-8);
  ctx.textAlign='right';ctx.fillText(tlabel(pts[pts.length-1].t),W-pR,H-8);ctx.textAlign='left';
  geo={X:X,Y:Y};
  if(hover!=null){var hx=X(hover),hy=Y(vs[hover]);
    ctx.strokeStyle=c.txt;ctx.globalAlpha=.45;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(hx,pT);ctx.lineTo(hx,H-pB);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;
    ctx.beginPath();ctx.arc(hx,hy,4.5,0,7);ctx.fillStyle=c.line;ctx.fill();
    var t=fmt(vs[hover])+'  ·  '+tlabel(pts[hover].t);ctx.font='12px sans-serif';var tw=ctx.measureText(t).width+14;
    var bx=Math.min(Math.max(hx-tw/2,pL),W-pR-tw),by=pT+2;
    ctx.fillStyle=c.tip;ctx.globalAlpha=.92;rr(ctx,bx,by,tw,23,6);ctx.fill();ctx.globalAlpha=1;
    ctx.fillStyle='#fff';ctx.textAlign='left';ctx.fillText(t,bx+7,by+16);}}
chart.addEventListener('mousemove',function(e){if(!geo||lastSeries.length<2)return;
  var r=chart.getBoundingClientRect(),mx=(e.clientX-r.left)*(chart.width/r.width);
  var n=lastSeries.length,best=0,bd=1e9;for(var i=0;i<n;i++){var d=Math.abs(geo.X(i)-mx);if(d<bd){bd=d;best=i;}}
  drawChart(lastSeries,best);});
chart.addEventListener('mouseleave',function(){if(elView.value==='line')drawChart(lastSeries,null);});
function range_(){var r=elR.value,now=Date.now(),from=null,to=null;
  if(r==='1h')from=now-3600e3;else if(r==='24h')from=now-86400e3;
  else if(r==='today'){var d=new Date();d.setHours(0,0,0,0);from=d.getTime();}
  else if(r==='date'){if(elFrom.value)from=new Date(elFrom.value).getTime();if(elTo.value)to=new Date(elTo.value).getTime();}
  else if(r==='month'&&elMonth.value){var p=elMonth.value.split('-');from=new Date(+p[0],+p[1]-1,1).getTime();to=new Date(+p[0],+p[1],1).getTime();}
  return {from:from,to:to};}
function qs(){var p=new URLSearchParams();if(elS.value)p.set('sensor',elS.value);
  var rg=range_();if(rg.from)p.set('from',Math.floor(rg.from));if(rg.to)p.set('to',Math.floor(rg.to));
  p.set('bucket',elB.value);p.set('limit',(elR.value==='recent')?'150':'3000');
  if(VIEW_UID)p.set('uid',VIEW_UID);                 // 관리자 열람 시 대상 회원 지정
  return p.toString();}
async function loadSensors(){var cur=elS.value;
  var list=await (await fetch(sensorsUrl())).json();
  if(!list.length){elS.innerHTML='<option value="">(데이터 없음)</option>';return;}
  elS.innerHTML=list.map(function(s){return '<option'+(s===cur?' selected':'')+'>'+s+'</option>';}).join('');}
async function refresh(){try{var view=elView.value,p=qs(),th=getTh();
  var s=await (await fetch('/api/my/stats?'+p+(th!=null?('&th='+th+'&thdir='+elThdir.value):''))).json();
  renderCards(s);renderHealth(s);
  if(view==='overlay'||view==='multi'){
    var list=await (await fetch(sensorsUrl())).json();
    var maps=await Promise.all(list.map(function(nm){return fetch(seriesUrl(nm)).then(function(r){return r.json();}).then(function(d){return {name:nm,pts:d};});}));
    lastSeries=[];$('legend').innerHTML=sensorLegend(maps);
    if(view==='overlay')drawOverlay(maps);else drawMulti(maps);
    $('status').textContent='갱신 '+new Date().toLocaleTimeString()+' · '+list.length+'개 센서';
  }else{
    var series=await (await fetch('/api/my/series?'+p)).json();lastSeries=series;
    if(view==='hist'){drawHist(series,s);$('legend').innerHTML=HIST_LEGEND;}
    else{drawChart(series,null);$('legend').innerHTML=STATIC_LEGEND;
      var oi=outlierInfo(series.map(function(x){return x.v;}));
      if(oi.n>0)$('health').innerHTML+='<span class="pill">이상치 <b>'+oi.n+'개</b> (±2.5σ)</span>';}
    $('status').textContent='갱신 '+new Date().toLocaleTimeString()+' · '+series.length+'점';
  }
}catch(e){$('status').textContent='대기…';}}
var timer=null;
function reschedule(){if(timer){clearInterval(timer);timer=null;}var iv=+elAuto.value;if(iv>0)timer=setInterval(tick,iv);}
async function tick(){await loadSensors();await refresh();}
function setDark(on){document.body.classList.toggle('dark',on);localStorage.setItem('dash_dark',on?'1':'0');drawChart(lastSeries,null);}
elR.addEventListener('change',function(){var d=(elR.value==='date');
  $('lfrom').style.display=d?'':'none';$('lto').style.display=d?'':'none';
  elMonth.style.display=(elR.value==='month')?'':'none';
  if(d&&!elFrom.value&&!elTo.value){elFrom.value=dtLocal(Date.now()-3600e3);elTo.value=dtLocal(Date.now());}
  refresh();});
[elS,elB,elFrom,elTo,elMonth,elTh,elThdir,elMA,elView,elNorm].forEach(function(e){e.addEventListener('change',refresh);});
elAuto.addEventListener('change',reschedule);
$('refreshBtn').addEventListener('click',tick);
$('darkBtn').addEventListener('click',function(){setDark(!document.body.classList.contains('dark'));});
(async function(){STATIC_LEGEND=$('legend').innerHTML;if(localStorage.getItem('dash_dark')==='1')setDark(true);
  await loadSensors();await refresh();reschedule();})();
</script></body></html>"""

PAGE_ADMIN = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>회원 관리 (관리자)</title>
<style>
:root{--ink:#1b1f33;--muted:#5f6478;--line:#e6e7f0;--brand:#4f46e5;--bg:#f6f7fb;--card:#fff;--soft:#eef0fb;--th:#f7f7ff}
body.dark{--ink:#e7e9f5;--muted:#98a2c4;--line:#2a2f45;--brand:#8b8ff7;--bg:#0f1220;--card:#1a1e2e;--soft:#232842;--th:#1f2440}
*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic",system-ui,sans-serif;background:var(--bg);color:var(--ink);transition:background .2s,color .2s}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
header h1{margin:0;font-size:20px}header a{color:#eaf6ff;font-size:14px;text-decoration:none;margin-left:6px}
.htool{display:flex;align-items:center;gap:10px;font-size:14px}
.iconbtn{background:rgba(255,255,255,.16);color:#fff;border:0;border-radius:9px;padding:6px 10px;cursor:pointer;font-weight:700;font-size:13px}
.wrap{max-width:960px;margin:0 auto;padding:20px}
.summary{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px}
.pill{display:inline-flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:8px 16px;font-size:13px;font-weight:700;color:var(--muted)}
.pill b{color:var(--ink);font-size:16px}
h2{font-size:16px;margin:22px 0 8px;display:flex;align-items:center;gap:8px}
.badge-n{font-size:12px;background:#fef3c7;color:#92400e;border-radius:999px;padding:2px 9px;font-weight:800}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid var(--line);padding:10px 14px;text-align:left;font-size:14px;vertical-align:middle}
th{background:var(--th);color:var(--brand);font-weight:700}tr:last-child td{border-bottom:0}
tbody tr:hover td,table tr:hover td{background:var(--soft)}
.tag{font-size:11px;font-weight:800;color:#6d28d9;background:#ede9fe;border-radius:8px;padding:2px 8px;margin-left:6px}
.muted{color:var(--muted)}.on{color:#16a34a;font-weight:700}.off{color:var(--muted)}
.msg{background:#e0f2fe;border:1px solid #bae0f7;color:#075985;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:14px}
form.inline{display:inline}
button{border:0;border-radius:8px;padding:7px 12px;font-weight:700;font-size:13px;cursor:pointer}
.ok{background:#16a34a;color:#fff}.no{background:#e11d48;color:#fff;margin-left:6px}.info{background:#0284c7;color:#fff}
a.abtn{display:inline-block;background:var(--brand);color:#fff;border-radius:8px;padding:7px 12px;font-weight:700;font-size:13px;text-decoration:none;margin-right:6px}
.create{display:grid;grid-template-columns:repeat(5,1fr) auto;gap:8px;padding:14px}
.create input{padding:9px;border:1px solid var(--line);border-radius:8px;font-size:13.5px;width:100%;background:var(--card);color:var(--ink)}
@media(max-width:760px){.create{grid-template-columns:1fr 1fr}}</style></head><body>
<header><h1>🛠 회원 관리</h1>
  <div class="htool"><b>{{ username }}</b> 님
    <button class="iconbtn" id="darkBtn" title="다크 모드">🌓</button>
    <a href="/dashboard">내 대시보드</a><a href="/logout">로그아웃</a></div></header>
<div class="wrap">
{% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
{% set ns = namespace(active=0) %}{% for m in members %}{% if m.n %}{% set ns.active = ns.active + 1 %}{% endif %}{% endfor %}
  <div class="summary">
    <span class="pill">총 회원 <b>{{ members|length }}</b></span>
    <span class="pill">승인 대기 <b>{{ pending|length }}</b></span>
    <span class="pill">데이터 수집 회원 <b>{{ ns.active }}</b></span>
  </div>

  <h2>승인 대기 {% if pending %}<span class="badge-n">{{ pending|length }}</span>{% endif %}</h2>
  <div class="panel"><table>
  <tr><th>이름</th><th>소속</th><th>이메일</th><th>아이디</th><th style="width:150px">처리</th></tr>
  {% for u in pending %}<tr>
  <td>{{ u.name }}</td><td>{{ u.org }}</td><td>{{ u.email }}</td><td>{{ u.username }}</td>
  <td>
  <form class="inline" method="post" action="/admin/approve"><input type="hidden" name="user_id" value="{{ u.id }}"><button class="ok">승인</button></form>
  <form class="inline" method="post" action="/admin/delete"><input type="hidden" name="user_id" value="{{ u.id }}"><button class="no">거절</button></form>
  </td></tr>{% else %}<tr><td colspan="5" class="muted">대기 중인 신청이 없습니다.</td></tr>{% endfor %}
  </table></div>

  <h2>회원 직접 생성 <span class="muted" style="font-size:13px;font-weight:400">(즉시 승인)</span></h2>
  <div class="panel"><form class="create" method="post" action="/admin/create">
  <input name="name" placeholder="이름" required>
  <input name="org" placeholder="소속">
  <input name="email" type="email" placeholder="이메일">
  <input name="username" placeholder="아이디(3자+)" required>
  <input name="password" type="password" placeholder="비밀번호(4자+)" required>
  <button class="ok" type="submit">생성</button>
  </form></div>

  <h2>회원 목록 · 수집 현황 <span class="muted" style="font-size:13px;font-weight:400">(총 {{ members|length }}명)</span></h2>
  <div class="panel"><table>
  <tr><th>이름</th><th>소속</th><th>아이디</th><th>샘플 수</th><th>최근값</th><th>최근 시각</th><th style="width:320px">관리</th></tr>
  {% for m in members %}<tr>
  <td>{{ m.name or '-' }}{% if m.is_admin %}<span class="tag">admin</span>{% endif %}</td>
  <td>{{ m.org or '-' }}</td><td>{{ m.username }}</td>
  <td>{% if m.n %}<span class="on">{{ m.n }}</span>{% else %}<span class="off">0</span>{% endif %}</td>
  <td>{{ '%.1f'|format(m.last_v) if m.last_v is not none else '-' }}</td>
  <td>{{ m.last_ts or '-' }}</td>
  <td><a class="abtn" href="/admin/view/{{ m.id }}">📈 데이터 보기</a>{% if not m.is_admin %}
  <form class="inline" method="post" action="/admin/reset_password"><input type="hidden" name="user_id" value="{{ m.id }}"><button class="info">비번 초기화</button></form>
  <form class="inline" method="post" action="/admin/delete" onsubmit="return confirm('{{ m.username }} 계정과 데이터를 삭제할까요?')"><input type="hidden" name="user_id" value="{{ m.id }}"><button class="no">삭제</button></form>
  {% endif %}</td>
  </tr>{% endfor %}
  </table></div>
</div>
<script>
var b=document.getElementById('darkBtn');
function sd(on){document.body.classList.toggle('dark',on);localStorage.setItem('dash_dark',on?'1':'0');}
b.addEventListener('click',function(){sd(!document.body.classList.contains('dark'));});
if(localStorage.getItem('dash_dark')==='1')sd(true);
</script>
</body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))   # 배포 시 PORT 환경변수로 지정
    print(f"서버 시작: 0.0.0.0:{port}  (배포 시 방화벽에서 이 포트를 개방)")
    app.run(host="0.0.0.0", port=port, debug=False)
