"""Actualiza la biblioteca de repositorios públicos del README.

Uso: python perfil/perfil.py (GITHUB_TOKEN es opcional).
"""

import json
import os
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import libreria

HERE = Path(__file__).resolve().parent
SALIDA = HERE / "salida"
README = HERE.parent / "README.md"
CONFIG = json.loads((HERE / "perfil.json").read_text(encoding="utf-8"))
USUARIO = CONFIG["usuario"]

LENGUAJE = {
    "Python": "#3572A5", "TypeScript": "#2F74C0", "JavaScript": "#B8951F", "PHP": "#4F5D95",
    "HTML": "#B8492A", "CSS": "#563D7C", "Dart": "#0B8F8A", "Vue": "#2E8F62", "Astro": "#B5400F",
    "Shell": "#4E8A2E", "Blade": "#B5372B",
}


def api(ruta):
    req = urllib.request.Request(
        f"https://api.github.com/{ruta}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "perfil"},
    )
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=20) as respuesta:
        return json.load(respuesta)


def main():
    readme, salida = Path(README), Path(SALIDA)
    texto = readme.read_bytes().decode("utf-8")
    inicio, fin = "<!-- LIBROS:INICIO -->", "<!-- LIBROS:FIN -->"
    antes, _, resto = texto.partition(inicio)
    _, separador, despues = resto.partition(fin)
    if texto.count(inicio) != 1 or texto.count(fin) != 1 or not separador:
        raise SystemExit("El README debe tener un solo bloque LIBROS")

    repos = [
        repo for repo in api(f"users/{USUARIO}/repos?per_page=100&type=owner")
        if repo["name"] not in CONFIG["excluir"]
    ]
    salto = "\r\n" if "\r\n" in texto else "\n"
    with TemporaryDirectory(dir=salida.parent) as temporal:
        carpeta = Path(temporal)
        libros = libreria.generar(repos, CONFIG.get("libros", {}), LENGUAJE, carpeta)
        nuevo = antes + inicio + salto + libros + salto + fin + despues
        recursos = list(carpeta.glob("*.svg"))
        salida.mkdir(exist_ok=True)
        for ruta in recursos:
            ruta.replace(salida / ruta.name)
        if nuevo != texto:
            readme_temporal = carpeta / readme.name
            readme_temporal.write_bytes(nuevo.encode("utf-8"))
            readme_temporal.replace(readme)
        nombres = {ruta.name for ruta in recursos}
        for ruta in salida.glob("*.svg"):
            if ruta.name not in nombres:
                ruta.unlink()
    print("Biblioteca generada:", len(repos), "repositorios")


if __name__ == "__main__":
    main()
