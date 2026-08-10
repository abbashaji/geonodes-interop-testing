"""
Cell: usd_export__points__bake_combined__extreme_scale
Maps to: geonodes_export_interop_gap.md source #14 (issue #132123, baking
for performance) combined with sources #11/#15 (production/extreme-scale
instance counts, up to the AOUSD forum's 8M+ figure). Extends usd_export__
points__bake_after_instancing__recovery_workaround (CONFIRMED WORKING,
~320 instances) past the already-confirmed 20,000-instance production-
scale checkpoint (usd_export__animated_position__bake_combined__production_
scale / ...scale__bake_combined__production_scale, both CONFIRMED WORKING)
to 200,000 instances -- directly attacking the standing blocker note
("true 8M-scale testing for any combined config is currently blocked in
this environment"). Static/no-animation/single-prototype, to isolate the
scale question from the animation/mixed/nested questions already answered
separately at 20K.

This session runs on a fresh Blender download inside GitHub Actions
(no live MCP connector), which is a genuinely different environment from
whatever earlier blocked extreme-scale combined-config testing -- worth
testing directly rather than assuming the same blocker still applies.
"""

import bpy
import bmesh
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__points__bake_combined__extreme_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #14 (issue #132123) + "
        "sources #11/#15 (production/extreme-scale instance counts); "
        "extends usd_export__points__bake_after_instancing__recovery_"
        "workaround (CONFIRMED WORKING, ~320) past the 20,000-instance "
        "production-scale checkpoint to 200,000 instances, static/no-"
        "animation/single-prototype -- attacks the standing 'true extreme-"
        "scale testing for any combined config is currently blocked' note"
    ),
    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": False,
    "nesting_depth": 1,
    "num_points_target": 200000,
    "output_path": os.path.join(os.getcwd(), "bake_200k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_200k"),
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
    print(json.dumps(stamp, indent=2))
    return stamp


# =====================================================================
# BUILD
# =====================================================================
def build_source_mesh(num_points):
    mesh = bpy.data.meshes.new("GN_Source_mesh")
    bm = bmesh.new()
    cols = 400
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
    return proto


def new_object_info_node(node_group, name):
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


# =====================================================================
# BAKE
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
        import time
        t0 = time.time()
        result = bpy.ops.object.geometry_node_bake_single(
            session_uid=source_obj.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )
        bake_seconds = time.time() - t0

    bake_root = os.path.join(CONFIG["bake_directory"], str(bake_id), "meta")
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


# =====================================================================
# EXPORT
# =====================================================================
def export_cell(source_obj):
    import time
    out_path = CONFIG["output_path"]
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


# =====================================================================
# ASSERTIONS
# =====================================================================
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

    # Spot-check a sample of positions for collapse-to-origin artifacts,
    # matching the methodology already used at 1M/8M single-prototype scale.
    sample_idx = list(range(0, ground_truth_count, max(1, ground_truth_count // 20)))[:20]
    collapsed = 0
    for i in sample_idx:
        if i < len(positions):
            p = positions[i]
            if abs(p[0]) < 1e-9 and abs(p[1]) < 1e-9 and abs(p[2]) < 1e-9:
                collapsed += 1
    results["spot_check_no_collapse_to_origin"] = {
        "pass": collapsed == 0,
        "detail": f"{collapsed}/{len(sample_idx)} sampled positions collapsed to origin",
    }

    return results


# =====================================================================
# REPORT
# =====================================================================
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


def main():
    stamp = log_version_stamp()
    bake_info = None
    export_seconds = None
    try:
        source_obj, mod, bake_node = build_scene()
        bake_info = trigger_bake(source_obj, mod, bake_node)
        print("=== BAKE INFO ===")
        print(json.dumps(bake_info, indent=2, default=str))
        out_path, export_seconds = export_cell(source_obj)
        results = run_assertions(out_path, CONFIG["num_points_target"])
        report(stamp, CONFIG, bake_info, export_seconds, results)
    except Exception as e:
        report(stamp, CONFIG, bake_info, export_seconds, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
