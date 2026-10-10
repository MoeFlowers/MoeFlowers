"""Renderiza los recursos del puerto Docker del perfil.

Salida en puerto/recursos/:
  barco.png             buque con agua, sin contenedores (fondo transparente)
  contenedor-<n>.png    un contenedor por color con su sombra (misma cámara, origen en 0,0,0)
  meta.json             píxel de cada hueco, orden de dibujo y la cara donde va el nombre

Uso: blender -b -P puerto/blender/escena.py -- [muestras] [porcentaje]
"""

import json
import math
import os
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
SAMPLES = int(argv[0]) if argv else 128
PCT = int(argv[1]) if len(argv) > 1 else 100

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "recursos")
os.makedirs(OUT, exist_ok=True)

W, H = 1800, 980

# Contenedor de 20 pies (m)
CL, CW, CH = 6.06, 2.44, 2.59
BAYS, ROWS, TIERS = 10, 4, 3
GAP_X, GAP_Y = 0.32, 0.12
DECK_Z = 0.0
HATCH_H = 0.35
BEAM = ROWS * (CW + GAP_Y) + 2.6
CARGO_LEN = BAYS * (CL + GAP_X)
BRIDGE_LEN = 11.0
BOW_LEN = 13.0
BOW_TAPER = 14.0
HULL_LEN = CARGO_LEN + BRIDGE_LEN + BOW_LEN
STERN_X = -HULL_LEN / 2
CARGO_X0 = STERN_X + BRIDGE_LEN + 1.0

COLORS = {
    "azul": "#2496ED",
    "azul-oscuro": "#1D63ED",
    "cian": "#0DB7ED",
    "verde": "#17A398",
    "naranja": "#E5862A",
    "rojo": "#C8394F",
    "gris": "#3B4A5F",
    "blanco": "#E9EDF2",
}


def srgb(hexstr):
    h = hexstr.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*lin, 1.0)


def material(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(color) if isinstance(color, str) else color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def box(name, size, loc, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    o.data.materials.append(mat)
    return o


def tapered(name, size, loc, mat, factor, bevel=0.0):
    """Caja cuya cara delantera (+X) se estrecha a factor * ancho."""
    o = box(name, size, loc, mat, bevel)
    for v in o.data.vertices:
        if v.co.x > 0:
            v.co.y *= factor
    return o


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def setup_render():
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
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
    s.render.resolution_x, s.render.resolution_y = W, H
    s.render.resolution_percentage = PCT
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA"
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Base Contrast"

    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    s.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = srgb("#C9D8EA")
    bg.inputs["Strength"].default_value = 0.85

    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(42), 0, math.radians(-38)))
    sun = bpy.context.object
    sun.data.energy = 3.4
    sun.data.angle = math.radians(4)
    sun.data.color = (1.0, 0.97, 0.92)

    # Cámara isométrica: desde proa-estribor, mirando al centro del barco
    bpy.ops.object.camera_add(location=(58, -58, 52))
    cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 112
    target = bpy.data.objects.new("objetivo", None)
    target.location = (-2.0, 0, 2.5)
    s.collection.objects.link(target)
    c = cam.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    s.camera = cam
    return cam


def px(cam, p):
    s = bpy.context.scene
    bpy.context.view_layer.update()
    v = world_to_camera_view(s, cam, Vector(p))
    w, h = W * PCT / 100, H * PCT / 100
    return [round(v.x * w, 2), round((1 - v.y) * h, 2), round(v.z, 4)]


# Barco

