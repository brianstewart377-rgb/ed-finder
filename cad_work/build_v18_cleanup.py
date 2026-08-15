"""Build laptop cooling pad v18 from the validated v17 FreeCAD document.

V18 cleans up legacy corner pockets, removes the unused rear split-line bore,
and rebuilds the USB-C PD trigger mount around the measured production board.
The PD mount dimensions near the top of this file are intentionally kept in
one place so the final physical measurements can be entered without touching
the geometry code.
"""

import json
import math
import os
import shutil

import FreeCAD as App
import Import
import Mesh
import Part


SOURCE_ROOT = r"C:\Users\brian\Downloads\laptop-cooling-pad-v17-deliverables"
OUTPUT_ROOT = r"C:\Users\brian\Downloads\laptop-cooling-pad-v18-deliverables"
ORIGINAL_STEP = r"C:\Users\brian\Downloads\laptopkuhlpad.step"

SOURCE_FCSTD = os.path.join(SOURCE_ROOT, "laptop_cooling_pad_v17_print_ready.FCStd")
OUTPUT_FCSTD = os.path.join(OUTPUT_ROOT, "laptop_cooling_pad_v18_print_ready.FCStd")
OUTPUT_STEP = os.path.join(OUTPUT_ROOT, "laptop_cooling_pad_v18_split_assembly.step")
STEP_DIR = os.path.join(OUTPUT_ROOT, "assembly_parts_step")
STL_DIR = os.path.join(OUTPUT_ROOT, "print_oriented_stl")

# Corner interface: the bottom has a blended 10 mm round collar.  The old
# 10.6 mm square clearance pocket is replaced by a matching round pocket.
CORNER_RELIEF_DIAMETER = 10.6
CORNER_SQUARE_SIZE = 10.6
CORNER_POCKET_BASES = {
    "middle_front_left": (-79.0, 176.0, 22.81),
    "middle_front_right": (333.0, 176.0, 22.81),
    "middle_rear_left": (-79.0, -106.0, 94.85),
    "middle_rear_right": (333.0, -106.0, 94.85),
}

# Obsolete original bore left exactly on the bottom rear left/right split.
REAR_SPLIT_X = 127.0
REAR_HOLE_AXIS = App.Vector(0.0, -0.247501, -0.968888)
REAR_BOTTOM_HOLE_BASE = App.Vector(127.0, -114.1656, 102.6381)
REAR_BOTTOM_COUNTERBORE_RADIUS = 3.0
REAR_BOTTOM_COUNTERBORE_DEPTH = 2.8
REAR_BOTTOM_CLEARANCE_RADIUS = 1.6
REAR_BOTTOM_CLEARANCE_DEPTH = 1.200001
REAR_MIDDLE_HOLE_BASE = App.Vector(127.0, -115.0965, 98.7474)
REAR_MIDDLE_HOLE_RADIUS = 2.15
REAR_MIDDLE_HOLE_DEPTH = 7.10807

# Measured CMTPD board data.  The two hole fields are completed after the
# physical board has been measured/top-down photographed.
PD_BOARD_LENGTH = 43.5
PD_BOARD_WIDTH = 18.15
PD_BOARD_THICKNESS = 1.6
PD_HOLE_DIAMETER = 2.0
PD_USB_HOLE_EDGE_OFFSET = 3.5
PD_HOLE_ROW_SPACING = 12.5

PD_LENGTH_AXIS = App.Vector(math.cos(math.radians(10.0)), 0.0, math.sin(math.radians(10.0)))
PD_WIDTH_AXIS = App.Vector(0.0, 1.0, 0.0)
PD_NORMAL_AXIS = App.Vector(math.sin(math.radians(10.0)), 0.0, -math.cos(math.radians(10.0)))
PD_USB_EDGE_CENTRE = App.Vector(-92.788147, -48.747, 32.023312)

