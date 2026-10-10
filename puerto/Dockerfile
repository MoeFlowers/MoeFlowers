# Imagen que compone el barco: Python + Pillow + la fuente de los rótulos
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-jetbrains-mono \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pillow==11.0.0

WORKDIR /repo
ENTRYPOINT ["python", "puerto/puerto.py"]
