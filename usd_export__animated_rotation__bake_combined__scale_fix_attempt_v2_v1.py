"""
Cell: usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2
Script version: v1

Fix-attempt follow-up to usd_export__animated_rotation__bake_combined__
production_scale (CONFIRMED BROKEN, Blender 5.0.1): at 20,000-instance
production scale, the PointInstancer's `orientations` time-sampled
attribute drops THREE boundary frames -- the single padding frame (4),
the real start (5), AND the real end (24) -- unlike `positions`/`scales`,
which only ever needed the single-padding-frame fix already proven at
small scale. This attempt widens the padding on both ends: two padding
frames at the start (3 and 4, both holding the frame-5 value) and one
padding frame past the end (25, holding the frame-24 value), with the
export range widened to match (3..25 instead of 4..24).

Hypothesis: if the boundary-drop is a fixed N-samples-from-each-edge
artifact rather than a single-frame artifact for this attribute
specifically, padding by 2 at the start should recover frame 5, and
padding by 1 past the end should recover frame 24. This is a genuine
unknown -- prior notes never tested asymmetric/wider padding for
`orientations` specifically, only ever the single-frame scheme that
already works for positions/scales.
"""

import bpy
import os
import sys
import json
import math
import tempfile

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (issue #139654, production "
        "USD pipeline) + source #14 (issue #132123, baking for performance) + "
        "sources #11/#15 (production-scale instance counts) -- fix-attempt "
        "follow-up to usd_export__animated_rotation__bake_combined__"
        "production_scale (CONFIRMED BROKEN: orientations attribute drops "
        "padding/start/end boundary frames at 20,000-instance scale; the "
        "single-padding-frame fix that resolves positions/scales at this "
        "scale is confirmed NOT sufficient for orientations)."
    ),

    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "instance_count": 20000,

    "float_tolerance": 1e-4,   # degrees, for rotation comparisons
    "output_path": os.path.join(tempfile.gettempdir(), "gn_interop_scale_fix_attempt_v2"),

    # --- the actual fix attempt under test ---
    "fix_attempt": "double_start_padding_plus_end_padding",
    "pad_start_frames": [3, 4],   # both hold the frame-5 (real start) value
    "real_start_frame": 5,
    "real_end_frame": 24,
    "pad_end_frames": [25],       # holds the frame-24 (real end) value
    "export_frame_start": 3,
    "export_frame_end": 25,

    "bake_directory": os.path.join(tempfile.gettempdir(), "gn_interop_scale_fix_attempt_v2_bake"),
}

TRUE_ROTATION_CURVE_DEG = {
    # authored curve, degrees around Z, sampled at frames of interest.
    # padding frames hold the boundary value exactly (constant extension).
    3: 0.0,
    4: 0.0,
    5: 0.0,
    6: 0.7217,
    7: 2.7817,
    10: 15.4177,
    15: 48.5494,
    24: 90.0000,
    25: 90.0000,
}


# =====================================================================
# VERSION STAMP
# =====================================================================
def log_version_stamp():
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": CONFIG["cell_id"],
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, separators=(",", ":")))
    return stamp


# =====================================================================
# BUILD -- Mesh to Points -> Object Info(As Instance) -> Instance on
# Points -> Bake (real, DISK target) -> Instances to Points -> Object
# Info(As Instance) -> Instance on Points, Rotation keyframed on this
# second node with the widened padding scheme.
# =====================================================================
def build_prototype():
    """A minimal real prototype: an 8-vertex cube, kept OUT of the
    exported collection's render path except via Object Info reference,
    matching the pattern already confirmed working in prior cells."""
    mesh = bpy.data.meshes.new("ProtoCube_mesh")
    bm_verts = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    ]
    bm_faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh.from_pydata(bm_verts, [], bm_faces)
    mesh.update()
    proto = bpy.data.objects.new("ProtoCube", mesh)
    bpy.context.collection.objects.link(proto)
    proto.hide_render = True
    proto.hide_viewport = False  # Object Info can still reference it either way; kept visible for build-time inspection
    return proto


