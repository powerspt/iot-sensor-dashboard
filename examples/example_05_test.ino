// example_05_test.ino
// 교재: 로드셀(HX711) 통신 없이 테스트 & 보정 (시리얼 모니터만, WiFi 없음)
// 라이브러리: "HX711" (Bogdan Necula / bogde) 설치 필요
// 배선: HX711 VCC→3V3, GND→GND, DT→IO26, SCK→IO27   (⚠️ 전원은 3.3V)
#include "HX711.h"

const int HX_DT = 26, HX_SCK = 27;     // DT→IO26, SCK→IO27
float CAL = 1.0;                        // 처음엔 1.0(원시값 확인) → 보정 후 실제 값으로 교체

HX711 scale;

void setup() {
  Serial.begin(115200);
  scale.begin(HX_DT, HX_SCK);          // 로드셀(HX711) 핀 설정
  scale.set_scale(CAL);
  scale.tare();                        // 빈 상태에서 영점(0) 맞추기
  Serial.println("tare 완료 — 무게를 올려 '측정값'을 확인하세요.");
}

void loop() {
  float v = scale.get_units(10);       // 10회 평균
  Serial.print("측정값: ");
  Serial.println(v, 1);
  // ▼ 보정법: 무게 아는 물체(예: 100g)를 올림 → 측정값 ÷ 실제무게(g) = CAL
  //           그 값을 위의 CAL 에 넣고 다시 업로드하면 g 단위로 표시됩니다.
  delay(500);
}
