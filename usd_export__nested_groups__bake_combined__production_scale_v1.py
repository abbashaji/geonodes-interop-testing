"""
Cell: usd_export__nested_groups__bake_combined__production_scale
Maps to: geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+
instance production scenes -- nested/multi-level instancing at scale)
combined with source #14 (issue #132123, baking for performance).
Composes usd_export__nested_groups__baked_object_fix (CONFIRMED WORKING,
2-level nesting via Python-side baked-inner-object, ~240 outer instances)
with usd_export__points__bake_after_instancing__recovery_workaround
(CONFIRMED WORKING GeometryNodeBake-node recovery chain, ~320 instances)
at 20,000-instance production scale, no animation -- explicitly flagged
as untested in the UNTESTED CELLS composite row ("nested+bake ...
remain untested at production/extreme scale").

Two distinct meanings of "bake" are both present here, deliberately, since
that is exactly what the untested-cell label refers to:
  1. Python-side to_mesh()+realize baking of the inner cluster into a real
     object (the established nesting-undercounting fix).
  2. The actual GeometryNodeBake node, DISK-target, applied to the OUTER
     level's instancing (the established performance-caching recovery
     chain), now driving 20,000 outer instances of that baked prototype.

Standalone run (no live MCP connector this session) -- built and run via
GitHub Actions on a fresh Blender 5.2.0 LTS download, per this session's
explicit instruction to run on GitHub Actions instead of the connector.
"""

import bpy
import bmesh
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__nested_groups__bake_combined__production_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+ "
        "instance production scenes) + source #14 (issue #132123); "
        "composes usd_export__nested_groups__baked_object_fix (CONFIRMED "
        "WORKING, 2-level, ~240) with usd_export__points__bake_after_"
        "instancing__recovery_workaround (CONFIRMED WORKING, ~320) at "
        "20,000-instance production scale, no animation"
    ),
    "export_format": "usd",
    "instance_type": "nested",
    "nesting_depth": 2,
    "bake_node_present": True,
    "animation_present": False,
    "inner_cluster_count": 5,       # exact-count inner points per cluster
    "outer_points_target": 20000,   # exact-count outer points (production scale)
    "float_tolerance": 1e-5,
    "output_path": os.path.join(os.getcwd(), "nested_bake_20k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_nested_20k"),
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
# BUILD -- Level 1 (inner): exact-count points -> Object Info(As Instance)
# -> Instance on Points -> Realize Instances -> Python-side bake to a real
# object. This is the established nesting fix, unchanged.
# =====================================================================
def build_exact_point_mesh(name, num_points, x_offset=0.0):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm = bmesh.new()
    for i in range(num_points):
        bm.verts.new((x_offset + i * 0.3, 0.0, 0.0))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assert len(obj.data.vertices) == num_points, (
        f"{name} vertex count mismatch: {len(obj.data.vertices)} != {num_points}"
    )
    return obj


def build_proto_cube():
    bpy.ops.mesh.primitive_cube_add(size=0.15, location=(0, 0, 8))
    proto = bpy.context.active_object
    proto.name = "ProtoCube"
    return proto


def new_object_info_node(node_group, name, target_obj):
    node = node_group.nodes.new("GeometryNodeObjectInfo")
    node.name = name
    node.inputs["As Instance"].default_value = True
    node.inputs["Object"].default_value = target_obj
    return node


