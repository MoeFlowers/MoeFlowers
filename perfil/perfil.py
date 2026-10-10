"""Secciones dinámicas del perfil, contadas como una sesión de Docker.

  docker inspect moeflowers   sobre mí, con datos del día (último push y commits del año)
  docker ps                   lenguajes de los repos públicos, con su tiempo en uso
  librería                    un libro por repo público; al pasar el ratón se ve el proyecto

Uso: python perfil/perfil.py   (con GITHUB_TOKEN en el entorno para no topar el límite de la API)
Genera los SVG en perfil/salida/ con un sello en el nombre (salta la caché de GitHub) y reescribe
los bloques marcados del README.
"""

import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from html import escape

import libreria

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
    txt = reemplazar(txt, "INSPECT", f'<img src="perfil/salida/inspect-{sello}.svg" alt="docker inspect moeflowers: perfil y actividad" width="100%">')
    txt = reemplazar(txt, "PS", f'<img src="perfil/salida/ps-{sello}.svg" alt="docker ps: lenguajes de mis repositorios públicos" width="100%">')
    txt = reemplazar(txt, "LIBROS", libreria.generar(repos, CONFIG.get("libros", {}), LENGUAJE, sello, SALIDA))
    open(README, "w", encoding="utf-8", newline="\n").write(txt)
    print("listo", sello, len(repos), "repos")


if __name__ == "__main__":
    main()
