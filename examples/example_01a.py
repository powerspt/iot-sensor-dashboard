# example_01a.py
# 교재: Python 실습코드 #01 — 시리얼 값 읽기 (짝: 아두이노 example_01.ino) (pyserial 필요: pip install pyserial)
import serial
ser = serial.Serial('COM3', 115200) # 포트·속도는 아두이노와 동일(ESP32=115200)
while True:
    line = ser.readline().decode().strip()
    if line.isdigit():
        print(int(line))