def bake_inner_cluster_to_real_object(proto_cube):
    """Level 1: 5 exact points -> Object Info(As Instance) -> Instance on
    Points -> Realize Instances, evaluated via depsgraph and copied into a
    real, persistent object -- matching usd_export__nested_groups__baked_
    object_fix's established approach exactly."""
    inner_source = build_exact_point_mesh("InnerSource", CONFIG["inner_cluster_count"])

    mod = inner_source.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Inner_Cluster", "GeometryNodeTree")
    mod.node_group = ng
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_in = ng.nodes.new("NodeGroupInput")
    group_out = ng.nodes.new("NodeGroupOutput")

    mesh_to_points = ng.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = "VERTICES"
    obj_info = new_object_info_node(ng, "ObjInfo_Inner", proto_cube)
    instance = ng.nodes.new("GeometryNodeInstanceOnPoints")
    realize = ng.nodes.new("GeometryNodeRealizeInstances")

    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], instance.inputs["Points"])
    ng.links.new(obj_info.outputs["Geometry"], instance.inputs["Instance"])
    ng.links.new(instance.outputs["Instances"], realize.inputs["Geometry"])
    ng.links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = inner_source.evaluated_get(depsgraph)
    mesh_eval = eval_obj.to_mesh()
    baked_mesh = mesh_eval.copy()
    baked_mesh.name = "BakedInnerCluster_mesh"
    eval_obj.to_mesh_clear()

    baked_obj = bpy.data.objects.new("BakedInnerCluster", baked_mesh)
    bpy.context.collection.objects.link(baked_obj)

    expected_verts = CONFIG["inner_cluster_count"] * 8  # 5 cubes x 8 verts
    actual_verts = len(baked_obj.data.vertices)
    assert actual_verts == expected_verts, (
        f"baked inner cluster vertex count mismatch: {actual_verts} != {expected_verts}"
    )
    return baked_obj, actual_verts


# =====================================================================
# BUILD -- Level 2 (outer, exported level): exact-count 20,000 points ->
# Object Info(As Instance, target=BakedInnerCluster) -> Instance on Points
# -> real GeometryNodeBake (DISK) -> Instances to Points -> second Object
# Info(As Instance) -> second Instance on Points -> Output. This is the
# established GeometryNodeBake recovery chain, now driving the outer level
# of a nested structure instead of a flat single-prototype scatter.
# =====================================================================
def build_outer_scene(baked_inner_obj):
    outer_source = build_exact_point_mesh("OuterSource", CONFIG["outer_points_target"], x_offset=1000.0)
    # OuterSource above used a 1D line layout via build_exact_point_mesh --
    # fine for exact count, geometry doesn't need to be planar for Mesh to
    # Points/VERTICES mode.

    mod = outer_source.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Outer_Bake", "GeometryNodeTree")
    mod.node_group = ng
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_in = ng.nodes.new("NodeGroupInput")
    group_out = ng.nodes.new("NodeGroupOutput")

    mesh_to_points = ng.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = "VERTICES"

    obj_info_1 = new_object_info_node(ng, "ObjInfo_Outer1", baked_inner_obj)
    instance_1 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    bake_node = ng.nodes.new("GeometryNodeBake")
    bake_node.bake_items.new("GEOMETRY", "Geometry")

    instances_to_points = ng.nodes.new("GeometryNodeInstancesToPoints")

    obj_info_2 = new_object_info_node(ng, "ObjInfo_Outer2", baked_inner_obj)
    instance_2 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], instance_1.inputs["Points"])
    ng.links.new(obj_info_1.outputs["Geometry"], instance_1.inputs["Instance"])
    ng.links.new(instance_1.outputs["Instances"], bake_node.inputs["Geometry"])
    ng.links.new(bake_node.outputs["Geometry"], instances_to_points.inputs["Instances"])
    ng.links.new(instances_to_points.outputs["Points"], instance_2.inputs["Points"])
    ng.links.new(obj_info_2.outputs["Geometry"], instance_2.inputs["Instance"])
    ng.links.new(instance_2.outputs["Instances"], group_out.inputs["Geometry"])

    return outer_source, mod, bake_node


