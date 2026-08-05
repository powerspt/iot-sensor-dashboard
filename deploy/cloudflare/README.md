# 배포 A · Docker + Cloudflare Tunnel

**공인 IP·포트포워딩 없이** 내 도메인 + 자동 HTTPS로 공개하는 방식입니다.
서버(컨테이너)가 Cloudflare로 "밖으로 나가는" 연결만 만들기 때문에, 학교 내부망이나 가정집(공유기 뒤)에서도 동작합니다.

```
[학생 브라우저/ESP32] ──https──▶ Cloudflare ──터널──▶ [내 서버 dashboard:8000]
```

## 준비물

- 도메인 1개 (연 1~2만 원대, 아무 등록기관이나 가능)
- Cloudflare 무료 계정 (도메인의 네임서버를 Cloudflare로 변경)
- Docker가 설치된 서버 (AWS EC2, 자체 서버, 집 PC 모두 가능)

## 1) Cloudflare 터널 만들기 (웹에서 1회)

1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com) → **Networks → Tunnels → Create a tunnel** (Cloudflared 방식)
2. 터널 이름 입력 → 생성하면 **터널 토큰**(`eyJ...` 긴 문자열)이 표시됨 → 복사
3. **Public hostname 추가**:
   - Subdomain: `dashboard` / Domain: `내도메인.com`
   - Service: **HTTP** / URL: `dashboard:8000` ← 컨테이너 이름:포트

## 2) 서버에서 실행

```bash
git clone https://github.com/powerspt/iot-sensor-dashboard.git
cd iot-sensor-dashboard

cp deploy/cloudflare/.env.example deploy/cloudflare/.env
nano deploy/cloudflare/.env      # SECRET_KEY, TUNNEL_TOKEN(위에서 복사) 채우기

docker compose -f deploy/cloudflare/docker-compose.yml up -d --build
```

## 3) 접속 확인

- 브라우저: `https://dashboard.내도메인.com` (HTTPS 자동)
- 서버에는 **어떤 포트도 열려 있지 않습니다** — 방화벽·보안그룹 설정 불필요.

## 4) ESP32(장치) 설정

`firmware/esp32_dashboard_post/esp32_dashboard_post.ino` 에서:

```cpp
#define USE_HTTPS 1                                          // ← 도메인(https) 방식은 1
const char* SERVER  = "https://dashboard.내도메인.com/api/ingest";
const char* API_KEY = "...";                                 // 대시보드 로그인 후 발급
```

## 운영 팁

- 로그: `docker compose -f deploy/cloudflare/docker-compose.yml logs -f`
- cloudflared 상태는 Zero Trust → Tunnels 에서 HEALTHY 인지 확인.
- 데이터 백업: 레포 루트 `data/` 폴더 복사.
- 서버를 다른 기계로 옮길 때: `data/` 복사 + 같은 `.env` → 그대로 재실행 (터널 토큰 재사용 가능).
