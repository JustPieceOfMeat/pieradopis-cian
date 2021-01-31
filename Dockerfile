FROM python:alpine

ENV DOCKER=TRUE
WORKDIR /

COPY requirements.txt .
RUN pip install -r /requirements.txt
VOLUME /sessions

COPY . .

CMD ["python", "main.py"]