def build_ship():
    navy = material("casco", "#1E2A44", 0.8, 0.0)
    white = material("blanco", "#EEF1F5", 0.45)
    deck = material("cubierta", "#4B5563", 0.7)
    hatch = material("escotillas", "#5B6676", 0.6, 0.3)
    glass = material("ventanas", "#14213D", 0.15, 0.6)
    blue = material("chimenea", "#2496ED", 0.4)

    # Casco: tramo recto + proa que se afila solo en sus últimos metros
    main_len = HULL_LEN - BOW_TAPER
    main_cx = STERN_X + main_len / 2
    bow_x0 = STERN_X + main_len - 0.3
    box("casco", (main_len, BEAM, 7.0), (main_cx, 0, DECK_Z - 3.5), navy, bevel=0.25)
    tapered("proa", (BOW_TAPER + 0.3, BEAM, 7.0), (bow_x0 + (BOW_TAPER + 0.3) / 2, 0, DECK_Z - 3.5), navy, 0.12, bevel=0.2)
    box("franja", (main_len - 2, BEAM + 0.04, 0.35), (main_cx + 1, 0, DECK_Z - 0.9), white)
    sl = BOW_TAPER - 1.5
    tapered("franja-proa", (sl, BEAM + 0.04, 0.35), (bow_x0 + 0.3 + sl / 2, 0, DECK_Z - 0.9), white, 1 - 0.88 * sl / BOW_TAPER)
    box("cubierta", (main_len - 1, BEAM - 0.5, 0.12), (main_cx, 0, DECK_Z + 0.06), deck)

    # Espuma en la línea de flotación, con la misma silueta del casco
    foam = material("espuma", "#CFE3F1", 0.5)
    box("espuma", (main_len + 1.2, BEAM + 0.9, 0.05), (main_cx - 0.3, 0, DECK_Z - 3.97), foam)
    tapered("espuma-proa", (BOW_TAPER + 1.5, BEAM + 0.9, 0.05), (bow_x0 + (BOW_TAPER + 1.5) / 2, 0, DECK_Z - 3.97), foam, 0.2)

    # Tapas de escotilla bajo cada bahía
    for b in range(BAYS):
        x = CARGO_X0 + b * (CL + GAP_X) + CL / 2
        box(f"escotilla-{b}", (CL + 0.1, ROWS * (CW + GAP_Y) + 0.3, HATCH_H), (x, 0, DECK_Z + HATCH_H / 2), hatch, bevel=0.05)

    # Superestructura en popa
    bx = STERN_X + BRIDGE_LEN / 2 + 0.5
    box("puente-base", (8.0, BEAM - 1.6, 8.5), (bx, 0, DECK_Z + 4.25), white, bevel=0.12)
    box("puente-alto", (6.0, BEAM + 1.2, 3.0), (bx + 0.6, 0, DECK_Z + 10.0), white, bevel=0.12)
    box("ventanas-puente", (0.1, BEAM + 0.6, 1.1), (bx + 3.62, 0, DECK_Z + 10.2), glass)
    for i, z in enumerate((2.4, 5.2)):
        box(f"ventanas-{i}", (0.1, BEAM - 2.6, 0.7), (bx + 4.02, 0, DECK_Z + z + 0.6), glass)
    box("chimenea", (2.6, 2.8, 4.2), (bx - 2.4, 0, DECK_Z + 12.0), white, bevel=0.2)
    box("chimenea-banda", (2.66, 2.86, 1.1), (bx - 2.4, 0, DECK_Z + 13.0), blue, bevel=0.2)

    # Nombre en el costado de estribor
    bpy.ops.object.text_add(location=(HULL_LEN / 2 - 20, -BEAM / 2 - 0.06, DECK_Z - 2.9), rotation=(math.radians(90), 0, 0))
    t = bpy.context.object
    t.data.body = "MOEFLOWERS"
    t.data.size = 2.0
    t.data.align_x = "CENTER"
    t.data.extrude = 0.02
    t.data.materials.append(white)


