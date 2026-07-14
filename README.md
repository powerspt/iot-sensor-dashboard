# IoT 센서 실시간 · 누적 대시보드

WiFi로 센서 데이터를 수집해 **실시간 시각화**하고 **누적**하는 교육용 대시보드입니다.
2026 IoT 캠프 방과후 심화 자료 (집에서 도전용).

- **방법 1 · 로컬 PC 대시보드** — 같은 WiFi에서 내 PC로 수집. 인터넷·계정 불필요.
- **방법 2 · 원격 계정 대시보드** — 여러 학생이 서버로 전송·누적, 각자 로그인해 자기 데이터만 조회. Docker + Cloudflare Tunnel로 배포.

> 공통 원칙: **ESP32는 “보내는 쪽(클라이언트)”** 입니다. 장치가 서버로 `HTTP POST` 하므로, 집·학교에 포트포워딩이 필요 없습니다(밖으로 나가는 요청만).

---

## 📁 파일 구성

| 파일 | 설명 |
|---|---|
| `방법1_pc_server.py` | 방법1 · PC 수집 서버 + 대시보드(Flask + SQLite, 오프라인 캔버스 차트) |
| `방법1_esp32.ino` | 방법1 · ESP32 → 내 PC로 값 POST |
| `방법2_server.py` | 방법2 · 계정/로그인/API키/수집/내 데이터 조회 서버 |
| `방법2_esp32.ino` | 방법2 · ESP32 → 원격 서버(HTTPS 도메인)로 값 POST |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | 방법2 · Docker + Cloudflare Tunnel 배포 |
| `requirements.txt` | 파이썬 패키지(Flask) |

---

## 🧰 사전 준비
- **하드웨어**: ESP32(Arduino D1 R32) + USB, 조도센서(CDS) + 1kΩ 저항, 브레드보드/점퍼선
- **소프트웨어**: Arduino IDE(ESP32 보드 패키지), Python 3(방법1·로컬), Docker(방법2·배포)
- 배선: `3V3 → 조도센서 → IO34(분기) → 1kΩ → GND` (ESP32는 3.3V 기준)

---

## 🟦 방법 1 — 로컬 PC 대시보드

### 1) 수집 서버 실행 (PC)
```bash
pip install -r requirements.txt      # 또는: pip install flask
python 방법1_pc_server.py            # http://localhost:5000
```

### 2) 내 PC의 IP 확인
```bash
ipconfig        # Windows, "IPv4 주소" 예: 192.168.0.5   (Mac/Linux: ifconfig)
```

### 3) ESP32 업로드
`방법1_esp32.ino`에서 아래를 수정 후 업로드(보드: **ESP32 Dev Module**, 115200):
```cpp
const char* ssid     = "우리집WiFi";
const char* password = "비밀번호";
const char* SERVER   = "http://192.168.0.5:5000/ingest";   // ← 2)의 PC IP
```

### 4) 대시보드 열기
PC 브라우저에서 **http://localhost:5000** → 통계 카드 + 실시간 차트. `CSV 내보내기`로 저장.

> 안 되면: PC·ESP32가 같은 WiFi인지, **PC 방화벽에서 5000 포트 인바운드 허용**, PC IP 고정.

---

## 🟪 방법 2 — 원격 계정 대시보드

### A) 로컬에서 먼저 테스트
```bash
pip install flask
# Windows: set SECRET_KEY=... & set PORT=5000
export SECRET_KEY="길고-랜덤한-고정값"
export PORT=5000
python 방법2_server.py               # http://localhost:5000/register
```
가입 → 대시보드의 **내 API 키** 확인 → ESP32에 넣고 전송하면 내 데이터만 보입니다.

### B) 서버 배포 — Docker + Cloudflare Tunnel
학교 내부망(공인 IP 없음)에서도 **내 도메인 + 자동 HTTPS**로 공개하는 방법.

**1. 도메인을 Cloudflare에 연결** — [Cloudflare](https://dash.cloudflare.com) 가입 → 사이트 추가 → 네임서버(NS)를 Cloudflare 것으로 변경.

**2. Tunnel 생성** — Zero Trust → Networks → Tunnels → *Create a tunnel* → **Cloudflared** →
- **터널 토큰**(`eyJ...`) 복사
- **Public Hostname**: `dashboard.<내도메인>` → Service **HTTP** `dashboard:8000`

**3. 서버(Ubuntu)에서 실행**
```bash
curl -fsSL https://get.docker.com | sudo sh      # Docker 설치
git clone https://github.com/powerspt/iot-sensor-dashboard.git
cd iot-sensor-dashboard

cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY 값
nano .env         # SECRET_KEY + TUNNEL_TOKEN(2번 토큰) 입력

docker compose up -d --build
docker compose ps                 # dashboard, cloudflared 가 Up
docker compose logs -f cloudflared  # "Registered tunnel connection" 이면 성공
```

**4. 접속 확인** — 브라우저에서 **https://dashboard.<내도메인>/register** (자물쇠=HTTPS)

### ESP32 (방법2_esp32.ino)
```cpp
#define USE_HTTPS 1                                        // 도메인(https)=1
const char* SERVER   = "https://dashboard.내도메인/api/ingest";
const char* API_KEY  = "stu_대시보드에서_복사한_키";
```
시리얼에 `POST 200` = 성공, `POST 401` = API 키 오류.

---

### 👤 관리자 계정 (선택)
`.env`에 아래를 넣으면 서버 시작 시 **관리자 계정이 자동 생성**됩니다(회원가입 불필요). 값을 바꾸면 다음 시작 때 비밀번호가 갱신됩니다.
```
ADMIN_USER=admin
ADMIN_PASSWORD=원하는-비밀번호
```
- 이 계정으로 로그인하면 헤더의 **학급 현황** → `/admin`에서 **전체 학생의 샘플 수·최근값·최근 시각**을 한눈에 볼 수 있습니다.
- 일반 학생은 `/admin`에 접근할 수 없습니다(자기 데이터만).

## 💾 데이터 · 백업
- 누적 데이터(SQLite)는 **`data/dashboard.db`**(Docker 볼륨)에 저장됩니다.
- 백업은 `data` 폴더를 복사: `cp -r data data_backup_$(date +%F)`
- 컨테이너를 지워도 `data` 폴더가 있으면 데이터는 보존됩니다.

## 🔒 보안
- `.env`·`data/`·`*.db`는 **커밋 금지**(`.gitignore`로 제외).
- `SECRET_KEY`는 **길고 고정된 값**(바뀌면 로그인 풀림).
- HTTPS는 Cloudflare가 자동 처리. 더 강한 보호는 Cloudflare **Access** 추가.
- 모든 조회는 **로그인한 본인 데이터만**(서버가 `user_id`로 소유권 확인).

---

## 🔧 자주 쓰는 명령 (방법 2 배포)
```bash
docker compose logs -f dashboard          # 서버 로그
docker compose restart                    # 재시작
git pull && docker compose up -d --build  # 코드 갱신 후 재배포
```

## 📄 라이선스 · 용도
교육용(2026 IoT 캠프). 자유롭게 수업에 활용하세요.
