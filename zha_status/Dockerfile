FROM python:3.11-slim

WORKDIR /app

COPY run.sh .
COPY collector.py .
COPY web ./web
RUN pip install flask websockets

RUN chmod +x run.sh
ENTRYPOINT ["./run.sh"]
