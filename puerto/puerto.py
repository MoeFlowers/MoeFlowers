"""Puerto Docker: cada visitante carga un contenedor con su usuario en el barco del perfil.

  python puerto/puerto.py cargar      lee $USUARIO, lo registra y regenera todo
  python puerto/puerto.py dibujar     solo regenera las imágenes y el README

Genera en puerto/salida/ la animación del barco (WebP: la grúa baja el último contenedor)
y la tarjeta "Últimos a bordo" (SVG). Los nombres cambian en cada carga para que la caché
de imágenes de GitHub muestre siempre la versión nueva. Escribe puerto/respuesta.md con el
mensaje para el issue.
"""

import base64
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from html import escape

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(HERE, "recursos")
SALIDA = os.path.join(HERE, "salida")
DATA = os.path.join(HERE, "contenedores.json")
README = os.path.join(ROOT, "README.md")
RESPUESTA = os.path.join(HERE, "respuesta.md")
ISSUE = (
    "https://github.com/MoeFlowers/MoeFlowers/issues/new?title=docker+run+puerto%2Fmi-contenedor"
    "&body=Press+%22Create%22+and+a+GitHub+Action+will+load+a+container+with+your+username+onto+the+ship."
    "%0A%0APulsa+%22Create%22+y+una+GitHub+Action+cargar%C3%A1+un+contenedor+con+tu+usuario+en+el+barco."
)

# Medidas de escena.py (m)
CL, CW, CH = 6.06, 2.44, 2.59
GAP_X, GAP_Y = 0.32, 0.12

ANCHO_SALIDA = 1400
USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
TEXTO_OSCURO = {"blanco", "cian"}
FUENTES = [
    os.environ.get("PUERTO_FUENTE", ""),
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
]


@lru_cache(maxsize=None)
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


def proyeccion(meta):
    """La cámara es ortográfica: un desplazamiento en metros es un desplazamiento fijo en píxeles."""
    s = {(h["bay"], h["row"], h["tier"]): h for h in meta["slots"]}
    o = s[(0, 0, 0)]

    def eje(otro, metros):
        return ((otro["x"] - o["x"]) / metros, (otro["y"] - o["y"]) / metros)

    ex = eje(s[(1, 0, 0)], CL + GAP_X)
    ey = eje(s[(0, 1, 0)], CW + GAP_Y)
    ez = eje(s[(0, 0, 1)], CH)
    prof_z = (s[(0, 0, 1)]["depth"] - o["depth"]) / CH
    return ex, ey, ez, prof_z


def a_pixel(ejes, x, y, z):
    ex, ey, ez = ejes
    return (x * ex[0] + y * ey[0] + z * ez[0], x * ex[1] + y * ey[1] + z * ez[1])


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


def pegar(lienzo, img, x, y):
    """alpha_composite que admite coordenadas negativas (recorta lo que queda fuera)."""
    x, y = round(x), round(y)
    cx, cy = max(0, -x), max(0, -y)
    if cx >= img.width or cy >= img.height:
        return
    if cx or cy:
        img = img.crop((cx, cy, img.width, img.height))
    lienzo.alpha_composite(img, (x + cx, y + cy))


def baldosas(meta, a_bordo):
    """Cada contenedor ya pintado con su nombre, recortado, con su posición y profundidad."""
    sprites = {}
    for c in meta["colors"]:
        im = Image.open(os.path.join(RES, f"contenedor-{c}.png")).convert("RGBA")
        caja = im.getbbox()
        sprites[c] = (im.crop(caja), caja[0], caja[1])
    ax, ay = meta["anchor"]
    piezas = []
    for slot, cont in zip(meta["slots"], a_bordo):
        color = color_de(cont["usuario"], meta["colors"])
        spr, ox, oy = sprites[color]
        tile = spr.copy()
        rot = etiqueta(cont["usuario"], color)
        quad = [(x - ox, y - oy) for x, y in meta["face"]]
        rw, rh = rot.size
        coef = coeficientes(quad, [(0, 0), (rw, 0), (rw, rh), (0, rh)])
        tile.alpha_composite(rot.transform(tile.size, Image.Transform.PERSPECTIVE, coef, Image.Resampling.BICUBIC))
        piezas.append({"tile": tile, "x": ox + slot["x"] - ax, "y": oy + slot["y"] - ay, "depth": slot["depth"],
                       "slot": slot, "usuario": cont["usuario"], "color": color})
    return piezas


