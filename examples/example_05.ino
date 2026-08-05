// example_05.ino
// 교재: 로드셀(HX711) → 서버로 무게 전송 (Arduino D1 R32 / ESP32)
// 필요 라이브러리: "HX711" (Bogdan Necula / bogde) — 라이브러리 관리에서 설치
// 배선: 로드셀 → HX711(E+/E-/A+/A-) / HX711 VCC→3V3, GND→GND, DT→IO26, SCK→IO27
//   ⚠️ HX711 전원은 3.3V (5V로 주면 DT 출력이 5V라 ESP32 손상 위험)
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "HX711.h"

const char* ssid     = "우리WiFi";       // ← 공유기 이름
const char* password = "********";       // ← 공유기 비밀번호
const char* SERVER   = "https://dashboard.boram-iot.com/api/ingest";
const char* API_KEY  = "stu_붙여넣기";   // ← 대시보드에서 복사한 내 API 키

const int   HX_DT = 26, HX_SCK = 27;     // DT→IO26, SCK→IO27
const float CAL   = 2280.0;              // ← 보정값(아래 절차로 구해 교체)
HX711 scale;

// 값 1개를 서버로 전송 (sensor 이름으로 구분) → 응답 코드 반환
int postReading(const char* sensor, float value) {
  if (WiFi.status() != WL_CONNECTED) { WiFi.begin(ssid, password); return -1; }
  WiFiClientSecure client; client.setInsecure();     // (학습용) 인증서 검증 생략
  HTTPClient http;
  http.begin(client, SERVER);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int code = http.POST(String("{\"sensor\":\"") + sensor + "\",\"value\":" + value + "}");
  Serial.printf("POST %d  %s=%.1f\n", code, sensor, value);  // 200 성공 / 401 키오류
  http.end();
  return code;
}

void setup() {
  Serial.begin(115200);
  scale.begin(HX_DT, HX_SCK);            // 로드셀(HX711) 핀 설정
  scale.set_scale(CAL);                  // 보정값 적용
  scale.tare();                          // 영점(빈 상태) 맞추기
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("WiFi 연결됨");
}

void loop() {
  float grams = scale.get_units(5);      // 5회 평균 무게(g)
  postReading("weight", grams);          // 대시보드에 'weight' 센서로 표시
  delay(2000);                           // 2초마다 (서버 기록 최소 주기 500)
}
