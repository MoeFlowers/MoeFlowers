"""Secciones dinámicas del perfil, contadas como una sesión de Docker.

  docker inspect moeflowers   sobre mí, con datos del día (último push, commits del año, tasa BCV)
  docker ps                   lenguajes de los repos públicos, con su tiempo en uso
  librería                    un libro por repo público; al pasar el ratón se ve el proyecto

Uso: python perfil/perfil.py   (con GITHUB_TOKEN en el entorno para no topar el límite de la API)
Genera los SVG en perfil/salida/ con un sello en el nombre (salta la caché de GitHub) y reescribe
los bloques marcados del README.
"""

import hashlib
import json
import math
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SALIDA = os.path.join(HERE, "salida")
README = os.path.join(ROOT, "README.md")
CONFIG = json.load(open(os.path.join(HERE, "perfil.json"), encoding="utf-8"))
USUARIO = CONFIG["usuario"]
AHORA = datetime.now(timezone.utc)

MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
# Colores de sintaxis del tema oscuro de GitHub
C = {"fondo": "#0D1117", "borde": "#30363D", "texto": "#E6EDF3", "tenue": "#9198A1",
     "prompt": "#7EE787", "clave": "#79C0FF", "cadena": "#A5D6FF", "numero": "#FFA657"}
LENGUAJE = {
    "Python": "#3572A5", "TypeScript": "#2F74C0", "JavaScript": "#B8951F", "PHP": "#4F5D95",
    "HTML": "#B8492A", "CSS": "#563D7C", "Dart": "#0B8F8A", "Vue": "#2E8F62", "Astro": "#B5400F",
    "Shell": "#4E8A2E", "Blade": "#B5372B",
}


# Solo lenguajes de programación: el marcado inflaría el porcentaje (cursos y páginas sueltas)
MARCADO = {"HTML", "CSS", "SCSS", "Less"}


