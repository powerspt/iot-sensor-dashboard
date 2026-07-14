/* ============================================================
   방법 2 · 원격 서버 + 계정 대시보드 — ESP32(Arduino D1 R32) 送信 코드
   ------------------------------------------------------------
   내 도메인(Cloudflare Tunnel, HTTPS)으로 센서 값을 POST 합니다.
   - SERVER  : https://dashboard.<내도메인>/api/ingest
   - API_KEY : 대시보드 로그인 후 "내 API 키"에서 복사해 붙여넣기
   - USE_HTTPS : 도메인(https)=1,  로컬 IP:포트로 테스트(http)=0
   ※ 장치는 밖으로 나가는 요청만 하므로 집/학교 포트포워딩이 필요 없습니다.
   ============================================================ */
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

const char* ssid     = "iotcamp";      // ← 공유기 이름(SSID)
const char* password = "********";     // ← 공유기 비밀번호

#define USE_HTTPS 1                     // 도메인(https)=1, 로컬 http 테스트=0
const char* SERVER   = "https://dashboard.example.com/api/ingest";  // ← 내 도메인
const char* API_KEY  = "stu_붙여넣기"; // ← 대시보드에서 발급받은 내 API 키
const char* SENSOR   = "light";
const int   SENSOR_PIN = 34;           // 조도센서 아날로그 입력(IO34)
const int   PERIOD_MS  = 2000;         // 전송 주기(ms)

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  WiFi.begin(ssid, password);
  Serial.print("WiFi 연결 중");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi 연결됨. IP: " + WiFi.localIP().toString());
}

void loop() {
  int value = analogRead(SENSOR_PIN);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
#if USE_HTTPS
    WiFiClientSecure client;
    client.setInsecure();               // (학습용) 인증서 검증 생략 — 도메인이 https라 필요
    http.begin(client, SERVER);
#else
    http.begin(SERVER);                 // 로컬 http 테스트용
#endif
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-Key", API_KEY);   // ← 누구 데이터인지 식별
    String body = String("{\"sensor\":\"") + SENSOR + "\",\"value\":" + value + "}";
    int code = http.POST(body);
    Serial.printf("POST %d  %s=%d\n", code, SENSOR, value);  // 200 성공 / 401 키오류
    http.end();
  } else {
    WiFi.begin(ssid, password);
  }
  delay(PERIOD_MS);
}
