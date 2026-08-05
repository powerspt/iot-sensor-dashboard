# firmware — ESP32 전송 코드 (대시보드용)

`esp32_dashboard_post/esp32_dashboard_post.ino` — ESP32(Arduino D1 R32)가 센서 값을 WiFi로 대시보드 서버에 `HTTP POST`로 전송합니다.
장치는 **밖으로 나가는 요청만** 하므로 집/학교 어디서든 포트포워딩 없이 동작합니다.

## 0) 개발 환경 설치 (최초 1회)

1. **Arduino IDE 2.x** 설치 — https://www.arduino.cc/en/software
2. **ESP32 보드 패키지** 추가:
   - 파일 → 기본 설정 → *추가 보드 매니저 URL* 에 입력:
     `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   - 도구 → 보드 → 보드 매니저 → **"esp32"(Espressif)** 검색 → 설치
3. 보드 선택: 도구 → 보드 → esp32 → **WEMOS D1 R32** (목록에 없으면 *ESP32 Dev Module*)
4. USB 연결 후 도구 → 포트에서 보드 포트 선택
   - (Windows) 포트가 안 보이면 보드 칩에 맞는 USB 드라이버 설치: **CP210x** 또는 **CH340**

## 배선 (조도센서 예시)

```
3V3 ── 조도센서(CDS) ──┬── IO34 (아날로그 입력)
                       └── 1kΩ ── GND
상태 RGB LED(선택): R→IO16, G→IO17, B→IO18, (−)→GND
```

LED 상태: 빨강=WiFi 연결 중/실패 · 초록=정상 대기 · 파랑=전송 성공

## 설정 — 코드 상단 4곳만 수정

```cpp
const char* ssid     = "우리집WiFi";     // ① WiFi 이름
const char* password = "비밀번호";       // ② WiFi 비밀번호

#define USE_HTTPS 1                      // ③ 배포 방식에 맞게 (아래 표)
const char* SERVER  = "...";             // ③ 서버 주소 (아래 표)
const char* API_KEY = "stu_...";         // ④ 대시보드 로그인 → "내 API 키" 복사
```

| 배포 방식 | `USE_HTTPS` | `SERVER` 예시 |
|---|---|---|
| A. Cloudflare(도메인) | `1` | `https://dashboard.내도메인.com/api/ingest` |
| B. 단순 IP | `0` | `http://3.36.xx.xx:8000/api/ingest` |

## 여러 센서 보내기

`postReading("이름", 값)` 을 서로 다른 이름으로 여러 번 호출하면, 대시보드의 **센서 드롭다운**에서 나눠 볼 수 있습니다.

```cpp
postReading("light", analogRead(34));
postReading("light2", analogRead(39));
```

전송 주기는 `PERIOD_MS`(기본 2000ms, 서버 허용 최소 500ms).

## 업로드

Arduino IDE에서 보드 **WEMOS D1 R32**(없으면 ESP32 Dev Module), 115200 baud로 업로드 후 시리얼 모니터에서 WiFi 연결·전송 로그(HTTP 200)를 확인하세요.
