FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/app

COPY wait-for-it.sh  /usr/src/app/wait-for-it.sh
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /usr/src/app/entrypoint.sh
RUN chmod +x /usr/src/app/wait-for-it.sh

EXPOSE 8000