def build_base_grid(count):
    """Base mesh with an EXACT `count` loose vertices, laid out on a
    grid -- avoids relying on Distribute Points on Faces' density-based
    approximate count, matching the production_scale cell's convention
    (which the isolation cell confirmed is not itself the cause of the
    defect -- scale is)."""
    side = math.ceil(math.sqrt(count))
    verts = []
    i = 0
    for y in range(side):
        for x in range(side):
            if i >= count:
                break
            verts.append((x * 1.5, y * 1.5, 0.0))
            i += 1
        if i >= count:
            break
    mesh = bpy.data.meshes.new("GN_Source_mesh")
    mesh.from_pydata(verts, [], [])
    mesh.update()
    assert len(mesh.vertices) == count, f"grid build produced {len(mesh.vertices)}, expected {count}"
    return mesh


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    proto = build_prototype()

    base_mesh = build_base_grid(CONFIG["instance_count"])
    base = bpy.data.objects.new("GN_Source", base_mesh)
    bpy.context.collection.objects.link(base)

    mod = base.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_ScaleFixAttemptV2", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes = ng.nodes
    links = ng.links

    n_in = nodes.new("NodeGroupInput")
    n_out = nodes.new("NodeGroupOutput")

    n_mesh_to_points = nodes.new("GeometryNodeMeshToPoints")

    n_objinfo1 = nodes.new("GeometryNodeObjectInfo")
    n_objinfo1.inputs["Object"].default_value = proto
    n_objinfo1.transform_space = "RELATIVE"
    # "As Instance" -- check the actual socket rather than assume, per
    # the harness note on never trusting a socket name string blind.
    assert "As Instance" in n_objinfo1.inputs.keys(), list(n_objinfo1.inputs.keys())
    n_objinfo1.inputs["As Instance"].default_value = True

    n_iop1 = nodes.new("GeometryNodeInstanceOnPoints")

    # --- Bake node ---
    n_bake = nodes.new("GeometryNodeBake")
    assert len(n_bake.bake_items) == 0, "expected a fresh Bake node with no default items"
    n_bake.bake_items.new("GEOMETRY", "Geometry")
    assert "Geometry" in n_bake.inputs.keys() and "Geometry" in n_bake.outputs.keys(), (
        list(n_bake.inputs.keys()), list(n_bake.outputs.keys())
    )

    n_instances_to_points = nodes.new("GeometryNodeInstancesToPoints")

    n_objinfo2 = nodes.new("GeometryNodeObjectInfo")
    n_objinfo2.inputs["Object"].default_value = proto
    n_objinfo2.transform_space = "RELATIVE"
    n_objinfo2.inputs["As Instance"].default_value = True

    n_iop2 = nodes.new("GeometryNodeInstanceOnPoints")

    links.new(n_in.outputs["Geometry"], n_mesh_to_points.inputs["Mesh"])
    links.new(n_mesh_to_points.outputs["Points"], n_iop1.inputs["Points"])
    links.new(n_objinfo1.outputs["Geometry"], n_iop1.inputs["Instance"])
    links.new(n_iop1.outputs["Instances"], n_bake.inputs["Geometry"])
    links.new(n_bake.outputs["Geometry"], n_instances_to_points.inputs["Instances"])
    links.new(n_instances_to_points.outputs["Points"], n_iop2.inputs["Points"])
    links.new(n_objinfo2.outputs["Geometry"], n_iop2.inputs["Instance"])
    links.new(n_iop2.outputs["Instances"], n_out.inputs["Geometry"])

    # --- Rotation keyframes on the SECOND Instance on Points node,
    # widened padding scheme (this is the fix attempt itself) ---
    rot_input = n_iop2.inputs["Rotation"]

    def keyframe_rot_z(frame, degrees):
        rot_input.default_value = (0.0, 0.0, math.radians(degrees))
        rot_input.keyframe_insert(data_path="default_value", frame=frame)

    for f in CONFIG["pad_start_frames"]:
        keyframe_rot_z(f, TRUE_ROTATION_CURVE_DEG[CONFIG["real_start_frame"]])
    keyframe_rot_z(CONFIG["real_start_frame"], TRUE_ROTATION_CURVE_DEG[CONFIG["real_start_frame"]])
    keyframe_rot_z(CONFIG["real_end_frame"], TRUE_ROTATION_CURVE_DEG[CONFIG["real_end_frame"]])
    for f in CONFIG["pad_end_frames"]:
        keyframe_rot_z(f, TRUE_ROTATION_CURVE_DEG[CONFIG["real_end_frame"]])

    bpy.context.scene.frame_start = CONFIG["export_frame_start"]
    bpy.context.scene.frame_end = CONFIG["export_frame_end"]

    # --- Trigger the real bake, DISK target only (PACKED confirmed
    # unreliable per harness notes) ---
    os.makedirs(CONFIG["bake_directory"], exist_ok=True)
    mod.bake_directory = CONFIG["bake_directory"]
    mod.bake_target = "DISK"

    bake_entry = None
    for b in mod.bakes:
        if b.node == n_bake:
            bake_entry = b
            break
    assert bake_entry is not None, "could not find modifier.bakes entry for the Bake node"
    bake_id = bake_entry.bake_id

    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win, screen=win.screen):
        bpy.ops.object.geometry_node_bake_single(
            session_uid=base.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )

    # Verify the bake actually produced real on-disk data -- a
    # {'FINISHED'} return alone is not sufficient evidence, per harness notes.
    bake_subdir = os.path.join(CONFIG["bake_directory"], str(bake_id))
    meta_files = []
    if os.path.isdir(bake_subdir):
        for root, _, files in os.walk(bake_subdir):
            for fn in files:
                if fn.endswith(".json"):
                    meta_files.append(os.path.join(root, fn))
    assert meta_files, f"no bake meta JSON found under {bake_subdir} -- bake did not actually produce disk data"
    with open(meta_files[0]) as fh:
        bake_meta = json.load(fh)

    return base, proto, bake_meta


