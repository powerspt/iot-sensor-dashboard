# example_04b.py
# 교재: Python 모델링 예제 #3 — WiFi 수집 → CSV → 그래프 (짝: 아두이노 example_04.ino)
# 필요: pip install pandas matplotlib  (socket은 표준 라이브러리)
import socket, datetime
import pandas as pd
import matplotlib.pyplot as plt

HOST = '192.168.0.10'   # ← D1 R32의 IP
PORT = 5000; DATA_LIMIT = 100
buf = ''; values, times = [], []

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # with: 끝나면 소켓 자동 반납
    s.connect((HOST, PORT))
    while len(values) < DATA_LIMIT:
        buf += s.recv(1024).decode(errors='ignore')
        while '\n' in buf:                 # 줄 단위로 잘라 처리
            line, buf = buf.split('\n', 1)
            line = line.strip()
            if line.isdigit():
                v = int(line)
                now = datetime.datetime.now().strftime("%H:%M:%S")
                values.append(v); times.append(now)
                print(len(values), v)

pd.DataFrame({'시간': times, '데이터': values}).to_csv('wifi_log.csv', index=False, encoding='utf-8-sig')
plt.plot(values); plt.ylabel('light'); plt.show()
