# Imagen del perfil: Python + Pillow + fuentes (rótulos del barco y títulos de los libros)
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-jetbrains-mono fonts-ebgaramond \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pillow==11.0.0

WORKDIR /repo
ENTRYPOINT ["python", "puerto/puerto.py"]
