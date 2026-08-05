// example_02.ino
// 교재: 실습코드 #01+ — 두 값(IO34·IO39)을 CSV로 (Arduino D1 R32 / ESP32)
void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
}
void loop() {
  int light  = analogRead(34); // 조도센서(IO34)
  int light2 = analogRead(39); // 두 번째 센서(IO39)
  Serial.print(light);
  Serial.print(",");          // 구분자
  Serial.println(light2);     // 줄바꿈
  delay(500);
}