PD_CLEARANCE_EACH_SIDE = 0.5
PD_CLEAR_WIDTH = PD_BOARD_WIDTH + 2.0 * PD_CLEARANCE_EACH_SIDE
PD_RAIL_THICKNESS = 2.2
PD_MOUNT_DEPTH = 3.3
PD_UNDERSIDE_GAP = 1.0
PD_LEDGE_WIDTH = 1.5
PD_TERMINAL_PAD_LENGTH = 6.0
PD_BOSS_DIAMETER = 4.6
PD_PILOT_DIAMETER = 1.6
PD_MOUNT_START = 0.3
PD_MOUNT_END = PD_BOARD_LENGTH + 0.4
PD_GUSSET_LENGTH = 8.0
PD_GUSSET_DROP = 3.0


def shape_metrics(shape):
    bbox = shape.BoundBox
    return {
        "valid": bool(shape.isValid()),
        "solids": len(shape.Solids),
        "volume_mm3": round(shape.Volume, 6),
        "bbox_mm": [
            round(bbox.XLength, 3),
            round(bbox.YLength, 3),
            round(bbox.ZLength, 3),
        ],
    }


def restore_round_corner_relief(shape, original_middle, centre):
    """Fill the old square pocket from source material, then cut a round one."""
    cx, cy, base_z = centre
    size = CORNER_SQUARE_SIZE
    restore_box = Part.makeBox(
        size,
        size,
        12.0,
        App.Vector(cx - size / 2.0, cy - size / 2.0, base_z - 0.01),
    )
    source_patch = original_middle.common(restore_box)
    restored = shape.fuse(source_patch).removeSplitter()
    circular_relief = Part.makeCylinder(
        CORNER_RELIEF_DIAMETER / 2.0,
        12.02,
        App.Vector(cx, cy, base_z - 0.02),
        App.Vector(0, 0, 1),
    )
    return restored.cut(circular_relief).removeSplitter()


def rear_bottom_split_plug():
    counterbore = Part.makeCylinder(
        REAR_BOTTOM_COUNTERBORE_RADIUS + 0.05,
        REAR_BOTTOM_COUNTERBORE_DEPTH,
        REAR_BOTTOM_HOLE_BASE,
        REAR_HOLE_AXIS,
    )
    clearance = Part.makeCylinder(
        REAR_BOTTOM_CLEARANCE_RADIUS + 0.05,
        REAR_BOTTOM_CLEARANCE_DEPTH,
        REAR_BOTTOM_HOLE_BASE
        + REAR_HOLE_AXIS * REAR_BOTTOM_COUNTERBORE_DEPTH,
        REAR_HOLE_AXIS,
    )
    return counterbore.fuse(clearance).removeSplitter()


def fill_rear_bottom_half_hole(shape, side):
    plug = rear_bottom_split_plug()
    if side == "left":
        half_space = Part.makeBox(
            REAR_SPLIT_X + 250.0,
            500.0,
            500.0,
            App.Vector(-250.0, -250.0, -150.0),
        )
    else:
        half_space = Part.makeBox(
            500.0, 500.0, 500.0, App.Vector(REAR_SPLIT_X, -250.0, -150.0)
        )
    return shape.fuse(plug.common(half_space)).removeSplitter()


def fill_rear_middle_hole(shape):
    plug = Part.makeCylinder(
        REAR_MIDDLE_HOLE_RADIUS + 0.05,
        REAR_MIDDLE_HOLE_DEPTH,
        REAR_MIDDLE_HOLE_BASE,
        REAR_HOLE_AXIS,
    )
    return shape.fuse(plug).removeSplitter()



def oriented_box(origin, length, width, depth):
    """Parallelepiped whose local axes are PD length, width and inward normal."""
    p0 = origin
    p1 = p0 + PD_LENGTH_AXIS * length
    p2 = p1 + PD_WIDTH_AXIS * width
    p3 = p0 + PD_WIDTH_AXIS * width
    wire = Part.makePolygon([p0, p1, p2, p3, p0])
    return Part.Face(wire).extrude(PD_NORMAL_AXIS * depth)


def pd_point(length_offset, width_offset, normal_offset):
    return (
        PD_USB_EDGE_CENTRE
        + PD_LENGTH_AXIS * length_offset
        + PD_WIDTH_AXIS * width_offset
        + PD_NORMAL_AXIS * normal_offset
    )


