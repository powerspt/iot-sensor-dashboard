# 배포 C · AWS(클라우드) + 도메인 + 자동 HTTPS (Caddy)

공인 IP가 있는 클라우드에 **도메인을 붙이고 자동 HTTPS**로 상시 공개하는 방식입니다: `https://내도메인`.
Cloudflare Tunnel 없이 서버가 직접 443을 서비스하며, **Caddy**가 Let's Encrypt 인증서를 **자동 발급·갱신**합니다.

> 언제 이 방식? — **도메인이 있고 AWS/클라우드처럼 공인 IP를 쓸 수 있을 때.**
> 공인 IP가 없으면(내부망·집) → [배포 A(Cloudflare)](../cloudflare/README.md) · HTTPS가 필요 없는 빠른 테스트면 → [배포 B(direct-ip)](../direct-ip/README.md)

## 1) 클라우드 인스턴스 준비 (AWS 예)

- **EC2**(또는 더 간단한 **Lightsail**) · Ubuntu 22.04 · 작은 사양(`t3.micro`/프리티어)으로 충분
- **탄력적 IP(Elastic IP)** 를 인스턴스에 연결 → 재시작해도 IP 고정 (도메인 연결에 필요)
- **보안 그룹(인바운드 규칙)**:

| 유형 | 포트 | 소스 |
|---|---|---|
| SSH | 22 | 내 IP |
| HTTP | 80 | 0.0.0.0/0 |
| HTTPS | 443 | 0.0.0.0/0 |

> **80번도 열어야** 인증서 자동 발급(ACME) 검증이 됩니다.

## 2) 도메인 연결

도메인 관리 페이지에서 **A 레코드** 추가: `dashboard.내도메인.com → <탄력적 IP>`
(전파에 몇 분~수십 분 소요 · `ping dashboard.내도메인.com` 으로 IP 확인)

## 3) 서버에서 실행

```bash
# ① 도커 설치 (최초 1회)
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER && newgrp docker

# ② 코드 받기
git clone https://github.com/powerspt/iot-sensor-dashboard.git
cd iot-sensor-dashboard

# ③ 환경변수 (도메인·비밀키)
cp deploy/aws-https/.env.example deploy/aws-https/.env
nano deploy/aws-https/.env        # DOMAIN, SECRET_KEY (, ADMIN_*)
#   SECRET_KEY 생성:  python3 -c "import secrets; print(secrets.token_hex(32))"

# ④ 실행 (Caddy가 인증서 자동 발급)
docker compose -f deploy/aws-https/docker-compose.yml up -d --build
docker compose -f deploy/aws-https/docker-compose.yml logs -f caddy   # "certificate obtained" 뜨면 성공
```

## 4) 접속

브라우저에서 **`https://dashboard.내도메인.com`** (자물쇠=HTTPS). 끝입니다.

## 5) ESP32(장치) 설정

`firmware/esp32_dashboard_post/esp32_dashboard_post.ino` 에서:

```cpp
#define USE_HTTPS 1                                            // 도메인 HTTPS
const char* SERVER  = "https://dashboard.내도메인.com/api/ingest";
const char* API_KEY = "...";                                  // 대시보드 로그인 후 발급
```

## 운영 팁

- 인증서는 Caddy가 **자동 갱신** — 별도 작업 없음. 발급이 안 되면 **A레코드·80·443 개방·DNS 전파**를 확인하세요.
- **데이터 백업**: 레포 루트 `data/` 폴더. 발급된 **인증서는 `caddy_data` 볼륨**에 보존됩니다.
- 로그: `docker compose -f deploy/aws-https/docker-compose.yml logs -f`
- 서브도메인을 여러 개 쓰거나 www도 받으려면 `Caddyfile` 의 사이트 주소에 나열하면 됩니다.
