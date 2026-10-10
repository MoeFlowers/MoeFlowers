"""Renderiza los libros 3D de la librería del perfil (en color neutro, se tiñen al componer).

Salida en perfil/recursos/:
  libro-<grosor>-<alto>.png   un libro por combinación de grosor y alto, con su sombra
  estante.png                 la tabla de madera, larga (cada libro recorta su tramo)
  sujetalibros.png            sujetalibros metálico
  libros.json                 tamaño de cada imagen, fila de la base y rectángulo del lomo

Todas las imágenes comparten escala (px por metro) y la fila de la base del estante,
así que al ponerlas una junto a otra encajan.
Uso: blender -b -P perfil/blender/libros.py -- [muestras]
"""

import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
SAMPLES = int(argv[0]) if argv else 96

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "recursos")
os.makedirs(OUT, exist_ok=True)

PX_M = 1400            # píxeles por metro (imagen al doble del tamaño en pantalla)
ALTO_PX = 472          # alto de cada imagen
BASE_PX = 424          # fila de la superficie del estante
INCLINA = 7           # grados que la cámara mira hacia abajo
GROSORES = [0.058, 0.066, 0.074, 0.082]
ALTOS = [0.205, 0.235, 0.265]
FONDO = 0.16           # profundidad de los libros


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return (*[x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c], 1.0)


def material(nombre, color, rough=0.5, metal=0.0, bump=0.0, escala=300.0):
    m = bpy.data.materials.get(nombre) or bpy.data.materials.new(nombre)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if bump:
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = escala
        n.inputs["Detail"].default_value = 8
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def caja(size, loc, mat, bevel=0.0, segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        m = o.modifiers.new("bisel", "BEVEL")
        m.width = bevel
        m.segments = segs
        bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return o


def limpiar():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def escena(ancho_m, centro_x):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for tipo in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            prefs.compute_device_type = tipo
            prefs.get_devices()
            if any(d.type == tipo for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == tipo
                s.cycles.device = "GPU"
                break
        except TypeError:
            continue
    s.cycles.samples = SAMPLES
    s.cycles.use_denoising = True
    try:
        s.cycles.denoising_use_gpu = True
    except AttributeError:
        pass
    s.render.film_transparent = True
    s.view_settings.view_transform = "AgX"
    s.render.resolution_x = max(2, round(ancho_m * PX_M))
    s.render.resolution_y = ALTO_PX
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA"

    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    s.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = srgb("#DDE3EA")
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    # Luz principal desde la izquierda: deja ver la curva del lomo (claro a oscuro)
    bpy.ops.object.light_add(type="AREA", location=(-1.1, -0.45, 0.45))
    luz = bpy.context.object
    luz.data.energy = 30
    luz.data.size = 0.35
    luz.rotation_euler = (math.radians(70), 0, math.radians(-68))
    bpy.ops.object.light_add(type="AREA", location=(0.6, -0.6, 0.3))
    relleno = bpy.context.object
    relleno.data.energy = 4
    relleno.data.size = 1.0
    relleno.rotation_euler = (math.radians(70), 0, math.radians(45))

    # Cámara ortográfica de frente, un poco desde arriba; la escala fija px/m
    alto_m = ALTO_PX / PX_M
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(alto_m, ancho_m)
    cam.rotation_euler = (math.radians(90 - INCLINA), 0, 0)
    s.camera = cam
    # Coloca la cámara para que z=0 (superficie del estante, borde frontal) caiga en BASE_PX
    cam.location = (centro_x, -2.0, 0.0)
    bpy.context.view_layer.update()
    v = world_to_camera_view(s, cam, Vector((centro_x, -FONDO / 2, 0)))
    fila = (1 - v.y) * ALTO_PX
    # Subir la cámara baja la imagen: sube lo que falte para que el punto quede en BASE_PX
    arriba = cam.matrix_world.to_quaternion() @ Vector((0, 1, 0))
    cam.location = cam.location + arriba * ((BASE_PX - fila) / PX_M)
    bpy.context.view_layer.update()
    return cam


def px(cam, p):
    s = bpy.context.scene
    v = world_to_camera_view(s, cam, Vector(p))
    return [round(v.x * s.render.resolution_x, 1), round((1 - v.y) * ALTO_PX, 1)]


def render(ruta):
    bpy.context.scene.render.filepath = ruta
    bpy.ops.render.render(write_still=True)


def libro(t, h):
    tela = material("tela", "#B4B4B4", 0.5, 0.0, bump=0.05, escala=1400)
    tapa = material("tapa", "#C8C8C8", 0.55)
    hojas = material("hojas", "#F2EBDD", 0.8, 0.0, bump=0.15, escala=2500)
    # Tapas (un poco más altas y salientes que el bloque de hojas) y lomo redondeado
    for lado in (-1, 1):
        caja((0.0028, FONDO, h), (lado * (t / 2 - 0.0014), 0, h / 2), tapa, bevel=0.0009)
    caja((t - 0.004, FONDO - 0.006, h - 0.006), (0, 0.003, h / 2), hojas)
    # Lomo redondeado: cilindro aplanado que sobresale un poco por delante
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=t / 2, depth=h, location=(0, -FONDO / 2 + t * 0.2, h / 2))
    lomo = bpy.context.object
    lomo.scale = (1, 0.62, 1)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    lomo.data.materials.append(tela)
    return lomo


def mascara(ruta):
    """Blanco donde va el color (tapas y lomo), negro en las hojas: así el tinte no pinta las páginas."""
    s = bpy.context.scene
    for o in s.objects:
        if o.type != "MESH" or o.is_shadow_catcher:
            continue
        nombre = o.active_material.name
        m = bpy.data.materials.new(f"mascara-{o.name}")
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (0, 0, 0, 1) if nombre.startswith("hojas") else (1, 1, 1, 1)
        salida = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs["Emission"], salida.inputs["Surface"])
        o.data.materials[0] = m
    muestras, vista = s.cycles.samples, s.view_settings.view_transform
    s.cycles.samples, s.view_settings.view_transform = 1, "Standard"
    s.cycles.use_denoising = False
    render(ruta)
    s.cycles.samples, s.view_settings.view_transform = muestras, vista
    s.cycles.use_denoising = True


