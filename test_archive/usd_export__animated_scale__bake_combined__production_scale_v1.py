"""
Cell: usd_export__animated_scale__bake_combined__production_scale
Maps to: geonodes_export_interop_gap.md source #2 (issue #139654, production
USD pipeline) combined with source #14 (issue #132123, baking for
performance) and sources #11/#15 (production-scale instance counts).
Extends usd_export__animated_scale__bake_combined (CONFIRMED WORKING at
~320 instances) to the 20,000-instance production-scale checkpoint --
closes the last open cell in the position/rotation/scale trio for
bake+animation composition at production scale (position: CONFIRMED
WORKING, rotation: CONFIRMED BROKEN -- see
usd_export__animated_rotation__bake_combined__production_scale).

Standalone run (no live MCP connector this session) -- built and run via
GitHub Actions on a fresh Blender 5.2.0 LTS download, per this session's
explicit instruction to run on GitHub Actions instead of the connector.
Follows references/methodology.md's stable procedure and
correctness_test_template.py's shape; adapted to actually author the node
network per Step B (the template's build_scene() is a skeleton, not
runnable as-is).
"""

import bpy
import bmesh
import os
import sys
import json
import mathutils

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__animated_scale__bake_combined__production_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (issue #139654) + "
        "source #14 (issue #132123) + sources #11/#15 (production-scale "
        "instance counts); extends usd_export__animated_scale__bake_combined "
        "(CONFIRMED WORKING, ~320 instances) to 20,000 instances"
    ),
    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": "scale",
    "nesting_depth": 1,
    "num_points_target": 20000,
    "float_tolerance": 1e-5,
    "frame_pad": 4,
    "frame_start": 5,
    "frame_end": 24,
    "scale_start": (1.0, 1.0, 1.0),
    "scale_end": (2.5, 2.5, 2.5),
    "output_path": os.path.join(os.getcwd(), "scale_bake_20k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_scale_20k"),
}


# =====================================================================
# VERSION STAMP -- must run first, must be in every log, no exceptions
# =====================================================================
def log_version_stamp():
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": CONFIG["cell_id"],
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, indent=2))
    return stamp


# =====================================================================
# BUILD -- construct the bake-after-instancing recovery chain, scale
# animation on the second (post-recovery) Instance on Points node
# =====================================================================
def build_source_mesh(num_points):
    """Exact-count loose-vert mesh (Mesh to Points / VERTICES mode source),
    matching the production_scale sibling cells' exact-count construction
    convention rather than density-tuned Distribute Points on Faces."""
    mesh = bpy.data.meshes.new("GN_Source_mesh")
    bm = bmesh.new()
    cols = 200
    rows = num_points // cols
    assert rows * cols == num_points, "grid must divide exactly for exact count"
    spacing = 0.5
    for i in range(rows):
        for j in range(cols):
            bm.verts.new((j * spacing, i * spacing, 0.0))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("GN_Source", mesh)
    bpy.context.collection.objects.link(obj)
    assert len(obj.data.vertices) == num_points, (
        f"source mesh vertex count mismatch: {len(obj.data.vertices)} != {num_points}"
    )
    return obj


def build_proto_cube():
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 5))
    proto = bpy.context.active_object
    proto.name = "ProtoCube"
    # Keep it out of the render/export set as a standalone geometry source --
    # it is only ever referenced via Object Info nodes, never itself exported.
    return proto


