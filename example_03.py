# example_03.py
# 교재: Python 모델링 예제 #2 — WiFi 소켓으로 값 받기 (짝: 아두이노 example_04.ino)
import socket
HOST = '192.168.0.10'   # ← 시리얼에 뜬 D1 R32의 IP
PORT = 5000
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # with: 끝나면 소켓 자동 반납
    s.connect((HOST, PORT))       # 서버(D1 R32)에 접속
    while True:
        chunk = s.recv(1024)          # 원본 바이트
        if not chunk:                 # 빈 바이트 = 연결 종료
            break
        data = chunk.decode().strip()
        if data:                      # 개행만 온 조각(빈 줄)은 건너뛰기
            print(data)