def capas(base, piezas, nueva, alto_max, prof_z):
    """Separa lo que nunca cambia de orden respecto a la pieza que baja: fondo ya compuesto,
    frente ya compuesto y solo las piezas intermedias, que se ordenan en cada fotograma."""
    lejos, cerca = nueva["depth"], nueva["depth"] + alto_max * prof_z
    if cerca > lejos:
        lejos, cerca = cerca, lejos
    fondo = base.copy()
    frente = Image.new("RGBA", base.size, (0, 0, 0, 0))
    medio = []
    for p in sorted(piezas, key=lambda p: -p["depth"]):
        if p["depth"] >= lejos:
            pegar(fondo, p["tile"], p["x"], p["y"])
        elif p["depth"] <= cerca:
            pegar(frente, p["tile"], p["x"], p["y"])
        else:
            medio.append(p)
    return fondo, medio, frente


def fotograma(fondo, medio, frente, nueva, alto, ejes, prof_z, cable):
    """Compone un fotograma. La pieza nueva va 'alto' metros por encima de su hueco."""
    img = fondo.copy()
    dx, dy = a_pixel(ejes, 0, 0, alto)
    orden = [(p["depth"], p, 0, 0) for p in medio] + [(nueva["depth"] + alto * prof_z, nueva, dx, dy)]
    for _, p, ox, oy in sorted(orden, key=lambda o: -o[0]):
        pegar(img, p["tile"], p["x"] + ox, p["y"] + oy)
    img.alpha_composite(frente)
    if cable is not None:
        dibujar_grua(img, nueva, alto, ejes, cable)
    return img


