import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "perfil"))
import perfil

sys.path.insert(0, str(ROOT / "puerto"))
import puerto


def snapshot(salida):
    return {ruta.name: ruta.read_bytes() for ruta in salida.iterdir()}


class RegeneracionTest(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.base = Path(carpeta.name)
        self.readme = self.base / "README.md"
        self.salida = self.base / "salida"
        self.prosa = (
            "# Una presentación escrita a mano\n\n"
            "[Professional profile](https://example.com/career)\n\n"
            "<details>\n<summary>Creative projects</summary>\n\n"
            "<!-- PUERTO:INICIO -->\nbarco\n<!-- PUERTO:FIN -->\n\n"
            "<!-- LIBROS:INICIO -->\nlibros\n<!-- LIBROS:FIN -->\n\n"
            "</details>\n\n"
            "Gracias por pasar.\n"
        )
        self.readme.write_text(self.prosa, encoding="utf-8")

    def afirmar_prosa(self, marca, anterior):
        patron = rf"(<!-- {marca}:INICIO -->).*?(<!-- {marca}:FIN -->)"
        original = re.sub(patron, r"\1\2", anterior, flags=re.S)
        actual = re.sub(patron, r"\1\2", self.readme.read_text(encoding="utf-8"), flags=re.S)
        self.assertEqual(actual, original)

    def test_biblioteca_conserva_prosa_puerto_y_enlaces_con_dos_regeneraciones(self):
        repo = {
            "name": "Portfolio",
            "html_url": "https://github.com/MoeFlowers/Portfolio",
            "pushed_at": "2026-10-25T21:33:00Z",
            "created_at": "2025-10-25T21:33:00Z",
            "fork": False,
            "language": "TypeScript",
        }
        with (
            patch.object(perfil, "README", self.readme),
            patch.object(perfil, "SALIDA", self.salida),
            patch.object(perfil, "api", side_effect=lambda ruta: [repo] if ruta.startswith("users/") else {}),
        ):
            perfil.main()
            primer_readme = self.readme.read_bytes()
            primeros_recursos = snapshot(self.salida)
            perfil.main()
        self.afirmar_prosa("LIBROS", self.prosa)
        self.assertEqual(self.readme.read_bytes(), primer_readme)
        self.assertEqual(snapshot(self.salida), primeros_recursos)
        self.assertIn(repo["html_url"], self.readme.read_text(encoding="utf-8"))
        self.assertIn('alt="Portfolio"', self.readme.read_text(encoding="utf-8"))

    def test_puerto_conserva_prosa_biblioteca_y_generacion_incluso_en_otro_segundo(self):
        datos = {"contenedores": [{"usuario": "example-visitor", "fecha": "2026-11-15"}]}
        instantes = [datetime(2026, 11, 15, 12, i, tzinfo=timezone.utc) for i in range(2)]
        with (
            patch.object(puerto, "README", self.readme),
            patch.object(puerto, "SALIDA", self.salida),
            patch.object(puerto, "avatar", return_value=None),
            patch.object(puerto, "ANCHO_SALIDA", 350),
            patch.object(puerto, "datetime", wraps=datetime) as reloj,
        ):
            reloj.now.side_effect = instantes
            puerto.generar(datos)
            primer_readme = self.readme.read_bytes()
            primeros_recursos = snapshot(self.salida)
            puerto.generar(datos)
        self.afirmar_prosa("PUERTO", self.prosa)
        self.assertEqual(self.readme.read_bytes(), primer_readme)
        self.assertEqual(snapshot(self.salida), primeros_recursos)
        self.assertIn("issues/new?title=docker+run", self.readme.read_text(encoding="utf-8"))

    def test_marcadores_invalidos_no_eliminan_los_assets_existentes(self):
        self.readme.write_text("Un perfil sin marcadores\n", encoding="utf-8")
        self.salida.mkdir()
        asset = self.salida / "libro-anterior.svg"
        asset.write_bytes(b"<svg/>")
        with (
            patch.object(perfil, "README", self.readme),
            patch.object(perfil, "SALIDA", self.salida),
            patch.object(perfil, "api", return_value=[{
                "name": "example", "fork": False, "pushed_at": "2026-11-15", "created_at": "2025-11-15"
            }]),
            self.assertRaisesRegex(SystemExit, "LIBROS"),
        ):
            perfil.main()
        self.assertEqual(snapshot(self.salida), {asset.name: b"<svg/>"})


if __name__ == "__main__":
    unittest.main()
