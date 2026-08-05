# 대시보드 서버 이미지 (Flask + gunicorn)
# 빌드 컨텍스트 = server/ 디렉토리 (deploy/*/docker-compose.yml 이 지정)
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

# (선택) 교재를 /textbook 경로로 서빙 — 없어도 서버는 정상 동작
COPY textbook.html /app/textbook.html
COPY media/ /app/media/

# 데이터(SQLite)는 /app/data 에 저장 → 볼륨으로 영속화
ENV DB_PATH=/app/data/dashboard.db
EXPOSE 8000

# gunicorn 워커 2개로 실행 (app.py 안의 app 객체)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
