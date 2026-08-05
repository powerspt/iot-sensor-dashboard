# 배포 B · 단순 IP 매핑 (Cloudflare 없이)

서버의 IP 주소로 바로 접속하는 가장 단순한 방식입니다: `http://<서버IP>:8000`

> ⚠️ **평문 HTTP**입니다. 로그인 정보가 암호화되지 않으므로 수업·실습 등 **통제된 기간·범위**에서 사용하고, 인터넷 상시 공개 운영은 [배포 A(Cloudflare)](../cloudflare/README.md)를 권장합니다.

## 1) AWS EC2에 올리기 (예: Ubuntu 22.04+)

```bash
# ① 도커 설치 (최초 1회)
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER && newgrp docker

# ② 코드 받기
git clone https://github.com/powerspt/iot-sensor-dashboard.git
cd iot-sensor-dashboard

# ③ 환경변수 준비
cp deploy/direct-ip/.env.example deploy/direct-ip/.env
nano deploy/direct-ip/.env          # SECRET_KEY 등 채우기
#   SECRET_KEY 생성:  python3 -c "import secrets; print(secrets.token_hex(32))"

# ④ 실행
docker compose -f deploy/direct-ip/docker-compose.yml up -d --build
```

**⑤ 보안 그룹에서 포트 열기** — EC2 콘솔 → 인스턴스 → 보안 그룹 → *인바운드 규칙 편집*:

| 유형 | 프로토콜 | 포트 | 소스 |
|---|---|---|---|
| 사용자 지정 TCP | TCP | 8000 | 필요 범위 (수업이면 학교 IP 대역 권장, 테스트면 0.0.0.0/0) |

**⑥ 접속**: 브라우저에서 `http://<EC2 퍼블릭 IP>:8000`

> EC2 퍼블릭 IP는 인스턴스를 중지→시작하면 바뀝니다. 고정하려면 **탄력적 IP(Elastic IP)** 를 연결하세요.

## 2) 자체 서버(리눅스 PC·미니PC)에 올리기

②~④는 위와 동일. 포트 개방만 환경에 맞게:

```bash
# OS 방화벽 (Ubuntu)
sudo ufw allow 8000/tcp
```

- **학교/기관망**: 그 서버 IP로 같은 네트워크에서 바로 접속 가능(`http://192.168.x.x:8000`). 외부 공개는 네트워크 관리자의 정책에 따름.
- **가정집**: 공유기 관리자 페이지에서 **포트포워딩**(외부 8000 → 서버 내부IP:8000) 추가 후 `http://<집 공인IP>:8000`. 공인 IP가 자주 바뀌면 DDNS를 쓰거나 배포 A를 권장.

## 3) ESP32(장치) 설정

`firmware/esp32_dashboard_post/esp32_dashboard_post.ino` 에서:

```cpp
#define USE_HTTPS 0                                   // ← IP 직접 방식은 0 (http)
const char* SERVER  = "http://<서버IP>:8000/api/ingest"; // ← 서버 주소
const char* API_KEY = "...";                          // 대시보드 로그인 후 발급
```

## 3-1) Docker 없이 Python으로 실행 (대안)

도커를 설치할 수 없는 환경(교내 PC 등)에서는 Python만으로 실행할 수 있습니다:

```bash
# Linux/Mac
pip install -r server/requirements.txt
SECRET_KEY=랜덤값 gunicorn -w 2 -b 0.0.0.0:8000 --chdir server app:app
```

```powershell
# Windows (개발/실습용 — Flask 내장 서버)
pip install -r server/requirements.txt
$env:SECRET_KEY="랜덤값"
python server/app.py            # 0.0.0.0:8000
```

- 포트 개방(방화벽/보안그룹)은 도커 방식과 동일하게 필요합니다.
- 재부팅 자동 시작·복구가 없으므로 **상시 운영에는 Docker 방식을 권장**합니다.
- (Windows 서버에서 도커를 쓰려면 **Docker Desktop** 설치: https://www.docker.com/products/docker-desktop )

## 4) 운영 팁

- 재부팅 자동 시작: compose에 `restart: unless-stopped`가 있어 **도커만 부팅 시 실행되면** 함께 살아납니다 (`sudo systemctl enable docker`).
- 로그 확인: `docker compose -f deploy/direct-ip/docker-compose.yml logs -f`
- 데이터 백업: 레포 루트 `data/` 폴더 복사.
- 80 포트로 쓰고 싶으면 `.env`의 `PORT=80` → `http://<서버IP>` 로 접속.

## 나중에 HTTPS가 필요해지면

도메인이 생기면 [배포 A(Cloudflare Tunnel)](../cloudflare/README.md)로 전환하세요 — 서버·데이터는 그대로 두고 compose 파일만 바꾸면 됩니다(같은 `data/` 볼륨 공유).