def pd_hole_centres():
    half_spacing = PD_HOLE_ROW_SPACING / 2.0
    return [
        pd_point(PD_USB_HOLE_EDGE_OFFSET, -half_spacing, 0.0),
        pd_point(PD_USB_HOLE_EDGE_OFFSET, half_spacing, 0.0),
    ]


def isolate_old_pd_mount(shape, original_middle):
    """Return the old 41 x 15 mm mount material added inside the source shell."""
    additions = shape.cut(original_middle).removeSplitter()
    candidates = []
    for solid in additions.Solids:
        bbox = solid.BoundBox
        if (
            1500.0 < solid.Volume < 5000.0
            and bbox.XMin < -90.0
            and -55.0 < bbox.XMax < -45.0
            and -65.0 < bbox.YMin < -50.0
            and -45.0 < bbox.YMax < -30.0
            and 10.0 < bbox.ZMin < 25.0
            and 30.0 < bbox.ZMax < 45.0
        ):
            candidates.append(solid)
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one old PD mount addition, found {len(candidates)}"
        )
    return candidates[0]


def make_pd_root_gusset(width_min):
    l0 = PD_MOUNT_START
    l1 = PD_MOUNT_START + PD_GUSSET_LENGTH
    n0 = PD_MOUNT_DEPTH
    p0 = pd_point(l0, width_min, n0)
    p1 = pd_point(l0, width_min, n0 + PD_GUSSET_DROP)
    p2 = pd_point(l1, width_min, n0)
    wire = Part.makePolygon([p0, p1, p2, p0])
    return Part.Face(wire).extrude(PD_WIDTH_AXIS * PD_RAIL_THICKNESS)


def make_pd_mount():
    rail_length = PD_MOUNT_END - PD_MOUNT_START
    low_rail_w = -PD_CLEAR_WIDTH / 2.0 - PD_RAIL_THICKNESS
    high_rail_w = PD_CLEAR_WIDTH / 2.0
    shapes = [
        oriented_box(
            pd_point(PD_MOUNT_START, low_rail_w, 0.0),
            rail_length,
            PD_RAIL_THICKNESS,
            PD_MOUNT_DEPTH,
        ),
        oriented_box(
            pd_point(PD_MOUNT_START, high_rail_w, 0.0),
            rail_length,
            PD_RAIL_THICKNESS,
            PD_MOUNT_DEPTH,
        ),
        oriented_box(
            pd_point(PD_MOUNT_START, -PD_CLEAR_WIDTH / 2.0, PD_UNDERSIDE_GAP),
            rail_length,
            PD_LEDGE_WIDTH,
            PD_MOUNT_DEPTH - PD_UNDERSIDE_GAP,
        ),
        oriented_box(
            pd_point(
                PD_MOUNT_START,
                PD_CLEAR_WIDTH / 2.0 - PD_LEDGE_WIDTH,
                PD_UNDERSIDE_GAP,
            ),
            rail_length,
            PD_LEDGE_WIDTH,
            PD_MOUNT_DEPTH - PD_UNDERSIDE_GAP,
        ),
        make_pd_root_gusset(low_rail_w),
        make_pd_root_gusset(high_rail_w),
    ]

    # Raise the final 6 mm of the edge ledges to support the terminal end of
    # the PCB without putting plastic beneath the terminal pins/components.
    terminal_start = PD_BOARD_LENGTH - PD_TERMINAL_PAD_LENGTH
    terminal_pad_width = 1.2
    shapes.extend(
        [
            oriented_box(
                pd_point(terminal_start, -PD_BOARD_WIDTH / 2.0, 0.0),
                PD_TERMINAL_PAD_LENGTH,
                terminal_pad_width,
                PD_MOUNT_DEPTH,
            ),
            oriented_box(
                pd_point(
                    terminal_start,
                    PD_BOARD_WIDTH / 2.0 - terminal_pad_width,
                    0.0,
                ),
                PD_TERMINAL_PAD_LENGTH,
                terminal_pad_width,
                PD_MOUNT_DEPTH,
            ),
        ]
    )

    mount = shapes[0]
    for addition in shapes[1:]:
        mount = mount.fuse(addition)

    for centre in pd_hole_centres():
        boss = Part.makeCylinder(
            PD_BOSS_DIAMETER / 2.0,
            PD_MOUNT_DEPTH,
            centre,
            PD_NORMAL_AXIS,
        )
        mount = mount.fuse(boss)

    mount = mount.removeSplitter()
    for centre in pd_hole_centres():
        pilot = Part.makeCylinder(
            PD_PILOT_DIAMETER / 2.0,
            PD_MOUNT_DEPTH + 0.2,
            centre - PD_NORMAL_AXIS * 0.1,
            PD_NORMAL_AXIS,
        )
        mount = mount.cut(pilot)
    return mount.removeSplitter()


