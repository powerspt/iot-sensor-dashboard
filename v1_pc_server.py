# v1_pc_server.py
# -*- coding: utf-8 -*-
"""
방법 1 · 로컬 PC 실시간 센서 대시보드 (수집 서버)
------------------------------------------------------------
ESP32(D1 R32)가 같은 WiFi에서 이 PC로 센서 값을 POST 하면,
SQLite에 누적하고 브라우저 대시보드(실시간 차트 + 통계)로 보여 줍니다.

실행:  pip install flask   →   python v1_pc_server.py
확인:  같은 PC의 브라우저에서  http://localhost:5000
장치:  ESP32는  http://<이 PC의 IP>:5000/ingest  로 POST
※ 인터넷 없이도 동작합니다(차트는 순수 자바스크립트로 그림).
"""
from flask import Flask, request, jsonify, Response
import sqlite3, datetime, os

DB = os.path.join(os.path.dirname(__file__), "sensor_data.db")
app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS readings(
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            ts     TEXT NOT NULL,
            sensor TEXT NOT NULL,
            value  REAL NOT NULL)""")


# ---- 장치 → 서버 : 데이터 수신 ----
@app.route("/ingest", methods=["POST"])
def ingest():
    data = request.get_json(force=True, silent=True) or {}
    sensor = str(data.get("sensor", "sensor"))
    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="value(숫자)가 필요합니다"), 400
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with db() as c:
        c.execute("INSERT INTO readings(ts, sensor, value) VALUES(?,?,?)",
                  (ts, sensor, value))
    return jsonify(ok=True)


# ---- 브라우저 → 서버 : 조회 ----
@app.route("/api/series")
def api_series():
    limit = min(int(request.args.get("limit", 120)), 2000)
    with db() as c:
        rows = c.execute("SELECT ts, value FROM readings ORDER BY id DESC LIMIT ?",
                         (limit,)).fetchall()
    rows = rows[::-1]  # 오래된 → 최신 순으로
    return jsonify([{"ts": r["ts"], "value": r["value"]} for r in rows])


@app.route("/api/stats")
def api_stats():
    with db() as c:
        r = c.execute("""SELECT COUNT(*) n, AVG(value) avg,
                                MIN(value) mn, MAX(value) mx FROM readings""").fetchone()
        last = c.execute("SELECT value FROM readings ORDER BY id DESC LIMIT 1").fetchone()
    return jsonify(count=r["n"], avg=r["avg"], min=r["mn"], max=r["mx"],
                   last=(last["value"] if last else None))


@app.route("/export.csv")
def export_csv():
    with db() as c:
        rows = c.execute("SELECT ts, sensor, value FROM readings ORDER BY id").fetchall()
    lines = ["time,sensor,value"] + [f'{r["ts"]},{r["sensor"]},{r["value"]}' for r in rows]
    return Response("\n".join(lines), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sensor_data.csv"})


@app.route("/")
def dashboard():
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>실시간 센서 대시보드 (로컬)</title>
<style>
:root{--ink:#1b1f33;--muted:#5f6478;--line:#e6e7f0;--brand:#4f46e5}
*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic","맑은 고딕",system-ui,sans-serif;background:#f6f7fb;color:var(--ink)}
header{background:linear-gradient(135deg,#0e7490,#4338ca);color:#fff;padding:22px 24px}
header h1{margin:0;font-size:22px}header p{margin:4px 0 0;color:#d9f2f7;font-size:14px}
.wrap{max-width:960px;margin:0 auto;padding:20px}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px}
@media(max-width:720px){.cards{grid-template-columns:repeat(2,1fr)}}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:0 4px 14px rgba(30,27,75,.05)}
.card .k{font-size:12.5px;color:var(--muted);font-weight:700}
.card .v{font-size:24px;font-weight:800;margin-top:4px}
.panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:0 4px 14px rgba(30,27,75,.05)}
canvas{width:100%;height:auto;display:block}
.bar{display:flex;align-items:center;gap:12px;margin-top:14px}
button{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:700;font-size:14px;cursor:pointer}
#status{color:var(--muted);font-size:13px}
</style></head><body>
<header><h1>📈 실시간 센서 대시보드 <span style="opacity:.7;font-size:14px">· 로컬 PC</span></h1>
<p>ESP32가 보낸 값을 실시간으로 수집·시각화합니다 (인터넷 불필요)</p></header>
<div class="wrap">
  <div class="cards" id="cards"></div>
  <div class="panel"><canvas id="chart" width="900" height="320"></canvas></div>
  <div class="bar"><button onclick="location.href='/export.csv'">⬇ CSV 내보내기</button><span id="status">연결 중…</span></div>
</div>
<script>
function card(k,v){return '<div class="card"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>';}
function fmt(x){return (x==null)?'-':(Math.round(x*10)/10);}
function renderCards(s){
  document.getElementById('cards').innerHTML =
    card('현재값', fmt(s.last)) + card('평균', fmt(s.avg)) +
    card('최소', fmt(s.min)) + card('최대', fmt(s.max)) + card('샘플 수', s.count);
}
function drawChart(v){
  const c=document.getElementById('chart'), ctx=c.getContext('2d');
  const W=c.width, H=c.height, pad=40;
  ctx.clearRect(0,0,W,H);
  if(v.length<2){ ctx.fillStyle='#9aa3b2'; ctx.font='16px sans-serif';
    ctx.fillText('데이터를 기다리는 중…', pad, H/2); return; }
  const mn=Math.min(...v), mx=Math.max(...v), rng=(mx-mn)||1;
  ctx.strokeStyle='#e2e6f0'; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(pad,H-pad); ctx.lineTo(W-10,H-pad);
  ctx.moveTo(pad,10); ctx.lineTo(pad,H-pad); ctx.stroke();
  ctx.strokeStyle='#4f46e5'; ctx.lineWidth=2; ctx.beginPath();
  v.forEach((val,i)=>{ const x=pad+(W-pad-10)*(i/(v.length-1));
    const y=(H-pad)-(H-pad-10)*((val-mn)/rng); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
  ctx.stroke();
  ctx.fillStyle='#5f6478'; ctx.font='12px sans-serif';
  ctx.fillText(String(Math.round(mx)), 6, 16);
  ctx.fillText(String(Math.round(mn)), 6, H-pad);
}
async function refresh(){
  try{
    const s = await (await fetch('/api/stats')).json();
    const series = await (await fetch('/api/series?limit=120')).json();
    renderCards(s); drawChart(series.map(p=>p.value));
    document.getElementById('status').textContent = '최근 갱신 ' + new Date().toLocaleTimeString();
  }catch(e){ document.getElementById('status').textContent = '서버 연결 대기…'; }
}
setInterval(refresh, 2000); refresh();
</script></body></html>"""


if __name__ == "__main__":
    init_db()
    print("대시보드: http://localhost:5000   (장치는 http://<이 PC IP>:5000/ingest 로 POST)")
    app.run(host="0.0.0.0", port=5000, debug=False)
