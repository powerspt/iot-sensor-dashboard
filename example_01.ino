// example_01.ino
// 교재: 실습코드 #01 — 조도 값 시리얼 전송 (Arduino D1 R32 / ESP32)
void setup() {
  Serial.begin(115200);
  analogReadResolution(12);   // ESP32 ADC 12비트(0~4095)
}
void loop() {
  int light = analogRead(34); // 조도센서(IO34)
  Serial.println(light);      // 값 + 줄바꿈
  delay(500);
}