def rebuild_pd_mount(shape, original_middle):
    old_mount = isolate_old_pd_mount(shape, original_middle)
    cleaned = shape.cut(old_mount).removeSplitter()
    new_mount = make_pd_mount()
    rebuilt = cleaned.fuse(new_mount).removeSplitter()
    return rebuilt, old_mount, new_mount


def make_pd_board_proxy():
    origin = pd_point(
        0.0,
        -PD_BOARD_WIDTH / 2.0,
        -PD_BOARD_THICKNESS,
    )
    return oriented_box(
        origin,
        PD_BOARD_LENGTH,
        PD_BOARD_WIDTH,
        PD_BOARD_THICKNESS,
    )


def make_pd_fit_coupon():
    outer_width = PD_CLEAR_WIDTH + 2.0 * PD_RAIL_THICKNESS
    length = PD_MOUNT_END
    low_rail = Part.makeBox(
        length,
        PD_RAIL_THICKNESS,
        PD_MOUNT_DEPTH,
        App.Vector(0, 0, 0),
    )
    high_rail = Part.makeBox(
        length,
        PD_RAIL_THICKNESS,
        PD_MOUNT_DEPTH,
        App.Vector(0, PD_RAIL_THICKNESS + PD_CLEAR_WIDTH, 0),
    )
    low_ledge = Part.makeBox(
        length,
        PD_LEDGE_WIDTH,
        PD_MOUNT_DEPTH - PD_UNDERSIDE_GAP,
        App.Vector(0, PD_RAIL_THICKNESS, 0),
    )
    high_ledge = Part.makeBox(
        length,
        PD_LEDGE_WIDTH,
        PD_MOUNT_DEPTH - PD_UNDERSIDE_GAP,
        App.Vector(
            0,
            outer_width - PD_RAIL_THICKNESS - PD_LEDGE_WIDTH,
            0,
        ),
    )
    coupon = low_rail.fuse(high_rail).fuse(low_ledge).fuse(high_ledge)

    board_centre_y = PD_RAIL_THICKNESS + PD_CLEAR_WIDTH / 2.0
    half_spacing = PD_HOLE_ROW_SPACING / 2.0
    coupon_centres = [
        App.Vector(PD_USB_HOLE_EDGE_OFFSET, board_centre_y - half_spacing, 0),
        App.Vector(PD_USB_HOLE_EDGE_OFFSET, board_centre_y + half_spacing, 0),
    ]
    for centre in coupon_centres:
        coupon = coupon.fuse(
            Part.makeCylinder(PD_BOSS_DIAMETER / 2.0, PD_MOUNT_DEPTH, centre)
        )

    # A low bridge makes the coupon one printable solid while remaining
    # 2.5 mm below the PCB underside.
    bridge = Part.makeBox(
        5.4,
        PD_HOLE_ROW_SPACING,
        0.8,
        App.Vector(
            PD_USB_HOLE_EDGE_OFFSET - 2.7,
            board_centre_y - half_spacing,
            0,
        ),
    )
    coupon = coupon.fuse(bridge)

    terminal_start = PD_BOARD_LENGTH - PD_TERMINAL_PAD_LENGTH
    board_y_min = PD_RAIL_THICKNESS + PD_CLEARANCE_EACH_SIDE
    terminal_pad_width = 1.2
    coupon = coupon.fuse(
        Part.makeBox(
            PD_TERMINAL_PAD_LENGTH,
            terminal_pad_width,
            PD_MOUNT_DEPTH,
            App.Vector(terminal_start, board_y_min, 0),
        )
    )
    coupon = coupon.fuse(
        Part.makeBox(
            PD_TERMINAL_PAD_LENGTH,
            terminal_pad_width,
            PD_MOUNT_DEPTH,
            App.Vector(
                terminal_start,
                board_y_min + PD_BOARD_WIDTH - terminal_pad_width,
                0,
            ),
        )
    )

    coupon = coupon.removeSplitter()
    for centre in coupon_centres:
        coupon = coupon.cut(
            Part.makeCylinder(
                PD_PILOT_DIAMETER / 2.0,
                PD_MOUNT_DEPTH + 0.2,
                centre - App.Vector(0, 0, 0.1),
            )
        )
    return coupon.removeSplitter()

