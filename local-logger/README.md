# local-logger — 방법 1 · 로컬 PC 대시보드

인터넷·계정·배포 **없이**, 같은 WiFi 안에서 내 PC로 센서 값을 모아 보는 가장 간단한 구성입니다.
(서버 배포형 대시보드는 `server/` + `deploy/` 참고)

```
[ESP32] ──WiFi(HTTP POST)──▶ [내 PC pc_server.py :5000] → 브라우저 http://localhost:5000
```

## 실행

```bash
# ① PC에서 수집 서버 실행
pip install -r requirements.txt      # flask
python pc_server.py                  # → http://localhost:5000

# ② 내 PC의 IP 확인 (같은 WiFi 기준)
ipconfig                             # Windows: "IPv4 주소" 예 192.168.0.5
```

```cpp
// ③ esp32_local_post/esp32_local_post.ino 수정 후 업로드
const char* ssid     = "우리집WiFi";
const char* password = "비밀번호";
const char* SERVER   = "http://192.168.0.5:5000/api/ingest";   // ← ②의 IP
```

브라우저에서 `http://localhost:5000` — 값이 실시간 그래프로 쌓입니다(SQLite 저장, 오프라인 차트).

## 언제 이걸 쓰나

- 수업/실습에서 배포 절차 없이 바로 "센서→무선→그래프"를 체험할 때
- 인터넷이 없는 환경(교실 공유기만 있는 경우)

여러 명이 각자 계정으로 쓰는 운영형은 `deploy/`의 배포형 대시보드를 사용하세요.
