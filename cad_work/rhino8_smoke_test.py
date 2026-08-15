import json
import os

import Rhino
import scriptcontext as sc


OUT_DIR = r"C:\Users\brian\ed-finder\cad_work\rhino8_smoke_output"
os.makedirs(OUT_DIR, exist_ok=True)

sc.doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
sc.doc.ModelAbsoluteTolerance = 0.01

box = Rhino.Geometry.Box(
    Rhino.Geometry.Plane.WorldXY,
    Rhino.Geometry.Interval(0.0, 20.0),
    Rhino.Geometry.Interval(0.0, 15.0),
    Rhino.Geometry.Interval(0.0, 8.0),
).ToBrep()
object_id = sc.doc.Objects.AddBrep(box)
sc.doc.Objects.Select(object_id)
sc.doc.Views.Redraw()

three_dm = os.path.join(OUT_DIR, "rhino8_smoke.3dm")
step_path = os.path.join(OUT_DIR, "rhino8_smoke.step")
stl_path = os.path.join(OUT_DIR, "rhino8_smoke.stl")
report_path = os.path.join(OUT_DIR, "rhino8_smoke_report.json")

sc.doc.WriteFile(three_dm, Rhino.FileIO.FileWriteOptions())
Rhino.RhinoApp.RunScript('-_Export "{}" _Enter'.format(step_path), False)
sc.doc.Objects.Select(object_id)
Rhino.RhinoApp.RunScript('-_Export "{}" _Enter _DetailedOptions _Enter _Enter'.format(stl_path), False)

report = {
    "rhino_version": Rhino.RhinoApp.Version.ToString(),
    "unit_system": str(sc.doc.ModelUnitSystem),
    "absolute_tolerance_mm": sc.doc.ModelAbsoluteTolerance,
    "brep_is_valid": box.IsValid,
    "brep_is_solid": box.IsSolid,
    "volume_mm3": Rhino.Geometry.VolumeMassProperties.Compute(box).Volume,
    "three_dm_exists": os.path.exists(three_dm),
    "step_exists": os.path.exists(step_path),
    "stl_exists": os.path.exists(stl_path),
}
with open(report_path, "w", encoding="utf-8") as stream:
    json.dump(report, stream, indent=2)

Rhino.RhinoApp.Exit()
