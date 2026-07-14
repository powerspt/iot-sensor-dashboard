# 방법 2 대시보드 서버 이미지 (Flask + gunicorn)
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn

# 한글 파일명을 피하기 위해 컨테이너 안에서는 app.py 로 복사해 실행
COPY v2_server.py /app/app.py

# 데이터(SQLite)는 /app/data 에 저장 → 볼륨으로 영속화
ENV DB_PATH=/app/data/dashboard.db
EXPOSE 8000

# gunicorn 워커 2개로 실행 (app.py 안의 app 객체)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
