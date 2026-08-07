"""
Cell: usd_export__mixed_instance_types__bake_combined__production_scale
Maps to: geonodes_export_interop_gap.md source #7 (issue #103919, "Make
Instances Real" breaks for mixed instance kinds) combined with source #14
(issue #132123, baking for performance) and sources #11/#15 (production-
scale instance counts). Composes usd_export__mixed_instance_types__join_
based_fix (CONFIRMED WORKING, 2-prototype join-based topology, ~320
instances, ONE PointInstancer with two prototypes) with usd_export__points__
bake_after_instancing__recovery_workaround (CONFIRMED WORKING, ~320
instances) at 20,000-instance production scale, no animation -- this exact
static combination was explicitly flagged as untested in the UNTESTED
CELLS composite row ("mixed+bake ... remain untested at production/
extreme scale").

Topology note: matches the CONFIRMED-WORKING join-based shape exactly --
ONE shared node tree, ONE source object, split via index-based Separate
Geometry into two independent branches, each with its own bake-then-
recover chain, combined via a single Join Geometry before the group
output (producing ONE exported PointInstancer with two prototypes) --
NOT two separately-exported objects, which would be a different, less
traceable topology than the one already validated at small scale.

Standalone run (no live MCP connector this session) -- built and run via
GitHub Actions on a fresh Blender 5.2.0 LTS download, per this session's
explicit instruction to run on GitHub Actions instead of the connector.
"""

import bpy
import bmesh
import os
import json
from collections import Counter

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__mixed_instance_types__bake_combined__production_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #7 (issue #103919) + "
        "source #14 (issue #132123) + sources #11/#15 (production-scale "
        "instance counts); composes usd_export__mixed_instance_types__"
        "join_based_fix (CONFIRMED WORKING, ~320) with usd_export__points__"
        "bake_after_instancing__recovery_workaround (CONFIRMED WORKING, "
        "~320) at 20,000-instance production scale, no animation"
    ),
    "export_format": "usd",
    "instance_type": "mixed",
    "bake_node_present": True,
    "animation_present": False,
    "nesting_depth": 1,
    "total_points": 20000,
    "split_threshold": 10000,  # index < threshold -> cube branch, else cone branch
    "float_tolerance": 1e-5,
    "output_path": os.path.join(os.getcwd(), "mixed_bake_20k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_mixed_20k"),
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
    """Single exact-count loose-vert source (Mesh to Points / VERTICES
    mode) -- vertex creation order is used as the split index, first
    `split_threshold` vertices go to the cube branch, the rest to cone."""
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
    return proto


def build_proto_cone():
    bpy.ops.mesh.primitive_cone_add(radius1=0.1, depth=0.2, location=(0, 0, 6))
    proto = bpy.context.active_object
    proto.name = "ProtoCone"
    # Read the real vertex count back rather than assuming a segment default.
    proto_vert_count = len(proto.data.vertices)
    return proto, proto_vert_count


def new_object_info_node(node_group, name, target_obj):
    """As Instance defaults to False when script-built -- must be set
    explicitly (see HARNESS NOTES)."""
    node = node_group.nodes.new("GeometryNodeObjectInfo")
    node.name = name
    node.inputs["As Instance"].default_value = True
    node.inputs["Object"].default_value = target_obj
    return node


def build_bake_branch(ng, branch_name, points_input_socket, proto_obj):
    """One independent branch of the bake-after-instancing recovery chain,
    starting from an already-split Points-domain geometry socket (not from
    Group Input directly, since this cell splits one shared source into
    two branches first)."""
    obj_info_1 = new_object_info_node(ng, f"ObjInfo1_{branch_name}", proto_obj)
    instance_1 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    instance_1.name = f"Instance1_{branch_name}"

    bake_node = ng.nodes.new("GeometryNodeBake")
    bake_node.name = f"Bake_{branch_name}"
    bake_node.bake_items.new("GEOMETRY", "Geometry")

    instances_to_points = ng.nodes.new("GeometryNodeInstancesToPoints")
    instances_to_points.name = f"InstancesToPoints_{branch_name}"

    obj_info_2 = new_object_info_node(ng, f"ObjInfo2_{branch_name}", proto_obj)
    instance_2 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    instance_2.name = f"Instance2_{branch_name}"

    ng.links.new(points_input_socket, instance_1.inputs["Points"])
    ng.links.new(obj_info_1.outputs["Geometry"], instance_1.inputs["Instance"])
    ng.links.new(instance_1.outputs["Instances"], bake_node.inputs["Geometry"])
    ng.links.new(bake_node.outputs["Geometry"], instances_to_points.inputs["Instances"])
    ng.links.new(instances_to_points.outputs["Points"], instance_2.inputs["Points"])
    ng.links.new(obj_info_2.outputs["Geometry"], instance_2.inputs["Instance"])

    return {
        "instance_1": instance_1,
        "bake_node": bake_node,
        "instance_2": instance_2,  # final output: instance_2.outputs["Instances"]
    }


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    proto_cube = build_proto_cube()
    proto_cone, cone_vert_count = build_proto_cone()

    source_obj = build_source_mesh(CONFIG["total_points"])

    mod = source_obj.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Mixed_Bake_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_in = ng.nodes.new("NodeGroupInput")
    group_out = ng.nodes.new("NodeGroupOutput")

    mesh_to_points = ng.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = "VERTICES"

    index_node = ng.nodes.new("GeometryNodeInputIndex")
    compare_node = ng.nodes.new("ShaderNodeMath")
    compare_node.operation = "LESS_THAN"
    compare_node.inputs[1].default_value = float(CONFIG["split_threshold"])

    separate_node = ng.nodes.new("GeometryNodeSeparateGeometry")
    separate_node.domain = "POINT"

    join_node = ng.nodes.new("GeometryNodeJoinGeometry")

    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], separate_node.inputs["Geometry"])
    ng.links.new(index_node.outputs["Index"], compare_node.inputs[0])
    ng.links.new(compare_node.outputs["Value"], separate_node.inputs["Selection"])

    cube_branch = build_bake_branch(ng, "cube", separate_node.outputs["Selection"], proto_cube)
    cone_branch = build_bake_branch(ng, "cone", separate_node.outputs["Inverted"], proto_cone)

    ng.links.new(cube_branch["instance_2"].outputs["Instances"], join_node.inputs["Geometry"])
    ng.links.new(cone_branch["instance_2"].outputs["Instances"], join_node.inputs["Geometry"])
    ng.links.new(join_node.outputs["Geometry"], group_out.inputs["Geometry"])

    return source_obj, mod, {"cube": cube_branch["bake_node"], "cone": cone_branch["bake_node"]}, cone_vert_count


