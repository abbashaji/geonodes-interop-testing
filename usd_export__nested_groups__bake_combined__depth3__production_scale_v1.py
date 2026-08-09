"""
Cell: usd_export__nested_groups__bake_combined__depth3__production_scale
Maps to: geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+
instance production scenes -- nested/multi-level instancing at scale)
combined with source #14 (issue #132123, baking for performance). Extends
usd_export__nested_groups__bake_combined__depth3 (CONFIRMED WORKING, real
Bake node at depth=3, small scale: 6x4x5=120 cubes) to 20,000-instance
production scale at the OUTER (exported) level only, holding levels 1 and
2's small counts fixed -- isolates scale as the only new variable, same
discipline already used to go from usd_export__nested_groups__bake_
combined__production_scale (depth=2) to _depth3 (depth=3, small scale) in
the first place. Closes the last remaining item in the UNTESTED CELLS
composite row: "depth-3 nesting+bake at production/extreme scale".

Levels 1 and 2 (innermost, middle) reuse the already-confirmed Python-side
realize+bake-into-a-real-object pattern (usd_export__nested_groups__
3level / _depth3), unchanged at 5 and 4 points respectively -- these are
NOT the exported level, so scaling them isn't what this cell tests.
Level 3 (outer, exported) uses the established GeometryNodeBake recovery
chain (Object Info(As Instance) -> Instance on Points -> Bake(DISK) ->
Instances to Points -> second Object Info(As Instance) -> second Instance
on Points), scaled to 20,000 exact-count points via the same grid-mesh
convention used by every other production-scale cell in this pipeline,
with the bake independently verified via real on-disk cache JSON (not
just "operator returned FINISHED"), per the standing depth3 caveat that a
directory-set bake can still silently fall back to packed.

Static / no animation.
"""

