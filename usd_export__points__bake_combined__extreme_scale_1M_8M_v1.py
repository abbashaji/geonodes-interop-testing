"""
Cell: usd_export__points__bake_combined__extreme_scale (1M, 8M rungs)
Maps to: geonodes_export_interop_gap.md source #14 (issue #132123, baking
for performance) combined with sources #11/#15 (production/extreme-scale
instance counts, up to the AOUSD forum's 8M+ figure). Extends
usd_export__points__bake_combined__extreme_scale (CONFIRMED WORKING at
200,000 instances, GitHub Actions run 31284975033) up the same scale
ladder already proven for the static/no-bake case
(usd_export__points__use_instancing_fix__extreme_scale: 1M and 8M, both
CONFIRMED WORKING) -- now with a real disk-verified GeometryNodeBake
recovery chain in the path, closing the "true 8M-scale testing for any
combined config is currently blocked" note at its actual target scale,
not just the 200K checkpoint.

Runs both scale points (1,000,000 then 8,000,000) in one script/one CI
run, matching the precedent set by the original extreme_scale_test.py
(SCALE=1000000 and SCALE=8000000 as two points of the same cell).

Fixes the HARNESS NOTES gotcha found on the 200K run: the previous
collapse-to-origin spot-check flagged index 0 as a false positive because
the grid's own point 0 is legitimately at true origin by construction.
This version compares every sampled position against its actual expected
grid coordinate (tolerance-based), not just "near zero" in isolation.
"""

import bpy
import bmesh
import os
import json
import time

COLS = 400
SPACING = 0.5
FLOAT_TOLERANCE = 1e-5
SCALES = [1000000, 8000000]


def log_version_stamp(cell_id):
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": cell_id,
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, indent=2))
    return stamp


def build_source_mesh(num_points):
    mesh = bpy.data.meshes.new("GN_Source_mesh")
    bm = bmesh.new()
    cols = COLS
    rows = num_points // cols
    assert rows * cols == num_points, "grid must divide exactly for exact count"
    for i in range(rows):
        for j in range(cols):
            bm.verts.new((j * SPACING, i * SPACING, 0.0))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("GN_Source", mesh)
    bpy.context.collection.objects.link(obj)
    assert len(obj.data.vertices) == num_points, (
        f"source mesh vertex count mismatch: {len(obj.data.vertices)} != {num_points}"
    )
    return obj


def expected_position(index):
    j = index % COLS
    i = index // COLS
    return (j * SPACING, i * SPACING, 0.0)


def build_proto_cube():
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 5))
    proto = bpy.context.active_object
    proto.name = "ProtoCube"
    return proto


def new_object_info_node(node_group, name):
    node = node_group.nodes.new("GeometryNodeObjectInfo")
    node.name = name
    node.inputs["As Instance"].default_value = True
    return node


def build_scene(num_points):
    bpy.ops.wm.read_factory_settings(use_empty=True)

    source_obj = build_source_mesh(num_points)
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
    bake_node.bake_items.new("GEOMETRY", "Geometry")

    instances_to_points = ng.nodes.new("GeometryNodeInstancesToPoints")

    obj_info_2 = new_object_info_node(ng, "ObjInfo_Second")
    obj_info_2.inputs["Object"].default_value = proto

    instance_2 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], instance_1.inputs["Points"])
    ng.links.new(obj_info_1.outputs["Geometry"], instance_1.inputs["Instance"])
    ng.links.new(instance_1.outputs["Instances"], bake_node.inputs["Geometry"])
    ng.links.new(bake_node.outputs["Geometry"], instances_to_points.inputs["Instances"])
    ng.links.new(instances_to_points.outputs["Points"], instance_2.inputs["Points"])
    ng.links.new(obj_info_2.outputs["Geometry"], instance_2.inputs["Instance"])
    ng.links.new(instance_2.outputs["Instances"], group_out.inputs["Geometry"])

    return source_obj, mod, bake_node