def build_sea():
    mat = bpy.data.materials.new("mar")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb("#1F6FA8")
    b.inputs["Roughness"].default_value = 0.12
    b.inputs["Specular IOR Level"].default_value = 0.6
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.6
    noise.inputs["Detail"].default_value = 6
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])

    bpy.ops.mesh.primitive_plane_add(size=1, location=(1.5, 0, DECK_Z - 4.0))
    sea = bpy.context.object
    sea.name = "mar"
    sea.scale = (HULL_LEN + 14, BEAM + 20, 1)
    bpy.ops.object.transform_apply(scale=True)
    bev = sea.modifiers.new("bisel", "BEVEL")
    bev.affect = "VERTICES"
    bev.width = 7
    bev.segments = 10
    sea.data.materials.append(mat)
    # Borde de la isla de agua
    bpy.ops.mesh.primitive_plane_add(size=1, location=(1.5, 0, DECK_Z - 4.6))
    rim = bpy.context.object
    rim.scale = (HULL_LEN + 14.6, BEAM + 20.6, 1)
    bpy.ops.object.transform_apply(scale=True)
    sol = rim.modifiers.new("grosor", "SOLIDIFY")
    sol.thickness = 1.2
    bev = rim.modifiers.new("bisel", "BEVEL")
    bev.affect = "VERTICES"
    bev.width = 7.3
    bev.segments = 10
    rim.data.materials.append(material("borde-mar", "#123E5E", 0.4))


# Contenedor

def build_container(color):
    paint = material(f"pintura-{color}", COLORS[color], 0.42, 0.25)
    dark = material("herrajes", "#20242B", 0.5, 0.6)
    root = box("contenedor", (CL, CW, CH), (0, 0, CH / 2), paint, bevel=0.04)
    parts = [root]
    # Corrugado en los costados largos
    n = 18
    for i in range(n):
        x = -CL / 2 + 0.35 + i * (CL - 0.7) / (n - 1)
        for side in (-1, 1):
            parts.append(box(f"costilla-{i}-{side}", (0.12, 0.06, CH - 0.32), (x, side * (CW / 2 + 0.02), CH / 2), paint))
    # Esquineros
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.09, CH - 0.09):
                parts.append(box("esquinero", (0.2, 0.2, 0.18), (sx * (CL / 2 - 0.08), sy * (CW / 2 - 0.08), z), dark))
    # Barras de las puertas (extremo de popa, -X)
    for y in (-0.7, -0.25, 0.25, 0.7):
        parts.append(box("barra", (0.05, 0.05, CH - 0.4), (-CL / 2 - 0.03, y, CH / 2), dark))
    return parts


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    clear()
    cam = setup_render()
    build_sea()
    build_ship()
    render(os.path.join(OUT, "barco.png"))

    # Huecos: posición del centro de la base de cada contenedor
    slots = []
    for t in range(TIERS):
        for b in range(BAYS):
            for r in range(ROWS):
                x = CARGO_X0 + b * (CL + GAP_X) + CL / 2
                y = (r - (ROWS - 1) / 2) * (CW + GAP_Y)
                z = DECK_Z + HATCH_H + t * CH
                p = px(cam, (x, y, z))
                center = px(cam, (x, y, z + CH / 2))
                slots.append({"bay": b, "row": r, "tier": t, "x": p[0], "y": p[1], "depth": center[2]})
    anchor = px(cam, (0, 0, 0))
    # Cara de estribor (-Y), la que mira a la cámara: aquí va el nombre
    face = [px(cam, c)[:2] for c in ((-CL / 2 + 0.4, -CW / 2 - 0.08, CH - 0.35), (CL / 2 - 0.4, -CW / 2 - 0.08, CH - 0.35), (CL / 2 - 0.4, -CW / 2 - 0.08, 0.35), (-CL / 2 + 0.4, -CW / 2 - 0.08, 0.35))]

    # Sprites: escena nueva con solo el contenedor y un captador de sombras
    for name in COLORS:
        clear()
        cam = setup_render()
        bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
        bpy.context.object.is_shadow_catcher = True
        build_container(name)
        render(os.path.join(OUT, f"contenedor-{name}.png"))

    meta = {
        "size": [W * PCT // 100, H * PCT // 100],
        "anchor": anchor[:2],
        "face": face,
        "colors": list(COLORS),
        "capacity": len(slots),
        "slots": slots,
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print("listo:", OUT)


main()