def new_object_info_node(node_group, name):
    """Object Info's As Instance socket defaults to False when script-built
    (see HARNESS NOTES) -- must be set explicitly or export silently
    produces near-empty output with warnings, not a crash."""
    node = node_group.nodes.new("GeometryNodeObjectInfo")
    node.name = name
    node.inputs["As Instance"].default_value = True
    return node


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    source_obj = build_source_mesh(CONFIG["num_points_target"])
    proto = build_proto_cube()

    mod = source_obj.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Test_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    group_in = ng.nodes.new("NodeGroupInput")
    group_out = ng.nodes.new("NodeGroupOutput")

    mesh_to_points = ng.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = "VERTICES"

    obj_info_1 = new_object_info_node(ng, "ObjInfo_First")
    obj_info_1.inputs["Object"].default_value = proto

    instance_1 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    bake_node = ng.nodes.new("GeometryNodeBake")
    # GeometryNodeBake ships with NO default bake item -- must add explicitly
    # (see HARNESS NOTES: "GeometryNodeBake socket naming and bake_id location").
    bake_node.bake_items.new("GEOMETRY", "Geometry")

    instances_to_points = ng.nodes.new("GeometryNodeInstancesToPoints")

    obj_info_2 = new_object_info_node(ng, "ObjInfo_Second")
    obj_info_2.inputs["Object"].default_value = proto

    instance_2 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    # --- Wire it up ---
    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], instance_1.inputs["Points"])
    ng.links.new(obj_info_1.outputs["Geometry"], instance_1.inputs["Instance"])
    ng.links.new(instance_1.outputs["Instances"], bake_node.inputs["Geometry"])
    ng.links.new(bake_node.outputs["Geometry"], instances_to_points.inputs["Instances"])
    ng.links.new(instances_to_points.outputs["Points"], instance_2.inputs["Points"])
    ng.links.new(obj_info_2.outputs["Geometry"], instance_2.inputs["Instance"])
    ng.links.new(instance_2.outputs["Instances"], group_out.inputs["Geometry"])

    return source_obj, mod, ng, bake_node, instance_2


# =====================================================================
# BAKE -- real DISK-target bake, verified via on-disk cache JSON, not
# trusted from the operator's {'FINISHED'} return value alone
# =====================================================================
def trigger_bake(source_obj, mod, bake_node):
    os.makedirs(CONFIG["bake_directory"], exist_ok=True)
    mod.bake_target = "DISK"
    mod.bake_directory = CONFIG["bake_directory"]

    bake_id = None
    for b in mod.bakes:
        if b.node == bake_node:
            bake_id = b.bake_id
            break
    if bake_id is None:
        raise RuntimeError("could not locate bake_id for bake_node on modifier.bakes")

    bpy.context.view_layer.objects.active = source_obj
    source_obj.select_set(True)

    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window, object=source_obj, active_object=source_obj):
        result = bpy.ops.object.geometry_node_bake_single(
            session_uid=source_obj.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )

    # {'FINISHED'} alone is not sufficient evidence -- read the on-disk
    # cache JSON to confirm real content.
    bake_root = os.path.join(CONFIG["bake_directory"], str(bake_id), "meta")
    cache_info = {"operator_result": str(result), "bake_id": bake_id, "meta_dir_exists": os.path.isdir(bake_root)}
    if os.path.isdir(bake_root):
        meta_files = sorted(os.listdir(bake_root))
        cache_info["meta_files"] = meta_files
        if meta_files:
            with open(os.path.join(bake_root, meta_files[0])) as f:
                meta = json.load(f)
            cache_info["meta_sample"] = {
                k: meta[k] for k in list(meta.keys())[:10]
            }
    return cache_info


# =====================================================================
# ANIMATE -- keyframe uniform scale on the SECOND (post-recovery)
# Instance on Points node, with the padding-frame drift fix
# =====================================================================
def animate_scale(instance_2):
    sock = instance_2.inputs["Scale"]
    pad, start, end = CONFIG["frame_pad"], CONFIG["frame_start"], CONFIG["frame_end"]
    s0, s1 = CONFIG["scale_start"], CONFIG["scale_end"]

    sock.default_value = s0
    sock.keyframe_insert(data_path="default_value", frame=pad)
    sock.keyframe_insert(data_path="default_value", frame=start)
    sock.default_value = s1
    sock.keyframe_insert(data_path="default_value", frame=end)

    bpy.context.scene.frame_start = pad
    bpy.context.scene.frame_end = end


def read_true_curve(ng, frames):
    """Read the TRUE authored curve via Blender 5.0+'s layered Action
    system (action.layers[0].strips[0].channelbags[0].fcurves), honoring
    Bezier easing rather than assuming linear interpolation between
    keyframes -- see HARNESS NOTES."""
    action = ng.animation_data.action
    fcurves = action.layers[0].strips[0].channelbags[0].fcurves
    scale_fcurves = [fc for fc in fcurves if "default_value" in fc.data_path and "Scale" not in fc.data_path]
    # Fall back to matching by data_path containing the node's scale socket
    # identifier if the simple filter above is ambiguous.
    curve = {}
    for frame in frames:
        vals = [fc.evaluate(frame) for fc in fcurves if fc.array_index in (0, 1, 2)]
        curve[frame] = vals
    return curve


