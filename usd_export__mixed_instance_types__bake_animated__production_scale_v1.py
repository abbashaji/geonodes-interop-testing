"""
Cell: usd_export__mixed_instance_types__bake_animated__production_scale
Maps to: geonodes_export_interop_gap.md source #7 (issue #103919, "Make
Instances Real" breaks for mixed instance kinds) + source #14 (issue
#132123, baking for performance) + source #2 (issue #139654, animated
instances) + sources #11/#15 (production-scale instance counts). Extends
usd_export__mixed_animated_bake__triple_combined (CONFIRMED WORKING, all
three fixes composed together, ~103 instances) to 20,000-instance
production scale -- closes the "mixed+bake+animation at production/
extreme scale" item flagged open in the UNTESTED CELLS composite row, the
last item in that row still untested.

Topology: matches the CONFIRMED-WORKING join-based mixed-types shape
(usd_export__mixed_instance_types__bake_combined__production_scale) --
ONE shared node tree, index-based Separate Geometry into two branches
(cube/cone), each with its own independent bake-then-recover chain, Join
Geometry, THEN a uniform animated Set Position (padding-frame drift fix)
applied after the join -- matching where the triple_combined small-scale
cell applied its own animation (after the join, not per-branch).
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
    "cell_id": "usd_export__mixed_instance_types__bake_animated__production_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #7 (issue #103919) + "
        "source #14 (issue #132123) + source #2 (issue #139654) + "
        "sources #11/#15 (production-scale instance counts); extends "
        "usd_export__mixed_animated_bake__triple_combined (CONFIRMED "
        "WORKING, ~103) to 20,000-instance production scale"
    ),
    "export_format": "usd",
    "instance_type": "mixed",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "total_points": 20000,
    "split_threshold": 10000,  # index < threshold -> cube branch, else cone branch
    "float_tolerance": 1e-5,
    "output_path": os.path.join(os.getcwd(), "mixed_bake_animated_20k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_mixed_animated_20k"),
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

    return {"instance_1": instance_1, "bake_node": bake_node, "instance_2": instance_2}


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    proto_cube = build_proto_cube()
    proto_cone, cone_vert_count = build_proto_cone()

    source_obj = build_source_mesh(CONFIG["total_points"])

    mod = source_obj.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Mixed_Bake_Animated_Group", "GeometryNodeTree")
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
    set_pos_node = ng.nodes.new("GeometryNodeSetPosition")

    ng.links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], separate_node.inputs["Geometry"])
    ng.links.new(index_node.outputs["Index"], compare_node.inputs[0])
    ng.links.new(compare_node.outputs["Value"], separate_node.inputs["Selection"])

    cube_branch = build_bake_branch(ng, "cube", separate_node.outputs["Selection"], proto_cube)
    cone_branch = build_bake_branch(ng, "cone", separate_node.outputs["Inverted"], proto_cone)

    ng.links.new(cube_branch["instance_2"].outputs["Instances"], join_node.inputs["Geometry"])
    ng.links.new(cone_branch["instance_2"].outputs["Instances"], join_node.inputs["Geometry"])
    ng.links.new(join_node.outputs["Geometry"], set_pos_node.inputs["Geometry"])
    ng.links.new(set_pos_node.outputs["Geometry"], group_out.inputs["Geometry"])

    return (source_obj, mod,
            {"cube": cube_branch["bake_node"], "cone": cone_branch["bake_node"]},
            cone_vert_count, set_pos_node)


# =====================================================================
# BAKE -- trigger each branch's bake independently, verify via on-disk JSON
# =====================================================================
def trigger_bake(branch_name, source_obj, mod, bake_node):
    # bake_directory is a single modifier-level field, not per-bake-node --
    # each bake node's own bake_id becomes a subfolder under this ONE
    # shared directory (see HARNESS NOTES / the static mixed+bake entry).
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
# ANIMATE -- padding-frame drift fix, applied AFTER the join (uniform,
# both prototypes move together)
# =====================================================================
def animate_set_position(set_pos_node):
    offset_socket = set_pos_node.inputs["Offset"]
    scene = bpy.context.scene

    offset_socket.default_value = (0.0, 0.0, 0.0)
    offset_socket.keyframe_insert(data_path="default_value", frame=4)

    offset_socket.default_value = (0.0, 0.0, 0.0)
    offset_socket.keyframe_insert(data_path="default_value", frame=5)

    offset_socket.default_value = (3.0, 0.0, 0.0)
    offset_socket.keyframe_insert(data_path="default_value", frame=24)

    scene.frame_start = 4
    scene.frame_end = 24
    scene.frame_set(4)


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
# ASSERTIONS
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
    instancer_prim = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer_prim = prim
            break

    if instancer_prim is None:
        results["instancer_found"] = {"pass": False, "detail": "no PointInstancer prim found"}
        return results

    instancer = UsdGeom.PointInstancer(instancer_prim)
    results["instancer_found"] = {"pass": True, "detail": str(instancer_prim.GetPath())}

    positions_attr = instancer.GetPositionsAttr()
    proto_indices_attr = instancer.GetProtoIndicesAttr()

    pos_f4 = positions_attr.Get(4)
    pos_f5 = positions_attr.Get(5)
    pos_f24 = positions_attr.Get(24)
    proto_indices = proto_indices_attr.Get(5)

    count_f5 = len(pos_f5) if pos_f5 else 0
    count_f24 = len(pos_f24) if pos_f24 else 0
    proto_count = len(proto_indices) if proto_indices else 0
    split = dict(Counter(proto_indices)) if proto_indices else {}

    results["count_match"] = {
        "pass": (count_f5 == expected_total and count_f24 == expected_total and
                 proto_count == expected_total and
                 sorted(split.values()) == sorted([expected_split, expected_total - expected_split])),
        "detail": f"expected_total={expected_total}, frame5_positions={count_f5}, "
                  f"frame24_positions={count_f24}, protoIndices={proto_count}, split={split}",
    }

    # --- Timing/drift: spot-check first, middle, last instance ---
    sample_indices = [0, expected_total // 2, expected_total - 1]
    tol = CONFIG["float_tolerance"]

    padding_drift_ok = True
    padding_details = []
    delta_ok = True
    delta_details = []

    if pos_f4 and pos_f5 and pos_f24:
        for i in sample_indices:
            d4, d5, d24 = pos_f4[i], pos_f5[i], pos_f24[i]
            pad_drift = (abs(d4[0] - d5[0]), abs(d4[1] - d5[1]), abs(d4[2] - d5[2]))
            if max(pad_drift) > 1e-6:
                padding_drift_ok = False
            padding_details.append({"instance": i, "frame4": list(d4), "frame5": list(d5), "drift": max(pad_drift)})

            delta_x = d24[0] - d5[0]
            if abs(delta_x - 3.0) > tol:
                delta_ok = False
            delta_details.append({"instance": i, "delta_x": delta_x})
    else:
        padding_drift_ok = False
        delta_ok = False

    results["padding_frame_zero_drift"] = {"pass": padding_drift_ok, "detail": padding_details}
    results["frame24_exact_delta_3_0"] = {"pass": delta_ok, "detail": delta_details}

    # --- Prototype-geometry resolution -- per HARNESS NOTES, do NOT assume
    # an animated cell resolves the same way a static cell does; check both
    # raw and forwarded targets rather than reusing the static cell's code
    # unchanged. ---
    rel = instancer.GetPrototypesRel()
    raw_targets = rel.GetTargets()
    forwarded_targets = rel.GetForwardedTargets()
    targets = raw_targets if raw_targets else forwarded_targets

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
        "detail": f"used_targets={'raw' if raw_targets else 'forwarded'}, "
                  f"resolved prototype vertex counts (by index): {proto_vert_counts}, expected={expected_vert_counts}",
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
        source_obj, mod, bake_nodes, cone_vert_count, set_pos_node = build_scene()
        for name, bake_node in bake_nodes.items():
            info = trigger_bake(name, source_obj, mod, bake_node)
            bake_infos[name] = info
            print(f"=== BAKE INFO ({name}) ===")
            print(json.dumps(info, indent=2, default=str))

        animate_set_position(set_pos_node)

        out_path = export_cell(source_obj)
        results = run_assertions(out_path, CONFIG["total_points"], CONFIG["split_threshold"], cone_vert_count)
        report(stamp, CONFIG, bake_infos, results)
    except Exception as e:
        report(stamp, CONFIG, bake_infos, {}, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
