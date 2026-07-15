// v2_esp32.ino
/* ============================================================
   방법 2 · 원격 서버 + 계정 대시보드 — ESP32(Arduino D1 R32) 送信 코드
   ------------------------------------------------------------
   내 도메인(Cloudflare Tunnel, HTTPS)으로 센서 값을 POST 합니다.
   - SERVER  : https://dashboard.boram-iot.com/api/ingest
   - API_KEY : 대시보드 로그인 후 "내 API 키"에서 복사해 붙여넣기
   - USE_HTTPS : 도메인(https)=1,  로컬 IP:포트로 테스트(http)=0
   - 다중 센서: 서로 다른 "sensor" 이름으로 여러 번 보내면
                대시보드의 "센서" 드롭다운에서 나눠 볼 수 있습니다.
   - 상태 LED(RGB 모듈, 핀 R·G·B·-): 빨강=연결중/실패, 초록=정상, 파랑=전송성공
   ※ 장치는 밖으로 나가는 요청만 하므로 집/학교 포트포워딩이 필요 없습니다.
   ============================================================ */
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

const char* ssid     = "iotcamp";      // ← 공유기 이름(SSID)
const char* password = "********";     // ← 공유기 비밀번호

#define USE_HTTPS 1                     // 도메인(https)=1, 로컬 http 테스트=0
const char* SERVER   = "https://dashboard.boram-iot.com/api/ingest";  // ← 내 도메인
const char* API_KEY  = "stu_붙여넣기"; // ← 대시보드에서 발급받은 내 API 키
const int   PERIOD_MS = 2000;          // 전송 주기(ms) · 서버 기록 가능한 최소값은 500(=delay(500))

// 상태 표시 RGB LED (모듈 핀:  R · G · B · - )   "-"(공통) → GND
const int LED_R = 16;   // R → IO16
const int LED_G = 17;   // G → IO17
const int LED_B = 18;   // B → IO18
void led(bool r, bool g, bool b) {     // 공통 캐소드 모듈: HIGH = 점등
  digitalWrite(LED_R, r); digitalWrite(LED_G, g); digitalWrite(LED_B, b);
}

// 센서 값 1개를 서버로 전송 (sensor 이름으로 구분) → 응답 코드 반환
int postReading(const char* sensor, float value) {
  if (WiFi.status() != WL_CONNECTED) { led(1, 0, 0); WiFi.begin(ssid, password); return -1; }
  HTTPClient http;
#if USE_HTTPS
  WiFiClientSecure client;
  client.setInsecure();               // (학습용) 인증서 검증 생략 — 도메인이 https라 필요
  http.begin(client, SERVER);
#else
  http.begin(SERVER);                 // 로컬 http 테스트용
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);          // ← 누구 데이터인지 식별
  String body = String("{\"sensor\":\"") + sensor + "\",\"value\":" + String(value) + "}";
  int code = http.POST(body);
  Serial.printf("POST %d  %s=%s\n", code, sensor, String(value).c_str());  // 200 성공 / 401 키오류
  http.end();
  return code;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);            // ESP32 ADC 12비트(0~4095)
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  led(1, 0, 0);                        // 🔴 WiFi 연결 중
  WiFi.begin(ssid, password);
  Serial.print("WiFi 연결 중");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi 연결됨. IP: " + WiFi.localIP().toString());
  led(0, 1, 0);                        // 🟢 WiFi 연결됨
}

void loop() {
  // ── 센서 1: 조도(IO34) ──
  int light = analogRead(34);
  int c1 = postReading("light", light);

  // ── 센서 2: 다른 아날로그 센서(IO39) ── 센서가 하나면 아래 2줄을 지우세요
  int value2 = analogRead(39);
  int c2 = postReading("sensor2", value2);

  // ── 전송 결과를 LED로 표시 ──
  bool ok = (c1 == 200 && c2 == 200);
  led(!ok, 0, ok); delay(150);         // 🔵 전송 성공 / 🔴 실패 깜빡
  led(0, 1, 0);                        // 🟢 정상 대기

  delay(PERIOD_MS);
}
