// example_04.ino
// 교재: 모델링 예제 #2 — WiFi TCP 서버(조도 전송) (Arduino D1 R32 / ESP32)
#include <WiFi.h>
const char* ssid     = "iotcamp";
const char* password = "********";
WiFiServer server(5000);       // 포트 5000으로 서버 열기
WiFiClient client;
void setup() {
  Serial.begin(115200);
  analogReadResolution(12);      // ESP32 ADC 12비트(0~4095)
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
  Serial.print("IP: "); Serial.println(WiFi.localIP());
  server.begin();
}
void loop() {
  if (!client || !client.connected()) {
    client = server.available();   // PC 접속 대기
    return;
  }
  int light = analogRead(34);   // 조도센서(IO34)
  client.println(light);          // 값 + 줄바꿈을 WiFi로 전송
  delay(500);
}
