# examples — 교재 실습 예제 (단계별)

IoT 캠프 교재의 실습 코드 모음입니다. `.ino`는 ESP32(Arduino D1 R32), `.py`는 PC(Python)에서 실행하며, 번호가 같은 파일이 짝입니다.

| 파일 | 내용 |
|---|---|
| `example_01.ino` | 조도 값 시리얼 전송 (유선 첫걸음) |
| `example_01a.py` | 시리얼 값 읽기 (pyserial) |
| `example_01b.py` | 유선 데이터 로거 — CSV 저장·그래프 |
| `example_02.ino` | 두 값(IO34·IO39)을 CSV 한 줄로 전송 |
| `example_03.ino` | WiFi 연결 & IP 확인 |
| `example_04.ino` | WiFi TCP 서버로 조도 전송 (무선 첫걸음) |
| `example_04a.py` | WiFi 소켓으로 값 받기 |
| `example_04b.py` | WiFi 수집 → CSV → 그래프 |
| `example_05_test.ino` | 로드셀(HX711) 통신 없이 테스트·보정 (시리얼) |
| `example_05.ino` | 로드셀(HX711) 무게를 대시보드 서버로 전송 |

학습 순서: `01 → 02`(유선) → `03 → 04`(무선 로컬) → 대시보드(`firmware/` + `deploy/`) → `05`(심화 센서).
