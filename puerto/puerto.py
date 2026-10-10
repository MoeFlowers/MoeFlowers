"""Puerto Docker: cada visitante carga un contenedor con su usuario en el barco del perfil.

  python puerto/puerto.py cargar      lee $USUARIO, lo registra y regenera todo
  python puerto/puerto.py dibujar     solo regenera la imagen y el README

Escribe puerto/respuesta.md con el mensaje para el issue.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(HERE, "recursos")
DATA = os.path.join(HERE, "contenedores.json")
OUT = os.path.join(HERE, "puerto.png")
README = os.path.join(ROOT, "README.md")
RESPUESTA = os.path.join(HERE, "respuesta.md")
REPO = "MoeFlowers/MoeFlowers"

USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
TEXTO_OSCURO = {"blanco", "cian"}
FUENTES = [
    os.environ.get("PUERTO_FUENTE", ""),
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
]


def fuente(tam):
    for f in FUENTES:
        if f and os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default(tam)


def leer():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def color_de(usuario, colores):
    h = int(hashlib.sha1(usuario.lower().encode()).hexdigest(), 16)
    return colores[h % len(colores)]


def coeficientes(destino, origen):
    """Coeficientes de Image.PERSPECTIVE que llevan el cuadrilátero destino al rectángulo origen."""
    filas, b = [], []
    for (x, y), (u, v) in zip(destino, origen):
        filas.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        filas.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    n = 8
    a = [fila + [bi] for fila, bi in zip(filas, b)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c:
                k = a[r][c] / a[c][c]
                a[r] = [x - k * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def etiqueta(usuario, color):
    """Rótulo plano del costado: lo que luego se deforma sobre la cara del contenedor."""
    w, h = 960, 360
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tinta = (22, 28, 38, 235) if color in TEXTO_OSCURO else (255, 255, 255, 240)
    texto = "@" + usuario
    tam = 150
    while tam > 40:
        f = fuente(tam)
        x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=f)
        if x1 - x0 <= w - 60:
            break
        tam -= 6
    d.text(((w - (x1 - x0)) / 2 - x0, (h - (y1 - y0)) / 2 - y0), texto, font=f, fill=tinta)
    return img


def dibujar(datos):
    meta = json.load(open(os.path.join(RES, "meta.json"), encoding="utf-8"))
    base = Image.open(os.path.join(RES, "barco.png")).convert("RGBA")
    sprites = {}
    for c in meta["colors"]:
        im = Image.open(os.path.join(RES, f"contenedor-{c}.png")).convert("RGBA")
        caja = im.getbbox()
        sprites[c] = (im.crop(caja), caja[0], caja[1])

    cap = meta["capacity"]
    a_bordo = datos["contenedores"][-cap:]
    ocupados = list(zip(meta["slots"], a_bordo))
    # Primero lo más lejano a la cámara
    ocupados.sort(key=lambda s: -s[0]["depth"])
    ax, ay = meta["anchor"]
    for slot, cont in ocupados:
        color = color_de(cont["usuario"], meta["colors"])
        spr, ox, oy = sprites[color]
        dx, dy = slot["x"] - ax, slot["y"] - ay
        base.alpha_composite(spr, (round(ox + dx), round(oy + dy)))
        rot = etiqueta(cont["usuario"], color)
        quad = [(x + dx, y + dy) for x, y in meta["face"]]
        rw, rh = rot.size
        coef = coeficientes(quad, [(0, 0), (rw, 0), (rw, rh), (0, rh)])
        capa = rot.transform(base.size, Image.Transform.PERSPECTIVE, coef, Image.Resampling.BICUBIC)
        base.alpha_composite(capa)
    base.save(OUT, optimize=True)


def actualizar_readme(datos):
    total = len(datos["contenedores"])
    ultimos = list(reversed(datos["contenedores"][-6:]))
    # HTML y no Markdown: el bloque va dentro de un <p> centrado, donde GitHub no procesa Markdown
    enlaces = " · ".join(f'<a href="https://github.com/{c["usuario"]}">@{c["usuario"]}</a>' for c in ultimos)
    bloque = (
        "<!-- PUERTO:INICIO -->\n"
        f"<b>{total}</b> {'contenedor cargado' if total == 1 else 'contenedores cargados'}. Últimos: {enlaces}\n"
        "<!-- PUERTO:FIN -->"
    )
    with open(README, encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"<!-- PUERTO:INICIO -->.*?<!-- PUERTO:FIN -->", bloque, txt, flags=re.S)
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


def responder(texto):
    with open(RESPUESTA, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def cargar():
    usuario = os.environ.get("USUARIO", "").strip()
    if not USUARIO_VALIDO.match(usuario):
        responder("No pude leer tu usuario de GitHub, así que no cargué ningún contenedor.")
        return 0
    datos = leer()
    if any(c["usuario"].lower() == usuario.lower() for c in datos["contenedores"]):
        responder(f"@{usuario}, tu contenedor ya va a bordo. Búscalo en el barco de https://github.com/MoeFlowers")
        return 0
    datos["contenedores"].append({"usuario": usuario, "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    with open(DATA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.write("\n")
    dibujar(datos)
    actualizar_readme(datos)
    n = len(datos["contenedores"])
    responder(
        f"`docker run` completado: @{usuario} cargó el contenedor número {n}. "
        "Ya está en el barco de https://github.com/MoeFlowers (si no lo ves, recarga: GitHub guarda la imagen en caché unos minutos). Gracias por pasar."
    )
    return 0


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "dibujar"
    if orden == "cargar":
        sys.exit(cargar())
    datos = leer()
    dibujar(datos)
    actualizar_readme(datos)
