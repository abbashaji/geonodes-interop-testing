"""
Cell: usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2
Script version: v2 (v1 crashed in build_scene() before any assertion ran --
see HARNESS NOTES: geometry_node_bake_single requires view_layer.objects.active
set BEFORE the bake call, not just a window/screen temp_override. Fixed here.)

Question this cell answers (verified directly from the crashed v1 script's own
CONFIG block, per this session's harness-note lookup):
  usd_export__animated_rotation__bake_combined__production_scale confirmed the
  `orientations` PointInstancer attribute drops its start/end boundary frames
  and returns a stale first sample at 20,000-instance scale. The single-
  padding-frame fix that already resolves this for `positions`/`scales` at
  the same scale (usd_export__animated_position__bake_combined__production_scale,
  usd_export__animated_scale__bake_combined__production_scale) is CONFIRMED
  NOT sufficient for `orientations`.

  v1 attempted a *flat, double-sided padding* fix (identical held value across
  multiple padding frames on each side) -- it crashed before running, so that
  approach remains untested, not refuted.

  v2 (this script) attempts a DIFFERENT fix: inject genuine, distinct non-zero
  rotation deltas at every padding frame instead of a flat held value, so no
  two adjacent requested frames share an identical sampled value anywhere in
  the range. This directly targets the root-cause hypothesis from the sibling
  cell usd_export__animated_rotation__orientations_defect__wide_range_padding_attempt:
  the defect is anchored to wherever Blender's exporter internally decides the
  curve's "active/changing window" is, so a flat-held padding frame still
  reads as unchanging to that internal trim logic -- a non-flat padding frame
  should not.

Traces to: geonodes_export_interop_gap.md source #2 (#139654) + source #7
(#132123, Bake node) + sources #11/#15 (production-scale instance counts).
"""

import bpy
import os
import sys
import json
import math

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2",
    "script_version": "v2",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (#139654) + source #7 (#132123) "
        "+ sources #11/#15 -- fix-attempt follow-up to "
        "usd_export__animated_rotation__bake_combined__production_scale (CONFIRMED "
        "BROKEN: orientations drops boundary frames + stale first sample at 20,000 "
        "instances). v2 fix under test: non-flat micro-motion padding instead of "
        "v1's flat double-padding (which crashed before any assertion ran)."
    ),

    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "instance_count": 20000,          # exact, via grid-of-verts Mesh to Points convention

    "float_tolerance": 1e-4,
    "angle_tolerance_deg": 1e-3,

    "output_path": "/tmp/gn_interop_scale_fix_attempt_v2_v2",
    "bake_directory": "/tmp/gn_interop_scale_fix_attempt_v2_v2_bake",

    "fix_attempt": "nonflat_micro_motion_padding",
    # Explicit keyframes (frame -> rotation_z in degrees). Every value distinct --
    # no two adjacent frames share an identical sampled value anywhere in range.
    "keyframes_deg": {
        3: -0.002,   # padding (pre-motion) -- expected to be dropped by wm.usd_export's
                     # own documented "always drops the first requested frame" behavior;
                     # kept in the timeline anyway so frame 4 has a real non-flat neighbor.
        4: -0.001,   # padding (pre-motion), first frame actually expected to survive export
        5: 0.0,      # REAL motion start
        24: 90.0,    # REAL motion end
        25: 90.001,  # padding (post-motion)
    },
    "export_frame_start": 3,
    "export_frame_end": 25,
    "real_start_frame": 5,
    "real_end_frame": 24,
}


# =====================================================================
# VERSION STAMP
# =====================================================================
def log_version_stamp():
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": CONFIG["cell_id"],
        "script_version": CONFIG["script_version"],
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, separators=(",", ":")))
    return stamp


