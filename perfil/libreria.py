"""Librería 3D del perfil: cada repo público es un libro renderizado en Blender.

Los libros vienen en color neutro (perfil/recursos/); aquí se tiñen con el color del lenguaje
(solo tapa y lomo, gracias a la máscara), se les imprime el título en dorado y se recorta el tramo
de estante que va debajo. Cada libro sale como un SVG propio para que en el README tenga su enlace
y su texto al pasar el ratón.
"""

import base64
import io
import json
import math
import os
from functools import lru_cache
from html import escape

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "recursos")
FUENTES = [
    os.environ.get("PERFIL_FUENTE", ""),
    # La Bold de Debian no trae tildes ni eñe: Regular con un trazo fino para darle peso
    "/usr/share/fonts/opentype/ebgaramond/EBGaramond12-Regular.otf",
    "C:/Windows/Fonts/georgia.ttf",
]
ORO = (226, 196, 122, 255)
TINTA_OSCURA = (40, 30, 20, 255)
GROSORES = [58, 66, 74, 82]
ALTOS = [205, 235, 265]


@lru_cache(maxsize=None)
def fuente(tam):
    for f in FUENTES:
        if f and os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default(tam)


@lru_cache(maxsize=None)
def imagen(nombre):
    return Image.open(os.path.join(RES, nombre)).convert("RGBA")


def rgb(hexa):
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def tenir(libro, mascara, color, oscurecer=0.0):
    base = libro.convert("RGB")
    tinte = ImageChops.multiply(base, Image.new("RGB", libro.size, rgb(color)))
    factor = 1.65 * (1 - oscurecer)
    tinte = tinte.point(lambda v: min(255, int(v * factor)))
    out = Image.composite(tinte, base, mascara.convert("L"))
    out.putalpha(libro.getchannel("A"))
    return out


def claro(color):
    r, g, b = rgb(color)
    return 0.299 * r + 0.587 * g + 0.114 * b > 170


def titulo(img, rect, texto, tinta):
    """Título en mayúsculas espaciadas, de abajo arriba (como los lomos en español), con filetes dorados."""
    (x0, y0), (x1, y1) = rect
    ancho, alto = x1 - x0, y1 - y0
    d = ImageDraw.Draw(img)
    for yy in (y0 + 16, y0 + 22, y1 - 22, y1 - 16):
        d.line([(x0 + 4, yy), (x1 - 4, yy)], fill=tinta, width=2)
    texto = texto.upper()
    disponible = alto - 76
    tam = max(14, int(ancho * 0.42))
    while True:
        f = fuente(tam)
        esp = tam * 0.14
        largo = sum(f.getlength(c) for c in texto) + esp * (len(texto) - 1)
        if largo <= disponible or tam <= 14:
            break
        tam -= 1
    while largo > disponible and len(texto) > 3:
        texto = texto[:-2] + "…"
        largo = sum(f.getlength(c) for c in texto) + esp * (len(texto) - 1)
    capa = Image.new("RGBA", (int(largo) + 4, int(tam * 1.5)), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    x = 2
    for c in texto:
        dc.text((x, tam * 0.15), c, font=f, fill=tinta, stroke_width=1, stroke_fill=tinta)
        x += f.getlength(c) + esp
    capa = capa.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    img.alpha_composite(capa, (round(cx - capa.width / 2), round(cy - capa.height / 2)))


def png64(im):
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def svg(ancho, alto, estante, libro=None, animado=False, etiqueta=""):
    anim = (
        "<style>.sale{animation:sale 7s ease-in-out 1.5s infinite}"
        "@keyframes sale{0%,62%,100%{transform:translateY(0)}74%,88%{transform:translateY(-22px)}}"
        "@media (prefers-reduced-motion:reduce){.sale{animation:none}}</style>" if animado else ""
    )
    clase = ' class="sale"' if animado else ""
    capa = f'<g{clase}><image href="data:image/png;base64,{png64(libro)}" width="{ancho}" height="{alto}"/></g>' if libro else ""
    rol = f'role="img" aria-label="{escape(etiqueta, quote=True)}"' if etiqueta else 'aria-hidden="true"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho // 2}" height="{alto // 2}" viewBox="0 0 {ancho} {alto}" {rol}>'
        f'{anim}<image href="data:image/png;base64,{png64(estante)}" width="{ancho}" height="{alto}"/>{capa}</svg>'
    )


def variante(kb, texto):
    grosor = GROSORES[min(3, max(0, int(math.log10(max(kb, 1)) - 1)))]
    n = len(texto)
    alto = ALTOS[0] if n <= 9 else ALTOS[1] if n <= 15 else ALTOS[2]
    return f"libro-{grosor}-{alto}"


def generar(repos, infos, colores, sello, salida):
    """Escribe un SVG por libro (y los sujetalibros) y devuelve el HTML de la estantería."""
    meta = json.load(open(os.path.join(RES, "libros.json"), encoding="utf-8"))
    estante = imagen("estante.png")
    alto = meta["alto"]
    x = 0
    piezas = []

    def tramo(ancho):
        nonlocal x
        t = estante.crop((x, 0, x + ancho, alto))
        x += ancho
        return t

    suj = imagen("sujetalibros.png")
    piezas.append(("suj-izq", svg(suj.width, alto, Image.alpha_composite(tramo(suj.width), suj)), None))

    propios = sorted([r for r in repos if not r["fork"]], key=lambda r: r["pushed_at"], reverse=True)
    forks = sorted([r for r in repos if r["fork"]], key=lambda r: r["pushed_at"], reverse=True)
    for i, r in enumerate(propios + forks):
        info = infos.get(r["name"], {})
        nombre = info.get("titulo") or r["name"].replace("-", " ").replace("_", " ").capitalize()
        clave = variante(r.get("size", 1), nombre)
        m = meta["libros"][clave]
        color = colores.get(r.get("language"), "#57606A")
        libro = tenir(imagen(clave + ".png"), imagen(clave + "-mascara.png"), color, 0.35 if r["fork"] else 0.0)
        tinta = TINTA_OSCURA if claro(color) and not r["fork"] else ORO
        titulo(libro, m["lomo"], nombre, tinta)
        ancho = libro.width
        piezas.append((f"libro-{i + 1}", svg(ancho, alto, tramo(ancho), libro, animado=(i == 0), etiqueta=nombre), (r, info, nombre)))

    piezas.append(("suj-der", svg(suj.width, alto, Image.alpha_composite(tramo(suj.width), suj.transpose(Image.Transpose.FLIP_LEFT_RIGHT))), None))

    html = []
    for clave, contenido, datos in piezas:
        archivo = f"{clave}-{sello}.svg"
        with open(os.path.join(salida, archivo), "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
        if datos is None:
            html.append(f'<img src="perfil/salida/{archivo}" alt="" height="{alto // 2}">')
            continue
        r, info, nombre = datos
        desc = (info.get("descripcion") or r.get("description") or "").replace(" — ", ": ").replace("—", ":").strip()
        partes = [desc] if desc.lower().startswith(nombre.lower()) else [nombre + (f": {desc}" if desc else "")]
        if r["fork"]:
            partes.append("fork")
        if r.get("language"):
            partes.append(r["language"])
        partes.append(f"actualizado {r['pushed_at'][:10]}")
        t = escape(" · ".join(partes), quote=True)
        html.append(f'<a href="{r["html_url"]}" title="{t}"><img src="perfil/salida/{archivo}" alt="{escape(nombre, quote=True)}" title="{t}" height="{alto // 2}"></a>')
    # Sin espacios entre imágenes: así los tramos de estante se juntan
    return "<p>" + "".join(html) + "</p>"
