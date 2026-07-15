// example_03.ino
// 교재: 실습코드 #02 — WiFi 연결 & IP 확인 (Arduino D1 R32 / ESP32)
#include <WiFi.h>
const char* ssid     = "iotcamp";      // ← 공유기 이름(SSID)
const char* password = "********";     // ← 공유기 비밀번호
void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi 연결됨");
  Serial.print("IP 주소: ");
  Serial.println(WiFi.localIP());   // ← 이 IP를 파이썬에 입력!
}
void loop() {}