# =====================================================================
# EXPORT + REIMPORT
# =====================================================================
def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.usdc"

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win, screen=win.screen):
        result = bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            export_animation=True,
            use_instancing=True,
        )
    assert result == {"FINISHED"}, result
    return out_path


def reimport_cell(path):
    before = set(bpy.data.objects.keys())
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win, screen=win.screen):
        bpy.ops.wm.usd_import(filepath=path)
    after = set(bpy.data.objects.keys())
    new_names = after - before
    return [bpy.data.objects[n] for n in new_names]


# =====================================================================
# ASSERTIONS
# =====================================================================
def run_assertions(source_obj, proto_obj, bake_meta, reimported_objs, usd_path):
    from pxr import Usd, UsdGeom  # available inside Blender's bundled USD

    results = {}
    tol_deg = CONFIG["float_tolerance"]

    # --- Bake sanity (not a fidelity assertion, but must be true for the
    # rest of the run to mean anything) ---
    results["bake_disk_cache_real"] = {
        "pass": bool(bake_meta) and bake_meta.get("instances", bake_meta.get("count", 0)) != 0,
        "detail": f"bake meta: {bake_meta}",
    }

    stage = Usd.Stage.Open(usd_path)
    instancer_prim = None
    for p in stage.Traverse():
        if p.IsA(UsdGeom.PointInstancer):
            instancer_prim = p
            break

    results["structural_pointinstancer_found"] = {
        "pass": instancer_prim is not None,
        "detail": str(instancer_prim.GetPath()) if instancer_prim else "no PointInstancer prim found",
    }
    if instancer_prim is None:
        results["count_match"] = {"pass": False, "detail": "no PointInstancer, cannot check count"}
        results["prototype_match"] = {"pass": False, "detail": "no PointInstancer, cannot check prototype"}
        results["transform_match"] = {"pass": False, "detail": "no PointInstancer, cannot check orientations"}
        return results

    instancer = UsdGeom.PointInstancer(instancer_prim)

    # --- Count match ---
    proto_indices_attr = instancer.GetProtoIndicesAttr()
    proto_indices = proto_indices_attr.Get()
    positions = instancer.GetPositionsAttr().Get()
    n_expected = CONFIG["instance_count"]
    n_actual = len(proto_indices) if proto_indices else 0
    results["count_match"] = {
        "pass": n_actual == n_expected and len(positions) == n_expected,
        "detail": f"expected={n_expected}, protoIndices={n_actual}, positions={len(positions) if positions else 0}",
    }

    # --- Prototype resolution -- try native-instance path first, then
    # the typeless-but-populated fallback, per harness notes ---
    prototypes = instancer.GetPrototypesRel().GetTargets()
    proto_vert_count = None
    proto_resolution_path = None
    if prototypes:
        proto_prim = stage.GetPrimAtPath(prototypes[0])
        if proto_prim.IsInstance():
            real_proto = proto_prim.GetPrototype()
            mesh_children = [c for c in real_proto.GetChildren() if UsdGeom.Mesh(c)]
            if mesh_children:
                proto_resolution_path = "native_instance"
                proto_vert_count = len(UsdGeom.Mesh(mesh_children[0]).GetPointsAttr().Get() or [])
        if proto_vert_count is None:
            mesh_children = [c for c in proto_prim.GetChildren() if UsdGeom.Mesh(c)]
            if mesh_children:
                proto_resolution_path = "typeless_populated_child"
                proto_vert_count = len(UsdGeom.Mesh(mesh_children[0]).GetPointsAttr().Get() or [])

    results["prototype_match"] = {
        "pass": proto_vert_count == 8,
        "detail": f"resolution_path={proto_resolution_path}, vert_count={proto_vert_count} (expected 8, real Cube, not a stub)",
    }

    # --- Transform match -- the actual point of this cell ---
    orientations_attr = instancer.GetOrientationsAttr()
    time_samples = sorted(orientations_attr.GetTimeSamples()) if orientations_attr else []
    requested_range = list(range(CONFIG["export_frame_start"], CONFIG["export_frame_end"] + 1))
    missing_frames = [f for f in requested_range if float(f) not in time_samples]

    real_boundary_frames = [CONFIG["real_start_frame"], CONFIG["real_end_frame"]]
    real_boundaries_present = [f for f in real_boundary_frames if float(f) in time_samples]
    real_boundaries_missing = [f for f in real_boundary_frames if float(f) not in time_samples]

    per_frame_check = {}
    import mathutils
    for f in [CONFIG["real_start_frame"], 6, 7, 10, 15, CONFIG["real_end_frame"]]:
        true_deg = TRUE_ROTATION_CURVE_DEG.get(f)
        quat = orientations_attr.Get(float(f))
        if quat is None:
            per_frame_check[f] = {"pass": False, "detail": "Get() returned None"}
            continue
        # pxr Quatf -> approximate Z-rotation degrees for comparison
        q = mathutils.Quaternion((quat.real, quat.imaginary[0], quat.imaginary[1], quat.imaginary[2]))
        got_deg = math.degrees(q.to_euler().z)
        per_frame_check[f] = {
            "pass": abs(got_deg - true_deg) <= tol_deg,
            "true_deg": true_deg,
            "got_deg": got_deg,
        }

    results["transform_match"] = {
        "pass": (not missing_frames) and all(v["pass"] for v in per_frame_check.values()),
        "detail": {
            "orientations_time_samples": time_samples,
            "requested_range": [requested_range[0], requested_range[-1]],
            "missing_frames_from_requested_range": missing_frames,
            "real_boundary_frames_present": real_boundaries_present,
            "real_boundary_frames_missing": real_boundaries_missing,
            "per_frame_check": per_frame_check,
            "fix_attempt": CONFIG["fix_attempt"],
        },
    }

    # --- Attribute-value match: not applicable to this cell (no custom
    # point attributes carried beyond transform) ---
    results["attribute_match"] = {"pass": None, "detail": "not applicable to this cell -- no custom attributes tested"}

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
        obj, proto, bake_meta = build_scene()
        out_path = export_cell(obj)
        reimported = reimport_cell(out_path)
        results = run_assertions(obj, proto, bake_meta, reimported, out_path)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
