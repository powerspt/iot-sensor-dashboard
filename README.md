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
| `v1_pc_server.py` | 방법1 · PC 수집 서버 + 대시보드(Flask + SQLite, 오프라인 캔버스 차트) |
| `v1_esp32.ino` | 방법1 · ESP32 → 내 PC로 값 POST |
| `v2_server.py` | 방법2 · 계정/로그인/API키/수집/내 데이터 조회 서버 |
| `v2_esp32.ino` | 방법2 · ESP32 → 원격 서버(HTTPS 도메인)로 값 POST |
| `example_01.ino` | 교재 실습코드 #01 · 조도 값 시리얼 전송 |
| `example_02.ino` | 교재 실습코드 #01+ · 두 값(IO34·IO39) CSV 전송 |
| `example_03.ino` | 교재 실습코드 #02 · WiFi 연결 & IP 확인 |
| `example_04.ino` | 교재 모델링 예제 #2 · WiFi TCP 서버(조도 전송) |
| `example_01.py` | 교재 Python 실습코드 #01 · 시리얼 값 읽기 |
| `example_02.py` | 교재 Python 모델링 예제 #1 · 유선 데이터 로거(CSV·그래프) |
| `example_03.py` | 교재 Python 모델링 예제 #2 · WiFi 소켓 값 받기 |
| `example_04.py` | 교재 Python 모델링 예제 #3 · WiFi 수집→CSV→그래프 |
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
python v1_pc_server.py            # http://localhost:5000
```

### 2) 내 PC의 IP 확인
```bash
ipconfig        # Windows, "IPv4 주소" 예: 192.168.0.5   (Mac/Linux: ifconfig)
```

### 3) ESP32 업로드
`v1_esp32.ino`에서 아래를 수정 후 업로드(보드: **WEMOS D1 R32** — 없으면 ESP32 Dev Module, 115200):
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
python v2_server.py               # http://localhost:5000/register
```
가입 → 대시보드의 **내 API 키** 확인 → ESP32에 넣고 전송하면 내 데이터만 보입니다.

### B) 서버 배포 — Docker + Cloudflare Tunnel
학교 내부망(공인 IP 없음)에서도 **내 도메인 + 자동 HTTPS**로 공개하는 방법.

**1. 도메인을 Cloudflare에 연결** — [Cloudflare](https://dash.cloudflare.com) 가입 → 사이트 추가 → 네임서버(NS)를 Cloudflare 것으로 변경.

**2. Tunnel 생성** — Zero Trust → Networks → Tunnels → *Create a tunnel* → **Cloudflared** →
- **터널 토큰**(`eyJ...`) 복사
- **Public Hostname**: `dashboard.boram-iot.com` → Service **HTTP** `dashboard:8000`

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

**4. 접속 확인** — 브라우저에서 **https://dashboard.boram-iot.com/register** (자물쇠=HTTPS)

### ESP32 (v2_esp32.ino)
```cpp
#define USE_HTTPS 1                                        // 도메인(https)=1
const char* SERVER   = "https://dashboard.boram-iot.com/api/ingest";
const char* API_KEY  = "stu_대시보드에서_복사한_키";
```
시리얼에 `POST 200` = 성공, `POST 401` = API 키 오류.

> ⏱ **전송 주기 하한** — 서버 스펙상 기록 가능한 가장 빠른 주기는 **`delay(500)`(0.5초)** 입니다. 그보다 짧게 보내도 더 촘촘히 저장되지 않으니, 최소값으로 `delay(500)`을 쓰세요.

---

### 👤 회원가입 · 승인 · 관리자

**회원가입**은 **이름 · 소속 · 이메일 · 아이디 · 비밀번호(+비밀번호 확인)** 를 받습니다. 비밀번호는 두 번 입력해 오타를 검증합니다. 가입 즉시 로그인되지 않고 **관리자 승인 대기(pending)** 상태가 됩니다.

**관리자 계정**은 `.env`에 아래를 넣으면 서버 시작 시 **자동 생성**됩니다(값 변경 시 다음 시작에 비번 갱신).
```
ADMIN_USER=admin
ADMIN_PASSWORD=원하는-비밀번호
```
관리자로 로그인하면 헤더의 **회원 관리** → `/admin`에서:
- **승인 대기** — 신청자(이름·소속·이메일) **승인 / 거절**. 승인 시 API 키가 자동 발급됩니다.
- **회원 직접 생성** — 관리자가 계정을 즉시 만들기(바로 승인).
- **회원 목록 · 수집 현황** — 전체 회원의 샘플 수·최근값·최근 시각, 회원별 **비밀번호 초기화**(임시 비번 발급) · **계정 삭제**(데이터 포함).

> 일반 회원은 `/admin`에 접근할 수 없고(자기 데이터만), 승인 전에는 로그인이 막힙니다. 관리자 계정은 삭제되지 않습니다.
> 기존 DB는 자동 마이그레이션됩니다(이름/소속/이메일/status/epoch_ms 컬럼 추가, 기존 사용자는 `approved` 유지).

### 📊 대시보드 조회 옵션 (시간 · 다중 센서)
로그인한 대시보드에서:
- **센서 선택** — 여러 종류를 보내면(아래) 드롭다운에서 골라 봅니다.
- **범위** — 최근 / 최근 1시간 / 24시간 / 오늘 / **날짜 지정** / **월 지정** / 전체.
- **집계 단위** — 원본 · 1초 · 10초 · 30초 · 1분 · 5분 · 1시간 · 1일 (구간 평균).
- **CSV 내보내기** — 현재 선택(센서·기간)이 그대로 반영됩니다.

**인사이트 · 편의 기능**
- **통계 카드** — 현재값(직전 대비 ▲▼ 증감) · 평균 · **표준편차** · 최소 · 최대 · 샘플 수.
- **수신 상태** — 🟢/🔴 배지 + "마지막 수신 N초 전"(장치 온·오프라인 확인), **수집 속도(개/분)**.
- **보기 모드** — **라인** / **겹쳐보기**(여러 센서를 한 차트에, `정규화`로 척도 통일) / **나눠보기**(센서별 작은 다중 차트) / **분포**(히스토그램).
- **이상치 자동 표시** — 라인 보기에서 평균±2.5σ를 벗어난 점을 빨간 링으로 표시하고 개수를 알려줍니다.
- **임계값** — 값을 입력하면 차트에 **임계선** + **초과 횟수·비율** 표시.
- **이동평균** — 체크 시 노이즈를 완만하게 본 추세선을 겹쳐 그립니다.
- **차트** — 그리드·Y축 눈금·최소/최대/현재 점, **마우스 호버 시 값·시각 툴팁**.
- **다크 모드** — 헤더 🌓 버튼(설정 저장, 관리자 페이지와 공유). **자동 새로고침 주기** 선택(끄기·1·2·5·10초). **API 키 복사** 버튼.
- **회원 관리(관리자)** — 같은 톤으로 개편: 요약(총 회원·승인 대기·데이터 수집 회원) pill, 다크 모드, 카드형 표.

> 서버는 각 값에 밀리초 정밀 시간(`epoch_ms`)을 함께 저장하므로 시간별·일별·월별 구분과 다양한 집계가 가능합니다.

### 🔀 센서 2개 이상 보내기
ESP32에서 **`sensor` 이름을 다르게** 여러 번 POST 하면 됩니다(제공된 `v2_esp32.ino`는 `light`·`sensor2` 두 개를 보내는 예시). 대시보드 **센서 드롭다운**에서 각각 조회됩니다.

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