# =====================================================================
# BAKE -- trigger each branch's bake independently, verify via on-disk JSON
# =====================================================================
def trigger_bake(branch_name, source_obj, mod, bake_node):
    # bake_directory is a single modifier-level field, not per-bake-node --
    # each bake node's own bake_id becomes a subfolder under this ONE shared
    # directory. Setting a different bake_directory per branch would make
    # the modifier "forget" the previous branch's cache location at
    # evaluation/export time, since only one bake_directory can be active
    # on the modifier at once.
    os.makedirs(CONFIG["bake_directory"], exist_ok=True)
    mod.bake_target = "DISK"
    mod.bake_directory = CONFIG["bake_directory"]

    bake_id = None
    for b in mod.bakes:
        if b.node == bake_node:
            bake_id = b.bake_id
            break
    if bake_id is None:
        raise RuntimeError(f"could not locate bake_id for {branch_name} branch")

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
            export_animation=False,
            use_instancing=True,
        )
    return out_path


# =====================================================================
# ASSERTIONS -- direct pxr.Usd inspection
# =====================================================================
def run_assertions(out_path, expected_total, expected_split, cone_vert_count):
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
    split = dict(Counter(proto_indices)) if proto_indices else {}

    results["count_match"] = {
        "pass": (n_pos == expected_total and n_proto == expected_total and
                 sorted(split.values()) == sorted([expected_split, expected_total - expected_split])),
        "detail": f"positions={n_pos}, protoIndices={n_proto}, expected_total={expected_total}, split={split}",
    }

    proto_rel = instancer.GetPrototypesRel()
    targets = proto_rel.GetTargets()
    proto_vert_counts = {}
    for idx, target_path in enumerate(targets):
        prim = stage.GetPrimAtPath(target_path)
        resolved_mesh = None
        if prim.IsInstance():
            proto_prim = prim.GetPrototype()
            for child in proto_prim.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    resolved_mesh = UsdGeom.Mesh(child)
                    break
            if resolved_mesh is None and proto_prim.IsA(UsdGeom.Mesh):
                resolved_mesh = UsdGeom.Mesh(proto_prim)
        else:
            for child in prim.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    resolved_mesh = UsdGeom.Mesh(child)
                    break
            if resolved_mesh is None and prim.IsA(UsdGeom.Mesh):
                resolved_mesh = UsdGeom.Mesh(prim)
        if resolved_mesh is not None:
            pts = resolved_mesh.GetPointsAttr().Get()
            proto_vert_counts[idx] = len(pts) if pts else 0
        else:
            proto_vert_counts[idx] = None

    expected_vert_counts = {8, cone_vert_count}
    got_vert_counts = set(v for v in proto_vert_counts.values() if v is not None)
    results["prototype_match"] = {
        "pass": (len(proto_vert_counts) == 2 and got_vert_counts == expected_vert_counts),
        "detail": f"resolved prototype vertex counts (by prototype index): {proto_vert_counts}, expected={expected_vert_counts}",
    }

    return results


# =====================================================================
# REPORT
# =====================================================================
def report(stamp, config, bake_infos, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "bake_infos": bake_infos,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def main():
    stamp = log_version_stamp()
    bake_infos = {}
    try:
        source_obj, mod, bake_nodes, cone_vert_count = build_scene()
        for name, bake_node in bake_nodes.items():
            info = trigger_bake(name, source_obj, mod, bake_node)
            bake_infos[name] = info
            print(f"=== BAKE INFO ({name}) ===")
            print(json.dumps(info, indent=2, default=str))

        out_path = export_cell(source_obj)
        results = run_assertions(out_path, CONFIG["total_points"], CONFIG["split_threshold"], cone_vert_count)
        report(stamp, CONFIG, bake_infos, results)
    except Exception as e:
        report(stamp, CONFIG, bake_infos, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