def update_assembly_and_print(doc, key, shape):
    assembly = doc.getObject(f"{key}_assembly")
    printable = doc.getObject(f"{key}_print")
    if assembly is None or printable is None:
        raise RuntimeError(f"Missing v17 objects for {key}")
    old_print_placement = printable.Placement.copy()
    assembly.Shape = shape
    printable.Shape = shape.copy()
    printable.Placement = old_print_placement


def export_step_shape(shape, label, path):
    temp_doc = App.newDocument("v18_step_export")
    obj = temp_doc.addObject("Part::Feature", "ExportShape")
    obj.Label = label
    obj.Shape = shape
    Import.export([obj], path)
    App.closeDocument(temp_doc.Name)


def export_stl_object(doc, object_name, path):
    obj = doc.getObject(object_name)
    if obj is None:
        raise RuntimeError(f"Missing printable object: {object_name}")
    temp_doc = App.newDocument("v18_stl_export")
    export_obj = temp_doc.addObject("Part::Feature", "ExportShape")
    export_obj.Shape = obj.Shape.copy()
    export_obj.Placement = obj.Placement.copy()
    Mesh.export([export_obj], path)
    App.closeDocument(temp_doc.Name)
    mesh = Mesh.Mesh(path)
    if abs(mesh.BoundBox.ZMin) > 1e-6:
        mesh.translate(0.0, 0.0, -mesh.BoundBox.ZMin)
        mesh.write(path)


def prepare_output_tree():
    if os.path.exists(OUTPUT_ROOT):
        raise RuntimeError(f"Refusing to overwrite existing output: {OUTPUT_ROOT}")
    os.makedirs(OUTPUT_ROOT)
    os.makedirs(STEP_DIR)
    os.makedirs(STL_DIR)
    shutil.copy2(SOURCE_FCSTD, OUTPUT_FCSTD)


def main():
    if PD_HOLE_DIAMETER is None or PD_HOLE_CENTRES_LOCAL is None:
        raise RuntimeError("Enter the measured PD mounting-hole layout before building v18")

    prepare_output_tree()
    doc = App.openDocument(OUTPUT_FCSTD)
    original_middle = Part.read(ORIGINAL_STEP).Solids[1]

    modified = {}
    for key, centre in CORNER_POCKET_BASES.items():
        old_shape = doc.getObject(f"{key}_assembly").Shape.copy()
        new_shape = restore_round_corner_relief(old_shape, original_middle, centre)
        modified[key] = new_shape
        update_assembly_and_print(doc, key, new_shape)

    for side in ("left", "right"):
        key = f"bottom_rear_{side}"
        old_shape = doc.getObject(f"{key}_assembly").Shape.copy()
        new_shape = fill_rear_bottom_half_hole(old_shape, side)
        modified[key] = new_shape
        update_assembly_and_print(doc, key, new_shape)

    # The corresponding unused frame bore belongs to the rear-right section.
    key = "middle_rear_right"
    new_shape = fill_rear_middle_hole(modified[key])
    modified[key] = new_shape
    update_assembly_and_print(doc, key, new_shape)

    # PD mount rebuild is added after the remaining physical measurements are
    # available.  Keeping this guard here prevents an incomplete package.
    raise RuntimeError("PD mount rebuild pending measured hole/component layout")


if __name__ == "__main__":
    main()