def api(ruta):
    req = urllib.request.Request(f"https://api.github.com/{ruta}", headers={"Accept": "application/vnd.github+json", "User-Agent": "perfil"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def tasa_bcv():
    try:
        req = urllib.request.Request("https://ve.dolarapi.com/v1/dolares/oficial", headers={"User-Agent": "perfil"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        valor = f"{d['promedio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        fecha = datetime.fromisoformat(d["fechaActualizacion"]).strftime("%d/%m/%Y")
        return f"1 USD = {valor} Bs (BCV, {fecha})"
    except Exception:
        return None


def hace(desde):
    """'Up 3 years' al estilo de docker ps."""
    meses = (AHORA.year - desde.year) * 12 + AHORA.month - desde.month
    if meses >= 24:
        return f"Up {meses // 12} years"
    if meses >= 12:
        return "Up 1 year"
    return "Up 1 month" if meses <= 1 else f"Up {meses} months"


# Terminal

def terminal(comando, lineas, ancho=830, alto_linea=21):
    """SVG de terminal: escribe el comando y luego aparecen las líneas una a una (una sola vez)."""
    pad = 22
    alto = pad * 2 + alto_linea * (len(lineas) + 1) + 6
    largo = len("$ " + comando)
    dur = 0.045 * largo
    filas = []
    for i, partes in enumerate(lineas):
        y = pad + alto_linea * (i + 2) + 4
        spans = "".join(f'<tspan fill="{C[c]}">{escape(t)}</tspan>' for c, t in partes)
        filas.append(f'<text x="{pad}" y="{y}" class="l" style="animation-delay:{dur + 0.25 + i * 0.07:.2f}s" xml:space="preserve">{spans}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}" role="img" aria-label="$ {escape(comando)}">
<style>
text{{font:400 13px {MONO}}}
.l{{opacity:0;animation:ver .01s linear forwards}}
.c{{animation:escribe {dur:.2f}s steps({largo}) forwards}}
.cursor{{animation:parpadeo 1s steps(1) infinite}}
@keyframes ver{{to{{opacity:1}}}}
@keyframes escribe{{from{{width:0}}to{{width:{largo * 7.85 + 4:.0f}px}}}}
@keyframes parpadeo{{50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.l{{animation:none;opacity:1}}.c{{animation:none;width:{largo * 7.85 + 4:.0f}px}}.cursor{{animation:none}}}}
</style>
<rect x=".5" y=".5" width="{ancho - 1}" height="{alto - 1}" rx="8" fill="{C['fondo']}" stroke="{C['borde']}"/>
<clipPath id="tecleo"><rect class="c" x="{pad}" y="{pad}" width="0" height="{alto_linea}"/></clipPath>
<text x="{pad}" y="{pad + 15}" clip-path="url(#tecleo)" xml:space="preserve"><tspan fill="{C['prompt']}">$</tspan><tspan fill="{C['texto']}"> {escape(comando)}</tspan></text>
{"".join(filas)}
<rect class="cursor" x="{pad}" y="{pad + alto_linea * (len(lineas) + 1) + 9}" width="8" height="15" fill="{C['tenue']}"/>
</svg>'''


def json_lineas(obj):
    """Formatea un objeto como la salida de docker inspect, con colores por tipo."""
    out = []

    def valor(v):
        if isinstance(v, str):
            return [("cadena", json.dumps(v, ensure_ascii=False))]
        if isinstance(v, list):
            partes = [("texto", "[")]
            for i, x in enumerate(v):
                partes += valor(x) + ([("texto", ", ")] if i < len(v) - 1 else [])
            return partes + [("texto", "]")]
        return [("numero", str(v))]

    def bloque(d, nivel):
        items = list(d.items())
        for i, (k, v) in enumerate(items):
            coma = [("texto", ",")] if i < len(items) - 1 else []
            sang = ("texto", "  " * nivel)
            if isinstance(v, dict):
                out.append([sang, ("clave", json.dumps(k)), ("texto", ": {")])
                bloque(v, nivel + 1)
                out.append([("texto", "  " * nivel + "}")] + coma)
            else:
                out.append([sang, ("clave", json.dumps(k)), ("texto", ": ")] + valor(v) + coma)

    out.append([("texto", "[")])
    out.append([("texto", "  {")])
    bloque(obj, 2)
    out.append([("texto", "  }")])
    out.append([("texto", "]")])
    return out


def inspect(repos):
    datos = dict(CONFIG["inspect"])
    propios = [r for r in repos if not r["fork"]]
    ultimo = max(r["pushed_at"] for r in propios)[:10]
    estado = {"LastPush": ultimo, "PublicRepos": len(propios)}
    try:
        estado["CommitsThisYear"] = api(f"search/commits?q=author:{USUARIO}+committer-date:>={AHORA.year}-01-01&per_page=1")["total_count"]
    except Exception:
        pass
    datos["State"] = estado
    tasa = tasa_bcv()
    if tasa:
        datos["Rate"] = tasa
    return terminal("docker inspect moeflowers", json_lineas(datos))


def ps(repos):
    propios = [r for r in repos if not r["fork"]]
    total, desde, cuantos = {}, {}, {}
    for r in propios:
        try:
            langs = api(f"repos/{USUARIO}/{r['name']}/languages")
        except Exception:
            continue
        creado = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        for lang, b in langs.items():
            if lang in MARCADO:
                continue
            total[lang] = total.get(lang, 0) + b
            cuantos[lang] = cuantos.get(lang, 0) + 1
            desde[lang] = min(desde.get(lang, creado), creado)
    suma = sum(total.values()) or 1
    top = sorted(total, key=total.get, reverse=True)[:8]
    fmt = "{:<14}{:<14}{:<16}{:>7}{:>8}"
    lineas = [[("tenue", fmt.format("CONTAINER ID", "IMAGE", "STATUS", "CÓDIGO", "REPOS"))]]
    for lang in top:
        cid = hashlib.sha1(lang.encode()).hexdigest()[:12]
        pct = f"{100 * total[lang] / suma:.1f}%"
        fila = fmt.format(cid, lang.lower(), hace(desde[lang]), pct, cuantos[lang])
        lineas.append([("tenue", fila[:14]), ("cadena", fila[14:28]), ("prompt", fila[28:44]), ("texto", fila[44:])])
    return terminal("docker ps", lineas)


# Librería

def mezclar(hexa, factor):
    """factor > 0 aclara hacia blanco, < 0 oscurece hacia negro."""
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    if factor >= 0:
        r, g, b = (round(c + (255 - c) * factor) for c in (r, g, b))
    else:
        r, g, b = (round(c * (1 + factor)) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def luminancia(hexa):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


ALTO_TILE, Y_ESTANTE = 236, 212


def estante(ancho):
    """Tramo de tabla: cada tile lleva el suyo y juntos forman una estantería continua."""
    return (
        f'<rect x="0" y="{Y_ESTANTE}" width="{ancho}" height="7" fill="#9C7A5B"/>'
        f'<rect x="0" y="{Y_ESTANTE + 7}" width="{ancho}" height="13" fill="#6E5139"/>'
        f'<rect x="0" y="{Y_ESTANTE + 7}" width="{ancho}" height="1" fill="#B8977A"/>'
        f'<rect x="0" y="{Y_ESTANTE + 20}" width="{ancho}" height="4" fill="#000" opacity=".18"/>'
    )


def libro(repo, info, animado):
    lang = repo.get("language")
    base = LENGUAJE.get(lang, "#57606A")
    if repo["fork"]:
        base = mezclar(base, -0.35)
    kb = max(repo.get("size", 1), 1)
    alto = round(min(190, 132 + 8 * math.log10(kb) * 1.6))
    titulo = info.get("titulo") or repo["name"].replace("-", " ").replace("_", " ").capitalize()
    tam = 13
    while tam > 10 and len(titulo) * tam * 0.6 > alto - 46:
        tam -= 1
    if len(titulo) * tam * 0.6 > alto - 46:
        titulo = titulo[: int((alto - 46) / (tam * 0.6)) - 1] + "…"
    grosor = round(min(54, 36 + 4 * math.log10(kb)))
    ancho = grosor + 4
    x0, y0 = 2, Y_ESTANTE - alto
    tinta = "#1F2328" if luminancia(base) > 0.45 else "#FFFFFF"
    banda = mezclar(base, 0.45) if tinta == "#FFFFFF" else mezclar(base, -0.4)
    gid = hashlib.sha1(repo["name"].encode()).hexdigest()[:8]
    cinta = (f'<path d="M{x0 + grosor - 14} {y0} h8 v22 l-4 -5 l-4 5 z" fill="#C8394F"/>' if repo["fork"] else "")
    clase = ' class="sale"' if animado else ""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{ALTO_TILE}" viewBox="0 0 {ancho} {ALTO_TILE}" role="img" aria-label="{escape(titulo)}">
<style>
.sale{{animation:sale 7s ease-in-out 1.5s infinite}}
@keyframes sale{{0%,62%,100%{{transform:translateY(0)}}74%,88%{{transform:translateY(-12px)}}}}
@media (prefers-reduced-motion:reduce){{.sale{{animation:none}}}}
</style>
<defs><linearGradient id="g{gid}" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="{mezclar(base, -0.35)}"/><stop offset=".18" stop-color="{base}"/>
<stop offset=".55" stop-color="{mezclar(base, 0.14)}"/><stop offset="1" stop-color="{mezclar(base, -0.42)}"/>
</linearGradient></defs>
{estante(ancho)}
<g{clase}>
<rect x="{x0}" y="{y0}" width="{grosor}" height="{alto}" rx="2.5" fill="url(#g{gid})"/>
<rect x="{x0}" y="{y0 + 12}" width="{grosor}" height="2" fill="{banda}" opacity=".7"/>
<rect x="{x0}" y="{y0 + alto - 16}" width="{grosor}" height="2" fill="{banda}" opacity=".7"/>
{cinta}
<text transform="translate({x0 + grosor / 2 + tam * 0.36:.1f} {y0 + alto / 2:.1f}) rotate(-90)" text-anchor="middle" fill="{tinta}" style="font:600 {tam}px {SANS};letter-spacing:.2px">{escape(titulo)}</text>
</g>
</svg>'''
    desc = (info.get("descripcion") or repo.get("description") or "").replace(" — ", ": ").replace("—", ":").strip()
    if desc.lower().startswith(titulo.lower()):
        partes = [desc]
    else:
        partes = [titulo + (f": {desc}" if desc else "")]
    if repo["fork"]:
        partes.append("fork")
    if lang:
        partes.append(lang)
    partes.append(f"actualizado {repo['pushed_at'][:10]}")
    return svg, " · ".join(partes)


def sujetalibros(lado):
    ancho = 24
    x = 4 if lado == "izq" else ancho - 12
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{ALTO_TILE}" viewBox="0 0 {ancho} {ALTO_TILE}" aria-hidden="true">
{estante(ancho)}
<rect x="{x}" y="{Y_ESTANTE - 92}" width="8" height="92" rx="2" fill="#2B3137"/>
<rect x="{x}" y="{Y_ESTANTE - 92}" width="8" height="3" rx="1.5" fill="#57606A"/>
</svg>'''
    return svg


def libreria(repos, sello):
    infos = CONFIG.get("libros", {})
    propios = sorted([r for r in repos if not r["fork"]], key=lambda r: r["pushed_at"], reverse=True)
    forks = sorted([r for r in repos if r["fork"]], key=lambda r: r["pushed_at"], reverse=True)
    html = []
    nombre = f"libro-0-{sello}.svg"
    open(os.path.join(SALIDA, nombre), "w", encoding="utf-8", newline="\n").write(sujetalibros("izq"))
    html.append(f'<img src="perfil/salida/{nombre}" alt="" height="{ALTO_TILE}">')
    for i, r in enumerate(propios + forks, 1):
        svg, tooltip = libro(r, infos.get(r["name"], {}), animado=(i == 1))
        nombre = f"libro-{i}-{sello}.svg"
        open(os.path.join(SALIDA, nombre), "w", encoding="utf-8", newline="\n").write(svg)
        t = escape(tooltip, quote=True)
        html.append(f'<a href="{r["html_url"]}" title="{t}"><img src="perfil/salida/{nombre}" alt="{escape(r["name"], quote=True)}" title="{t}" height="{ALTO_TILE}"></a>')
    nombre = f"libro-z-{sello}.svg"
    open(os.path.join(SALIDA, nombre), "w", encoding="utf-8", newline="\n").write(sujetalibros("der"))
    html.append(f'<img src="perfil/salida/{nombre}" alt="" height="{ALTO_TILE}">')
    # Sin espacios entre imágenes: así los tramos de estante se juntan
    return "<p>" + "".join(html) + "</p>"


def reemplazar(txt, marca, contenido):
    patron = rf"<!-- {marca}:INICIO -->.*?<!-- {marca}:FIN -->"
    nuevo = f"<!-- {marca}:INICIO -->\n{contenido}\n<!-- {marca}:FIN -->"
    if not re.search(patron, txt, flags=re.S):
        raise SystemExit(f"Falta el bloque {marca} en el README")
    return re.sub(patron, lambda _: nuevo, txt, flags=re.S)


def main():
    repos = [r for r in api(f"users/{USUARIO}/repos?per_page=100&type=owner") if r["name"] not in CONFIG["excluir"]]
    os.makedirs(SALIDA, exist_ok=True)
    for viejo in os.listdir(SALIDA):
        os.remove(os.path.join(SALIDA, viejo))
    sello = AHORA.strftime("%Y%m%d%H%M%S")
    archivos = {"inspect": inspect(repos), "ps": ps(repos)}
    for clave, svg in archivos.items():
        open(os.path.join(SALIDA, f"{clave}-{sello}.svg"), "w", encoding="utf-8", newline="\n").write(svg)
    txt = open(README, encoding="utf-8").read()
    txt = reemplazar(txt, "INSPECT", f'<img src="perfil/salida/inspect-{sello}.svg" alt="docker inspect moeflowers: perfil, estado y tasa BCV del día" width="100%">')
    txt = reemplazar(txt, "PS", f'<img src="perfil/salida/ps-{sello}.svg" alt="docker ps: lenguajes de mis repositorios públicos" width="100%">')
    txt = reemplazar(txt, "LIBROS", libreria(repos, sello))
    open(README, "w", encoding="utf-8", newline="\n").write(txt)
    print("listo", sello, len(repos), "repos")


if __name__ == "__main__":
    main()
