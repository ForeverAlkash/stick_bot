FROM python:3.11-slim

# ffmpeg нужен handlers/sticker_control.py для конвертации стикеров
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
docker save sticker-bot:latest | gzip > sticker-bot.tar.gz
scp sticker-bot.tar.gz user@server:~
ssh user@server 'gunzip -c sticker-bot.tar.gz | docker load'
ssh user@server 'docker run -d --name sticker-bot --restart unless-stopped sticker-bot:latest'