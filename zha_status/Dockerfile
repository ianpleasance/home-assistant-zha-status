FROM python:3.11-slim

WORKDIR /app

COPY run.sh .
COPY collector.py .
COPY web ./web

RUN apt-get update && apt-get install -y jq && \
    pip install flask websockets && \
    chmod +x run.sh

ENTRYPOINT ["./run.sh"]