# =====================================================================
# BAKE -- trigger, verify via on-disk JSON
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
        raise RuntimeError("could not locate bake_id on outer modifier")

    bpy.context.view_layer.objects.active = source_obj
    source_obj.select_set(True)

    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window, object=source_obj, active_object=source_obj):
        result = bpy.ops.object.geometry_node_bake_single(
            session_uid=source_obj.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )

    bake_root = os.path.join(CONFIG["bake_directory"], str(bake_id), "meta")
    cache_info = {"operator_result": str(result), "bake_id": bake_id, "meta_dir_exists": os.path.isdir(bake_root)}
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
def export_cell(outer_source):
    out_path = CONFIG["output_path"]
    bpy.ops.object.select_all(action="DESELECT")
    outer_source.select_set(True)
    bpy.context.view_layer.objects.active = outer_source

    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            export_animation=False,
            use_instancing=True,
        )
    return out_path


# =====================================================================
# ASSERTIONS
# =====================================================================
def run_assertions(out_path, expected_total, expected_proto_vert_count):
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

    results["instancer_count"] = {
        "pass": instancer is not None,
        "detail": f"instancer_found={instancer is not None}",
    }
    if instancer is None:
        results["count_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        results["prototype_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        return results

    positions = instancer.GetPositionsAttr().Get()
    proto_indices = instancer.GetProtoIndicesAttr().Get()
    n_pos = len(positions) if positions else 0
    n_proto = len(proto_indices) if proto_indices else 0
    all_zero_index = all(i == 0 for i in proto_indices) if proto_indices else False

    results["count_match"] = {
        "pass": (n_pos == expected_total and n_proto == expected_total and all_zero_index),
        "detail": f"positions={n_pos}, protoIndices={n_proto}, expected={expected_total}, all_proto_index_zero={all_zero_index}",
    }

    proto_rel = instancer.GetPrototypesRel()
    targets = proto_rel.GetTargets()
    resolved_vert_count = None
    resolution_path = None
    if targets:
        prim = stage.GetPrimAtPath(targets[0])
        if prim.IsInstance():
            proto_prim = prim.GetPrototype()
            for child in proto_prim.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    resolved_vert_count = len(UsdGeom.Mesh(child).GetPointsAttr().Get() or [])
                    resolution_path = str(child.GetPath())
                    break
            if resolved_vert_count is None and proto_prim.IsA(UsdGeom.Mesh):
                resolved_vert_count = len(UsdGeom.Mesh(proto_prim).GetPointsAttr().Get() or [])
                resolution_path = str(proto_prim.GetPath())
        else:
            for child in prim.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    resolved_vert_count = len(UsdGeom.Mesh(child).GetPointsAttr().Get() or [])
                    resolution_path = str(child.GetPath())
                    break
            if resolved_vert_count is None and prim.IsA(UsdGeom.Mesh):
                resolved_vert_count = len(UsdGeom.Mesh(prim).GetPointsAttr().Get() or [])
                resolution_path = str(prim.GetPath())

    results["prototype_match"] = {
        "pass": resolved_vert_count == expected_proto_vert_count,
        "detail": f"resolved prototype vertex count={resolved_vert_count} at {resolution_path}, expected={expected_proto_vert_count}",
    }

    return results


# =====================================================================
# REPORT
# =====================================================================
def report(stamp, config, bake_info, inner_bake_verts, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "outer_bake_info": bake_info,
        "inner_baked_cluster_vert_count": inner_bake_verts,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def main():
    stamp = log_version_stamp()
    bake_info = None
    inner_verts = None
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        proto_cube = build_proto_cube()

        baked_inner_obj, inner_verts = bake_inner_cluster_to_real_object(proto_cube)
        print(f"=== INNER CLUSTER BAKED: {inner_verts} verts ===")

        outer_source, mod, bake_node = build_outer_scene(baked_inner_obj)
        bake_info = trigger_bake(outer_source, mod, bake_node)
        print("=== OUTER BAKE INFO ===")
        print(json.dumps(bake_info, indent=2, default=str))

        out_path = export_cell(outer_source)
        results = run_assertions(out_path, CONFIG["outer_points_target"], inner_verts)
        report(stamp, CONFIG, bake_info, inner_verts, results)
    except Exception as e:
        report(stamp, CONFIG, bake_info, inner_verts, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
