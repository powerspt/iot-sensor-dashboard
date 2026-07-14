/* ============================================================
   방법 1 · 로컬 PC 대시보드 — ESP32(Arduino D1 R32) 送信 코드
   ------------------------------------------------------------
   같은 WiFi에 연결된 "내 PC"의 수집 서버로 센서 값을 POST 합니다.
   - 보드: ESP32 (Arduino D1 R32)  · 보드레이트 115200
   - 준비: 아래 ssid / password / SERVER 를 내 환경에 맞게 수정
   - SERVER 의 IP 는 PC에서 ipconfig 로 확인한 "내 PC의 IP"
   ============================================================ */
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid     = "iotcamp";      // ← 공유기 이름(SSID)
const char* password = "********";     // ← 공유기 비밀번호
const char* SERVER   = "http://192.168.0.5:5000/ingest";  // ← 내 PC IP:5000
const char* SENSOR   = "light";        // 센서 이름(대시보드 표시용)
const int   SENSOR_PIN = 34;           // 조도센서 아날로그 입력(IO34)
const int   PERIOD_MS  = 1000;         // 전송 주기(ms)

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);            // ESP32 ADC 12비트(0~4095)
  WiFi.begin(ssid, password);
  Serial.print("WiFi 연결 중");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi 연결됨. IP: " + WiFi.localIP().toString());
}

void loop() {
  int value = analogRead(SENSOR_PIN);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER);
    http.addHeader("Content-Type", "application/json");
    // 전송 본문 예: {"sensor":"light","value":2731}
    String body = String("{\"sensor\":\"") + SENSOR + "\",\"value\":" + value + "}";
    int code = http.POST(body);
    Serial.printf("POST %d  %s=%d\n", code, SENSOR, value);
    http.end();
  } else {
    Serial.println("WiFi 끊김 — 재연결 대기");
    WiFi.begin(ssid, password);
  }
  delay(PERIOD_MS);
}