def dibujar_grua(img, nueva, alto, ejes, recogida):
    """Spreader y cables de la grúa sobre el contenedor que baja; 'recogida' (0..1) los sube al final."""
    ax_base = nueva["slot"]["x"], nueva["slot"]["y"]
    d = ImageDraw.Draw(img)
    sube = recogida * 16.0
    top = alto + CH + 0.05 + sube

    def p(x, y, z):
        px, py = a_pixel(ejes, x, y, z)
        return (ax_base[0] + px, ax_base[1] + py)

    gancho = p(0, 0, top + 3.2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            d.line([p(sx * (CL / 2 - 0.4), sy * (CW / 2 - 0.3), top), gancho], fill=(40, 46, 56, 255), width=2)
    d.line([p(-(CL / 2 - 0.3), 0, top), p(CL / 2 - 0.3, 0, top)], fill=(250, 190, 40, 255), width=7)
    arriba = p(0, 0, top + 60)
    d.line([gancho, arriba], fill=(40, 46, 56, 255), width=3)
    d.ellipse([gancho[0] - 5, gancho[1] - 5, gancho[0] + 5, gancho[1] + 5], fill=(250, 190, 40, 255))


def animar(meta, a_bordo, ruta):
    base = Image.open(os.path.join(RES, "barco.png")).convert("RGBA")
    piezas = baldosas(meta, a_bordo)
    ex, ey, ez, prof_z = proyeccion(meta)
    ejes = (ex, ey, ez)
    nueva, resto = piezas[-1], piezas[:-1]
    ALTO = 18.0
    fondo, medio, frente = capas(base, resto, nueva, ALTO, prof_z)
    escala = ANCHO_SALIDA / base.width
    tam = (ANCHO_SALIDA, round(base.height * escala))

    frames, durs = [], []

    def agregar(alto, cable, ms):
        f = fotograma(fondo, medio, frente, nueva, alto, ejes, prof_z, cable)
        frames.append(f.resize(tam, Image.Resampling.LANCZOS))
        durs.append(ms)

    caida = 18
    for i in range(caida):
        t = i / (caida - 1)
        agregar(ALTO * (1 - t) ** 3, 0.0, 350 if i == caida - 1 else 45)
    for i in range(1, 7):
        agregar(0.0, i / 6, 45)
    agregar(0.0, None, 4200)
    # Un solo fotograma clave: entre fotogramas solo cambia la zona de la grúa
    n = len(frames)
    frames[0].save(ruta, save_all=True, append_images=frames[1:], duration=durs, loop=0, quality=80, method=4, kmin=n, kmax=n + 1)
    return piezas


def avatar(usuario):
    try:
        req = urllib.request.Request(f"https://github.com/{usuario}.png?size=96", headers={"User-Agent": "puerto-docker"})
        with urllib.request.urlopen(req, timeout=8) as r:
            tipo = r.headers.get_content_type()
            if tipo.startswith("image/"):
                return f"data:{tipo};base64,{base64.b64encode(r.read()).decode()}"
    except Exception:
        pass
    return None


TEMAS = {
    # Colores de GitHub: texto principal, texto secundario y líneas
    "claro": {"fg": "#1F2328", "muted": "#59636E", "line": "#D1D9E0", "vacio": "#F6F8FA"},
    "oscuro": {"fg": "#E6EDF3", "muted": "#9198A1", "line": "#3D444D", "vacio": "#151B23"},
}
MOSTRAR = 7


def tarjetas(datos, capacidad, rutas):
    """Lista 'A bordo' en dos versiones (tema claro y oscuro): avatar y usuario, sin fondo propio."""
    total = len(datos["contenedores"])
    ultimos = list(reversed(datos["contenedores"][-MOSTRAR:]))
    avatares = {c["usuario"]: avatar(c["usuario"]) for c in ultimos}
    W, H, paso, r = 840, 112, 120, 20
    for tema, ruta in rutas.items():
        t = TEMAS[tema]
        partes = []
        for i, c in enumerate(ultimos):
            u = c["usuario"]
            cx = paso * i + paso / 2
            nombre = u if len(u) <= 18 else u[:17] + "…"
            img = avatares[u]
            cara = (
                f'<image href="{img}" x="{cx - r}" y="44" width="{2 * r}" height="{2 * r}" clip-path="url(#c{i})"/>' if img else
                f'<circle cx="{cx}" cy="{44 + r}" r="{r}" fill="{t["vacio"]}"/>'
                f'<text x="{cx}" y="{44 + r + 5}" class="m" text-anchor="middle">{escape(u[0].upper())}</text>'
            )
            partes.append(
                f'<clipPath id="c{i}"><circle cx="{cx}" cy="{44 + r}" r="{r}"/></clipPath>{cara}'
                f'<circle cx="{cx}" cy="{44 + r}" r="{r}" fill="none" stroke="{t["line"]}"/>'
                f'<text x="{cx}" y="104" class="u" text-anchor="middle">{escape(nombre)}</text>'
            )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="A bordo">
<style>
.h{{font:600 14px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{t["fg"]}}}
.m{{font:400 12px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{t["muted"]}}}
.u{{font:400 12px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{t["fg"]}}}
</style>
<text x="0" y="16" class="h">A bordo</text>
<text x="{W}" y="16" class="m" text-anchor="end">{total} / {capacidad}</text>
<line x1="0" y1="28.5" x2="{W}" y2="28.5" stroke="{t["line"]}"/>
{"".join(partes)}
</svg>'''
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)


def generar(datos):
    meta = json.load(open(os.path.join(RES, "meta.json"), encoding="utf-8"))
    os.makedirs(SALIDA, exist_ok=True)
    for viejo in os.listdir(SALIDA):
        os.remove(os.path.join(SALIDA, viejo))
    sello = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    a_bordo = datos["contenedores"][-meta["capacity"]:]
    barco = f"barco-{sello}.webp"
    claro, oscuro = f"a-bordo-claro-{sello}.svg", f"a-bordo-oscuro-{sello}.svg"
    animar(meta, a_bordo, os.path.join(SALIDA, barco))
    tarjetas(datos, meta["capacity"], {"claro": os.path.join(SALIDA, claro), "oscuro": os.path.join(SALIDA, oscuro)})
    nombres = ", ".join("@" + c["usuario"] for c in reversed(datos["contenedores"][-MOSTRAR:]))
    bloque = f'''<!-- PUERTO:INICIO -->
<p align="center">
  <img src="puerto/salida/{barco}" alt="Container ship rendered in Blender; a crane lowers the latest container. Every container carries the GitHub username of a visitor" width="100%">
</p>

<p align="center">
  <a href="{ISSUE}"><img src="puerto/boton-carga.svg" alt="Carga tu contenedor" height="36"></a>
</p>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="puerto/salida/{oscuro}">
  <img src="puerto/salida/{claro}" alt="A bordo: {escape(nombres)}" width="100%">
</picture>
<!-- PUERTO:FIN -->'''
    with open(README, encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"<!-- PUERTO:INICIO -->.*?<!-- PUERTO:FIN -->", lambda _: bloque, txt, flags=re.S)
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
    generar(datos)
    n = len(datos["contenedores"])
    responder(
        f"`docker run` completado: @{usuario} cargó el contenedor número {n}. "
        "La grúa lo está bajando ahora mismo en https://github.com/MoeFlowers. Gracias por pasar."
    )
    return 0


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "dibujar") == "cargar":
        sys.exit(cargar())
    generar(leer())