import bpy
import bmesh
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__nested_groups__bake_combined__depth3__production_scale",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+ "
        "instance production scenes) + source #14 (issue #132123); "
        "extends usd_export__nested_groups__bake_combined__depth3 "
        "(CONFIRMED WORKING, depth=3, small scale 6x4x5=120 cubes) to "
        "20,000-instance production scale at the outer level only"
    ),
    "export_format": "usd",
    "instance_type": "nested",
    "nesting_depth": 3,
    "bake_node_present": True,
    "animation_present": False,
    "level1_points": 5,   # unchanged from the small-scale depth3 cell
    "level2_points": 4,   # unchanged from the small-scale depth3 cell
    "level3_points": 20000,  # production scale, outer/exported level only
    "float_tolerance": 1e-5,
    "output_path": os.path.join(os.getcwd(), "nested_bake_depth3_20k.usdc"),
    "bake_directory": os.path.join(os.getcwd(), "bake_cache_nested_depth3_20k"),
}


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
# BUILD -- small exact-count source (levels 1 & 2, unchanged small scale)
# =====================================================================
def make_exact_count_source(name, n_verts):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata([(float(i), 0.0, 0.0) for i in range(n_verts)], [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def make_cube_prototype(name):
    mesh_data = bpy.data.meshes.new(f"{name}_mesh")
    verts = [
        (-0.1, -0.1, -0.1), (0.1, -0.1, -0.1), (0.1, 0.1, -0.1), (-0.1, 0.1, -0.1),
        (-0.1, -0.1, 0.1), (0.1, -0.1, 0.1), (0.1, 0.1, 0.1), (-0.1, 0.1, 0.1),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh_data.from_pydata(verts, [], faces)
    mesh_data.update()
    obj = bpy.data.objects.new(name, mesh_data)
    bpy.context.collection.objects.link(obj)
    return obj


def add_gn_modifier(obj, group_name):
    mod = obj.modifiers.new("GeometryNodes", "NODES")
    group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")
    mod.node_group = group
    group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    in_node = group.nodes.new("NodeGroupInput")
    out_node = group.nodes.new("NodeGroupOutput")
    return mod, group, in_node, out_node


def wire_instance_chain(group, source_socket, proto_obj):
    m2p = group.nodes.new("GeometryNodeMeshToPoints")
    m2p.mode = "VERTICES"

    obj_info = group.nodes.new("GeometryNodeObjectInfo")
    obj_info.transform_space = "RELATIVE"
    obj_info.inputs["Object"].default_value = proto_obj
    obj_info.inputs["As Instance"].default_value = True

    inst = group.nodes.new("GeometryNodeInstanceOnPoints")

    group.links.new(source_socket, m2p.inputs["Mesh"])
    group.links.new(m2p.outputs["Points"], inst.inputs["Points"])
    group.links.new(obj_info.outputs["Geometry"], inst.inputs["Instance"])

    return inst.outputs["Instances"]


def realize_and_bake_python_side(points_obj, proto_obj, out_name, expected_verts):
    """Levels 1 and 2: the already-confirmed realize+bake-into-a-real-
    object pattern, unchanged small scale."""
    mod, group, in_node, out_node = add_gn_modifier(points_obj, f"{out_name}_TmpGroup")
    inst_out = wire_instance_chain(group, in_node.outputs["Geometry"], proto_obj)
    realize = group.nodes.new("GeometryNodeRealizeInstances")
    group.links.new(inst_out, realize.inputs["Geometry"])
    group.links.new(realize.outputs["Geometry"], out_node.inputs["Geometry"])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = points_obj.evaluated_get(depsgraph)
    eval_mesh = bpy.data.meshes.new_from_object(eval_obj)

    baked_obj = bpy.data.objects.new(out_name, eval_mesh)
    bpy.context.collection.objects.link(baked_obj)

    actual_verts = len(eval_mesh.vertices)
    print(f"=== {out_name} BAKED: {actual_verts} verts (expected {expected_verts}) ===")

    points_obj.modifiers.remove(mod)
    bpy.data.node_groups.remove(group)

    return baked_obj, actual_verts


# =====================================================================
# BUILD -- outer/exported level, production scale, real GeometryNodeBake
# =====================================================================
def build_outer_source_mesh(num_points):
    """Exact-count grid mesh, matching every other production-scale
    cell's convention (not the small-scale loose-vert-row convention used
    at levels 1/2)."""
    mesh = bpy.data.meshes.new("L3_OuterSource_mesh")
    bm = bmesh.new()
    cols = 200
    rows = num_points // cols
    assert rows * cols == num_points, "grid must divide exactly for exact count"
    spacing = 1.0
    for i in range(rows):
        for j in range(cols):
            bm.verts.new((j * spacing, i * spacing, 0.0))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("L3_OuterSource", mesh)
    bpy.context.collection.objects.link(obj)
    assert len(obj.data.vertices) == num_points
    return obj


def build_outer_bake_chain(points_obj, proto_obj):
    mod, group, in_node, out_node = add_gn_modifier(points_obj, "OuterBakeGroup")

    inst1_out = wire_instance_chain(group, in_node.outputs["Geometry"], proto_obj)

    bake_node = group.nodes.new("GeometryNodeBake")
    if len(bake_node.bake_items) == 0:
        bake_node.bake_items.new(socket_type="GEOMETRY", name="Geometry")
    group.links.new(inst1_out, bake_node.inputs["Geometry"])

    inst2points = group.nodes.new("GeometryNodeInstancesToPoints")
    group.links.new(bake_node.outputs["Geometry"], inst2points.inputs["Instances"])

    obj_info2 = group.nodes.new("GeometryNodeObjectInfo")
    obj_info2.transform_space = "RELATIVE"
    obj_info2.inputs["Object"].default_value = proto_obj
    obj_info2.inputs["As Instance"].default_value = True

    inst2 = group.nodes.new("GeometryNodeInstanceOnPoints")
    group.links.new(inst2points.outputs["Points"], inst2.inputs["Points"])
    group.links.new(obj_info2.outputs["Geometry"], inst2.inputs["Instance"])

    group.links.new(inst2.outputs["Instances"], out_node.inputs["Geometry"])

    return mod, group, bake_node


def trigger_bake(obj, mod, bake_node, bake_dir):
    bpy.context.view_layer.update()

    if len(mod.bakes) == 0:
        raise RuntimeError(
            f"modifier.bakes is empty after wiring the Bake node "
            f"(node.bake_id={getattr(bake_node, 'bake_id', 'N/A')})"
        )
    # NOTE (HARNESS NOTES): bake_cfg.directory (the per-bake-item field) is
    # NOT sufficient to route to disk -- Blender logs "Bake directory ...
    # is empty, setting default path" / "Cannot determine bake location on
    # disk. Falling back to packed bake." and silently packs instead, even
    # though bake_cfg.directory looks set. The field that actually routes
    # the bake to disk is the MODIFIER-level mod.bake_directory (matching
    # every other production-scale bake cell in this pipeline), not the
    # per-bake-item bake_cfg.directory used by the ORIGINAL small-scale
    # depth3 script -- that script's disk-bake was therefore likely never
    # actually verified either (it also never checked meta_dir_exists).
    os.makedirs(os.path.abspath(bake_dir), exist_ok=True)
    mod.bake_target = "DISK"
    mod.bake_directory = os.path.abspath(bake_dir)
    bake_cfg = mod.bakes[0]

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    result = bpy.ops.object.geometry_node_bake_single(
        session_uid=obj.session_uid,
        modifier_name=mod.name,
        bake_id=bake_cfg.bake_id,
    )

    # Independently verify via real on-disk cache JSON -- don't trust
    # "operator returned FINISHED" alone, per the standing depth3 caveat
    # that a directory-set bake can still silently fall back to packed.
    cache_info = {
        "operator_result": str(result),
        "bake_id": bake_cfg.bake_id,
        "directory_requested": bake_cfg.directory,
    }
    bake_root = os.path.join(os.path.abspath(bake_dir), str(bake_cfg.bake_id), "meta")
    cache_info["meta_dir_exists"] = os.path.isdir(bake_root)
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
# EXPORT + ASSERTIONS
# =====================================================================
def export_and_inspect(obj, out_path, expected_total, expected_proto_verts):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.usd_export(
        filepath=out_path,
        selected_objects_only=True,
        export_animation=False,
        use_instancing=True,
    )

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
        results["count_match"] = {"pass": False, "detail": "no PointInstancer found"}
        results["prototype_match"] = {"pass": False, "detail": "no PointInstancer found"}
        return results

    positions = instancer.GetPositionsAttr().Get()
    proto_indices = instancer.GetProtoIndicesAttr().Get()
    n_pos = len(positions) if positions else 0
    n_proto = len(proto_indices) if proto_indices else 0
    results["count_match"] = {
        "pass": n_pos == expected_total and n_proto == expected_total,
        "detail": f"positions={n_pos}, protoIndices={n_proto}, expected={expected_total}",
    }

    # Spot-check a sample for collapse/duplication artifacts at scale.
    sample_idx = list(range(0, expected_total, max(1, expected_total // 20)))[:20]
    duplicate_check = len(set(tuple(positions[i]) for i in sample_idx if i < len(positions)))
    results["spot_check_positions_not_all_identical"] = {
        "pass": duplicate_check > 1,
        "detail": f"{duplicate_check}/{len(sample_idx)} unique sampled positions",
    }

    # Prototype-geometry resolution -- per HARNESS NOTES, check both raw
    # and forwarded targets, don't assume static behaves like the small-
    # scale depth3 run without verifying.
    rel = instancer.GetPrototypesRel()
    raw_targets = rel.GetTargets()
    forwarded_targets = rel.GetForwardedTargets()
    targets = raw_targets if raw_targets else forwarded_targets

    proto_vert_count = None
    proto_path = None
    if targets:
        proto_prim = stage.GetPrimAtPath(targets[0])
        mesh_prim = None
        if proto_prim.IsA(UsdGeom.Mesh):
            mesh_prim = proto_prim
        elif proto_prim.IsInstance():
            proto_proto = proto_prim.GetPrototype()
            for child in proto_proto.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    mesh_prim = child
                    break
            if mesh_prim is None and proto_proto.IsA(UsdGeom.Mesh):
                mesh_prim = proto_proto
        else:
            for child in proto_prim.GetAllChildren():
                if child.IsA(UsdGeom.Mesh):
                    mesh_prim = child
                    break
        if mesh_prim is not None:
            mesh = UsdGeom.Mesh(mesh_prim)
            pts = mesh.GetPointsAttr().Get()
            proto_vert_count = len(pts) if pts else 0
            proto_path = str(mesh_prim.GetPath())

    results["prototype_match"] = {
        "pass": proto_vert_count == expected_proto_verts,
        "detail": f"used_targets={'raw' if raw_targets else 'forwarded'}, "
                  f"resolved prototype vertex count={proto_vert_count} at {proto_path}, "
                  f"expected={expected_proto_verts}",
    }

    return results


def report(stamp, config, outer_bake_info, l1_verts, l2_verts, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "outer_bake_info": outer_bake_info,
        "level1_verts": l1_verts,
        "level2_verts": l2_verts,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def main():
    stamp = log_version_stamp()
    outer_bake_info = None
    l1_verts = l2_verts = None
    assertions = {}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        cube_proto = make_cube_prototype("Cube_L1_Proto")

        l1_points = make_exact_count_source("L1_Points", CONFIG["level1_points"])
        baked_l1, l1_verts = realize_and_bake_python_side(
            l1_points, cube_proto, "BakedInnerCluster_L1", CONFIG["level1_points"] * 8
        )

        l2_points = make_exact_count_source("L2_Points", CONFIG["level2_points"])
        baked_l2, l2_verts = realize_and_bake_python_side(
            l2_points, baked_l1, "BakedMidCluster_L2", CONFIG["level2_points"] * l1_verts
        )

        l3_points = build_outer_source_mesh(CONFIG["level3_points"])
        mod, group, bake_node = build_outer_bake_chain(l3_points, baked_l2)
        outer_bake_info = trigger_bake(l3_points, mod, bake_node, CONFIG["bake_directory"])
        print("=== OUTER BAKE INFO ===")
        print(json.dumps(outer_bake_info, indent=2, default=str))

        expected_proto_verts = l2_verts  # the outer level's prototype IS the level-2 baked object
        assertions = export_and_inspect(
            l3_points, CONFIG["output_path"], CONFIG["level3_points"], expected_proto_verts
        )
        report(stamp, CONFIG, outer_bake_info, l1_verts, l2_verts, assertions)
    except Exception as e:
        report(stamp, CONFIG, outer_bake_info, l1_verts, l2_verts, assertions, crashed=True, crash_detail=repr(e))
        raise


if __name__ == "__main__":
    main()