# =====================================================================
# BUILD -- exact-count grid (Mesh to Points) -> Object Info(As Instance) ->
# Instance on Points -> Bake (DISK) -> Instances to Points -> second
# Object Info(As Instance) -> Instance on Points, with Rotation keyframed
# on the second Instance-on-Points node's own Rotation input.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # --- Exact-count source grid: 200 x 100 = 20,000 vertices exactly ---
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=200, y_subdivisions=100, size=50)
    source = bpy.context.active_object
    source.name = "GN_Source_Grid"
    n_verts = len(source.data.vertices)
    assert n_verts == CONFIG["instance_count"], (
        f"Grid vertex count mismatch: got {n_verts}, expected {CONFIG['instance_count']}"
    )

    # --- Prototype: an 8-vertex cube, single prototype (matches the already-
    # confirmed single-prototype threshold_bisection/production_scale family) ---
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 5))
    proto = bpy.context.active_object
    proto.name = "ProtoCube"
    proto.hide_render = True
    proto.hide_viewport = False  # must stay evaluable by Object Info even if visually hidden

    bpy.context.view_layer.objects.active = source
    mod = source.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_ScaleFixV2", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n_in = ng.nodes.new("NodeGroupInput")
    n_out = ng.nodes.new("NodeGroupOutput")
    n_in.location = (-1400, 0)
    n_out.location = (1400, 0)

    # Mesh to Points (VERTS domain) -> exact 20,000 points
    n_m2p = ng.nodes.new("GeometryNodeMeshToPoints")
    n_m2p.mode = 'VERTICES'
    n_m2p.location = (-1100, 0)
    ng.links.new(n_in.outputs["Geometry"], n_m2p.inputs["Mesh"])

    # First Object Info(As Instance) -> Instance on Points
    n_objinfo1 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo1.inputs["Object"].default_value = proto
    n_objinfo1.inputs["As Instance"].default_value = True  # NOT default -- must set explicitly
    n_objinfo1.location = (-1100, -300)

    n_iop1 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_iop1.location = (-800, 0)
    ng.links.new(n_m2p.outputs["Points"], n_iop1.inputs["Points"])
    ng.links.new(n_objinfo1.outputs["Geometry"], n_iop1.inputs["Instance"])

    # Bake node -- must add a Geometry bake item explicitly before wiring
    n_bake = ng.nodes.new("GeometryNodeBake")
    n_bake.bake_items.new(socket_type="GEOMETRY", name="Geometry")
    n_bake.location = (-500, 0)
    ng.links.new(n_iop1.outputs["Instances"], n_bake.inputs["Geometry"])

    # Instances to Points (bake recovery chain)
    n_i2p = ng.nodes.new("GeometryNodeInstancesToPoints")
    n_i2p.location = (-200, 0)
    ng.links.new(n_bake.outputs["Geometry"], n_i2p.inputs["Instances"])

    # Second Object Info(As Instance) -> Instance on Points (this is where
    # Rotation gets keyframed)
    n_objinfo2 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo2.inputs["Object"].default_value = proto
    n_objinfo2.inputs["As Instance"].default_value = True  # again -- both need it
    n_objinfo2.location = (-200, -300)

    n_iop2 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_iop2.location = (200, 0)
    ng.links.new(n_i2p.outputs["Points"], n_iop2.inputs["Points"])
    ng.links.new(n_objinfo2.outputs["Geometry"], n_iop2.inputs["Instance"])

    ng.links.new(n_iop2.outputs["Instances"], n_out.inputs["Geometry"])

    # --- Keyframe Rotation directly on n_iop2's Rotation input socket ---
    rot_socket = n_iop2.inputs["Rotation"]
    for frame, deg in CONFIG["keyframes_deg"].items():
        rot_socket.default_value = (0.0, 0.0, math.radians(deg))
        rot_socket.keyframe_insert(data_path="default_value", frame=frame)

    # --- Trigger the bake, with BOTH required fixes from harness notes ---
    # (1) view_layer.objects.active + selection set BEFORE the bake call --
    #     this is what v1 was missing and what crashed it.
    bpy.context.view_layer.objects.active = source
    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)

    # (2) modifier-level bake_target/bake_directory (NOT per-bake-item .directory,
    #     which silently fails to route to disk per harness notes)
    mod.bake_target = 'DISK'
    mod.bake_directory = CONFIG["bake_directory"]
    bpy.context.view_layer.update()

    bake_id = mod.bakes[0].bake_id
    bpy.ops.object.geometry_node_bake_single(
        session_uid=source.session_uid,
        modifier_name=mod.name,
        bake_id=bake_id,
    )

    # Verify disk bake actually landed on disk (not silently falling back to
    # packed) -- per harness notes, a FINISHED result alone doesn't confirm this.
    meta_dir = os.path.join(CONFIG["bake_directory"], "meta")
    disk_bake_confirmed = os.path.isdir(meta_dir) and len(os.listdir(meta_dir)) > 0

    return source, proto, {"disk_bake_confirmed": disk_bake_confirmed, "meta_dir": meta_dir}