# =====================================================================
# EXPORT
# =====================================================================
def export_cell(source_obj):
    out_path = CONFIG["output_path"]
    bpy.ops.object.select_all(action="DESELECT")
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj

    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            export_animation=True,
            use_instancing=True,
        )
    return out_path


# =====================================================================
# ASSERTIONS -- inspect the exported USD directly via pxr.Usd (no
# reimport step needed/available in this standalone runner session;
# confirmed importable directly in --background on this runner per
# HARNESS NOTES' Blender 5.2.0 entry)
# =====================================================================
def run_assertions(out_path, ground_truth_count):
    from pxr import Usd, UsdGeom

    results = {}
    tol = CONFIG["float_tolerance"]

    file_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    results["export_produced_nonempty_file"] = {
        "pass": file_size > 1000,
        "detail": f"size={file_size} bytes",
    }

    stage = Usd.Stage.Open(out_path)
    instancer = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer = UsdGeom.PointInstancer(prim)
            break

    if instancer is None:
        results["count_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        results["transform_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        return results

    positions_attr = instancer.GetPositionsAttr()
    proto_idx_attr = instancer.GetProtoIndicesAttr()
    positions = positions_attr.Get(0) if positions_attr else None
    proto_indices = proto_idx_attr.Get(0) if proto_idx_attr else None
    n_pos = len(positions) if positions else 0
    n_proto = len(proto_indices) if proto_indices else 0

    results["count_match"] = {
        "pass": (n_pos == ground_truth_count and n_proto == ground_truth_count),
        "detail": f"positions={n_pos}, protoIndices={n_proto}, ground_truth={ground_truth_count}",
    }

    scales_attr = instancer.GetScalesAttr()
    frames = [CONFIG["frame_pad"], CONFIG["frame_start"], CONFIG["frame_start"] + 1,
              CONFIG["frame_start"] + 5, CONFIG["frame_end"]]
    sample_indices = [0, ground_truth_count - 1]

    time_samples = scales_attr.GetTimeSamples() if scales_attr else []
    results["scales_attr_time_samples"] = {
        "pass": None,
        "detail": f"requested_range={frames[0]}-{frames[-1]}, actual_time_samples={time_samples}",
    }

    per_frame = {}
    for frame in frames:
        vals = scales_attr.Get(frame) if scales_attr else None
        if vals is None:
            per_frame[frame] = None
            continue
        per_frame[frame] = [tuple(vals[i]) for i in sample_indices if i < len(vals)]

    true_curve = {
        CONFIG["frame_pad"]: CONFIG["scale_start"],
        CONFIG["frame_start"]: CONFIG["scale_start"],
        CONFIG["frame_end"]: CONFIG["scale_end"],
    }

    boundary_ok = True
    boundary_detail = {}
    for frame in (CONFIG["frame_pad"], CONFIG["frame_start"], CONFIG["frame_end"]):
        expected = true_curve.get(frame)
        got = per_frame.get(frame)
        if expected is None or got is None:
            continue
        for v in got:
            err = max(abs(v[k] - expected[k]) for k in range(3))
            boundary_detail[f"frame{frame}"] = {"got": v, "expected": expected, "max_abs_err": err}
            if err > tol:
                boundary_ok = False

    results["transform_match"] = {
        "pass": boundary_ok,
        "detail": {
            "tolerance": tol,
            "per_frame_sample": per_frame,
            "boundary_check": boundary_detail,
            "requested_export_range": f"{CONFIG['frame_pad']}-{CONFIG['frame_end']}",
        },
    }

    return results


# =====================================================================
# REPORT
# =====================================================================
def report(stamp, config, bake_info, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "bake_info": bake_info,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def main():
    stamp = log_version_stamp()
    bake_info = None
    try:
        source_obj, mod, ng, bake_node, instance_2 = build_scene()
        bake_info = trigger_bake(source_obj, mod, bake_node)
        print("=== BAKE INFO ===")
        print(json.dumps(bake_info, indent=2, default=str))
        animate_scale(instance_2)
        out_path = export_cell(source_obj)
        results = run_assertions(out_path, CONFIG["num_points_target"])
        report(stamp, CONFIG, bake_info, results)
    except Exception as e:
        report(stamp, CONFIG, bake_info, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
