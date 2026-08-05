# example_01b.py
# 교재: Python 모델링 예제 #1 — 유선 데이터 로거 (짝: 아두이노 example_01.ino)
# 필요: pip install pyserial pandas matplotlib
import serial, datetime
import pandas as pd
import matplotlib.pyplot as plt

PORT = 'COM3'      # ← 내 포트로 수정
DATA_LIMIT = 100    # ← 모을 데이터 개수
values, times = [], []

with serial.Serial(PORT, 115200, timeout=1) as ser:  # with: 끝나면 포트를 자동 반납
    while len(values) < DATA_LIMIT:
        try:
            line = ser.readline().decode().strip()
            if line.isdigit():
                v = int(line)
                now = datetime.datetime.now().strftime("%H:%M:%S")
                values.append(v); times.append(now)
                print(len(values), now, v)
        except:
            pass
# with 블록을 벗어나면 포트가 닫혀 시리얼 모니터를 다시 쓸 수 있음

pd.DataFrame({'시간': times, '데이터': values}).to_csv('light_log.csv', index=False, encoding='utf-8-sig')
plt.plot(values); plt.ylabel('light'); plt.show()