def main():
    meta = {"px_m": PX_M, "alto": ALTO_PX, "base": BASE_PX, "libros": {}}
    sombra = None
    for t in GROSORES:
        for h in ALTOS:
            limpiar()
            cam = escena(t + 0.004, 0.0)
            bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0, 0, 0))
            bpy.context.object.is_shadow_catcher = True
            libro(t, h)
            nombre = f"libro-{round(t * 1000)}-{round(h * 1000)}"
            render(os.path.join(OUT, nombre + ".png"))
            mascara(os.path.join(OUT, nombre + "-mascara.png"))
            y = -FONDO / 2 + t * 0.2 - t / 2 * 0.62 - 0.001
            meta["libros"][nombre] = {
                "grosor": t, "alto": h, "ancho_px": bpy.context.scene.render.resolution_x,
                # Rectángulo del lomo (para el título): esquinas sup-izq e inf-der
                "lomo": [px(cam, (-t / 2 + 0.004, y, h - 0.012)), px(cam, (t / 2 - 0.004, y, 0.012))],
            }

    # Estante: tabla larga de madera con veta
    limpiar()
    largo = 1.4
    cam = escena(largo, 0.0)
    madera = material("madera", "#5A3D27", 0.5, 0.0, bump=0.04, escala=180)
    caja((largo + 0.2, 0.24, 0.028), (0, 0.02, -0.014), madera, bevel=0.002)
    render(os.path.join(OUT, "estante.png"))
    meta["estante"] = {"ancho_px": bpy.context.scene.render.resolution_x}

    # Sujetalibros: pieza en L de metal oscuro
    limpiar()
    cam = escena(0.03, 0.0)
    bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0, 0, 0))
    bpy.context.object.is_shadow_catcher = True
    metal = material("metal", "#2B3137", 0.35, 0.8)
    caja((0.006, 0.12, 0.13), (0, 0, 0.065), metal, bevel=0.0015)
    caja((0.03, 0.12, 0.004), (0, 0, 0.002), metal, bevel=0.001)
    render(os.path.join(OUT, "sujetalibros.png"))
    meta["sujetalibros"] = {"ancho_px": bpy.context.scene.render.resolution_x}

    with open(os.path.join(OUT, "libros.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print("listo:", OUT)


main()