def trigger_bake(source_obj, mod, bake_node, bake_directory):
    os.makedirs(bake_directory, exist_ok=True)
    mod.bake_target = "DISK"
    mod.bake_directory = bake_directory

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
        t0 = time.time()
        result = bpy.ops.object.geometry_node_bake_single(
            session_uid=source_obj.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )
        bake_seconds = time.time() - t0

    bake_root = os.path.join(bake_directory, str(bake_id), "meta")
    cache_info = {
        "operator_result": str(result),
        "bake_id": bake_id,
        "meta_dir_exists": os.path.isdir(bake_root),
        "bake_wall_seconds": round(bake_seconds, 2),
    }
    if os.path.isdir(bake_root):
        meta_files = sorted(os.listdir(bake_root))
        cache_info["meta_files"] = meta_files
        if meta_files:
            with open(os.path.join(bake_root, meta_files[0])) as f:
                meta = json.load(f)
            try:
                inst = meta["items"]["0"]["data"]["instances"]
                cache_info["num_instances_in_cache"] = inst["num_instances"]
                mesh_ref = inst["references"][0]["instances"]["references"][0]["mesh"]
                cache_info["referenced_mesh_vert_count"] = mesh_ref["num_vertices"]
            except (KeyError, IndexError) as e:
                cache_info["cache_parse_error"] = repr(e)
    return cache_info


def export_cell(source_obj, out_path):
    bpy.ops.object.select_all(action="DESELECT")
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj

    window = bpy.context.window_manager.windows[0]
    t0 = time.time()
    with bpy.context.temp_override(window=window):
        bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            export_animation=False,
            use_instancing=True,
        )
    export_seconds = time.time() - t0
    return out_path, export_seconds


def run_assertions(out_path, ground_truth_count):
    from pxr import Usd, UsdGeom

    results = {}
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
        return results

    positions = instancer.GetPositionsAttr().Get()
    proto_indices = instancer.GetProtoIndicesAttr().Get()
    n_pos = len(positions) if positions else 0
    n_proto = len(proto_indices) if proto_indices else 0

    results["count_match"] = {
        "pass": (n_pos == ground_truth_count and n_proto == ground_truth_count),
        "detail": f"positions={n_pos}, protoIndices={n_proto}, ground_truth={ground_truth_count}",
    }

    # Fixed per HARNESS NOTES: compare each sampled position against its
    # actual expected grid coordinate, not just "near zero" in isolation.
    # This correctly handles index 0, which is legitimately at true origin.
    sample_idx = list(range(0, ground_truth_count, max(1, ground_truth_count // 20)))[:20]
    mismatches = []
    for i in sample_idx:
        if i < len(positions):
            p = positions[i]
            ex, ey, ez = expected_position(i)
            if (abs(p[0] - ex) > FLOAT_TOLERANCE
                    or abs(p[1] - ey) > FLOAT_TOLERANCE
                    or abs(p[2] - ez) > FLOAT_TOLERANCE):
                mismatches.append({
                    "index": i,
                    "got": list(p),
                    "expected": [ex, ey, ez],
                })
    results["spot_check_matches_expected_position"] = {
        "pass": len(mismatches) == 0,
        "detail": f"{len(mismatches)}/{len(sample_idx)} sampled positions mismatched expected grid coordinate (tolerance={FLOAT_TOLERANCE})",
        "mismatches": mismatches,
    }

    return results


def report(stamp, config, bake_info, export_seconds, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "bake_info": bake_info,
        "export_wall_seconds": round(export_seconds, 2) if export_seconds is not None else None,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def run_one_scale(scale):
    cell_id = f"usd_export__points__bake_combined__extreme_scale_{scale}"
    config = {
        "cell_id": cell_id,
        "export_format": "usd",
        "instance_type": "points",
        "bake_node_present": True,
        "animation_present": False,
        "nesting_depth": 1,
        "num_points_target": scale,
        "output_path": os.path.join(os.getcwd(), f"bake_{scale}.usdc"),
        "bake_directory": os.path.join(os.getcwd(), f"bake_cache_{scale}"),
    }
    stamp = log_version_stamp(cell_id)
    bake_info = None
    export_seconds = None
    try:
        source_obj, mod, bake_node = build_scene(scale)
        bake_info = trigger_bake(source_obj, mod, bake_node, config["bake_directory"])
        print("=== BAKE INFO ===")
        print(json.dumps(bake_info, indent=2, default=str))
        out_path, export_seconds = export_cell(source_obj, config["output_path"])
        results = run_assertions(out_path, scale)
        report(stamp, config, bake_info, export_seconds, results)
    except Exception as e:
        report(stamp, config, bake_info, export_seconds, {}, crashed=True, crash_detail=repr(e))
        raise


def main():
    for scale in SCALES:
        run_one_scale(scale)


if __name__ == "__main__":
    main()