# =====================================================================
# EXPORT (no reimport -- direct pxr.Usd inspection, matching how this
# defect family has been tested on every prior sibling cell; the real-
# world failure mode is "our pipeline is built around USD" reading the
# raw file, not necessarily Blender reimport)
# =====================================================================
def export_cell(obj):
    scene = bpy.context.scene
    scene.frame_start = CONFIG["export_frame_start"]
    scene.frame_end = CONFIG["export_frame_end"]

    out_path = f"{CONFIG['output_path']}.usdc"

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.wm.usd_export(
        filepath=out_path,
        selected_objects_only=True,
        export_animation=True,
        use_instancing=True,  # unenumerated but critical -- default False writes no PointInstancer
    )
    return out_path


# =====================================================================
# ASSERTIONS -- direct pxr.Usd inspection of the exported file
# =====================================================================
def run_assertions(out_path, bake_info):
    from pxr import Usd, UsdGeom

    results = {}
    tol = CONFIG["float_tolerance"]
    ang_tol = math.radians(CONFIG["angle_tolerance_deg"])

    stage = Usd.Stage.Open(out_path)

    instancer = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer = UsdGeom.PointInstancer(prim)
            break

    if instancer is None:
        results["count_match"] = {"pass": False, "detail": "No PointInstancer prim found in exported stage."}
        results["prototype_match"] = {"pass": False, "detail": "No PointInstancer prim found."}
        results["transform_match"] = {"pass": False, "detail": "No PointInstancer prim found."}
        results["attribute_match"] = {"pass": None, "detail": "N/A for this cell -- no custom attributes under test."}
        return results

    # --- Count match ---
    proto_indices_attr = instancer.GetProtoIndicesAttr()
    positions_attr = instancer.GetPositionsAttr()
    proto_indices = proto_indices_attr.Get(Usd.TimeCode.EarliestTime())
    positions = positions_attr.Get(Usd.TimeCode.EarliestTime())
    n_proto_idx = len(proto_indices) if proto_indices else 0
    n_pos = len(positions) if positions else 0
    results["count_match"] = {
        "pass": (n_proto_idx == CONFIG["instance_count"] and n_pos == CONFIG["instance_count"]),
        "detail": f"protoIndices={n_proto_idx}, positions={n_pos}, expected={CONFIG['instance_count']}",
    }

    # --- Prototype resolution (single prototype, resolve via IsInstance()
    # -> GetPrototype(), fall back to direct child-Mesh search) ---
    proto_targets = instancer.GetPrototypesRel().GetTargets()
    proto_ok = False
    proto_detail = f"targets={proto_targets}"
    if proto_targets:
        proto_prim = stage.GetPrimAtPath(proto_targets[0])
        resolved_mesh = None
        if proto_prim.IsInstance():
            resolved_mesh = proto_prim.GetPrototype()
        if resolved_mesh is None or not resolved_mesh:
            for child in Usd.PrimRange(proto_prim):
                if child.IsA(UsdGeom.Mesh):
                    resolved_mesh = child
                    break
        if resolved_mesh:
            mesh_geom = UsdGeom.Mesh(resolved_mesh)
            pts = mesh_geom.GetPointsAttr().Get()
            n_proto_verts = len(pts) if pts else 0
            proto_ok = (n_proto_verts == 8)  # ProtoCube is an 8-vertex cube
            proto_detail = f"resolved prototype vertex count={n_proto_verts} (expected 8)"
    results["prototype_match"] = {"pass": proto_ok, "detail": proto_detail}

    # --- Transform match: orientations boundary-recovery (the actual
    # question this cell exists to answer) ---
    orientations_attr = instancer.GetOrientationsAttr()
    time_samples = list(orientations_attr.GetTimeSamples()) if orientations_attr else []

    real_start = float(CONFIG["real_start_frame"])
    real_end = float(CONFIG["real_end_frame"])

    boundary_present = (real_start in time_samples) and (real_end in time_samples)

    # Value accuracy at every explicitly-keyframed frame that is present
    # in the exported time samples (skip 3.0 -- documented as always
    # dropped as the first requested frame, independent of our fix).
    def expected_quat_deg(deg):
        # Build the same quaternion Blender would from a Z-axis Euler,
        # for comparison against the exported orientations sample.
        import mathutils
        return mathutils.Euler((0.0, 0.0, math.radians(deg)), 'XYZ').to_quaternion()

    value_checks = {}
    for frame, deg in CONFIG["keyframes_deg"].items():
        f = float(frame)
        if f not in time_samples:
            value_checks[frame] = {"present": False}
            continue
        sample = orientations_attr.Get(f)
        got = sample[0] if sample else None
        expected = expected_quat_deg(deg)
        if got is None:
            value_checks[frame] = {"present": True, "pass": False, "detail": "sample is None"}
            continue
        # pxr quatf: compare real+imaginary components within tolerance
        got_vec = (got.GetReal(), *got.GetImaginary())
        exp_vec = (expected.w, expected.x, expected.y, expected.z)
        diff = max(abs(a - b) for a, b in zip(got_vec, exp_vec))
        value_checks[frame] = {"present": True, "pass": diff <= max(tol, ang_tol), "diff": diff}

    # Stale-adjacent-sample check: any two consecutive samples in the
    # present time-sample list must NOT be byte-identical (this was the
    # signature of the original defect -- a "stale" first sample equal to
    # its predecessor's value).
    stale_adjacent_found = False
    stale_detail = "n/a"
    sorted_samples = sorted(time_samples)
    for i in range(1, len(sorted_samples)):
        a = orientations_attr.Get(sorted_samples[i - 1])
        b = orientations_attr.Get(sorted_samples[i])
        if a and b:
            a0, b0 = a[0], b[0]
            if (a0.GetReal(), *a0.GetImaginary()) == (b0.GetReal(), *b0.GetImaginary()):
                stale_adjacent_found = True
                stale_detail = f"frames {sorted_samples[i-1]} and {sorted_samples[i]} identical"
                break

    transform_pass = (
        boundary_present
        and all(v.get("pass", False) for v in value_checks.values() if v.get("present"))
        and not stale_adjacent_found
    )

    results["transform_match"] = {
        "pass": transform_pass,
        "detail": (
            f"time_samples={sorted_samples}, "
            f"boundary_present(start={real_start},end={real_end})={boundary_present}, "
            f"value_checks={value_checks}, "
            f"stale_adjacent_found={stale_adjacent_found} ({stale_detail})"
        ),
    }

    # --- Attribute match: not applicable for this cell (no custom
    # point/face/instance attributes under test -- the defect under test
    # IS the orientations attribute itself, covered by transform_match) ---
    results["attribute_match"] = {
        "pass": None,
        "detail": "N/A for this cell -- orientations boundary defect is covered under transform_match; no separate custom attribute is under test here.",
    }

    results["_bake_diagnostics"] = bake_info

    return results


# =====================================================================
# REPORT
# =====================================================================
def report(stamp, config, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, separators=(",", ":"), default=str))


def main():
    stamp = log_version_stamp()
    try:
        obj, proto, bake_info = build_scene()
        out_path = export_cell(obj)
        results = run_assertions(out_path, bake_info)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
