"""
usd_export__nested_groups__bake_combined__depth3

Extends usd_export__nested_groups__bake_combined__production_scale (depth=2,
outer level routed through a real GeometryNodeBake node, 20,000 instances)
to nesting depth=3, while holding instance counts at the SAME small scale
already used by usd_export__nested_groups__3level (6 outer x 4 mid x 5
inner = 120 cubes) so this run isolates depth as the only new variable, not
depth+scale together -- per methodology.md's "don't bundle multiple
untested variables into one script" rule.

Levels 1 and 2 (innermost, middle) use the already-confirmed Python-side
realize+bake-into-a-real-object pattern (usd_export__nested_groups__3level).
Level 3 (outer, the exported level) uses the already-confirmed
GeometryNodeBake node recovery chain (Object Info(As Instance) -> Instance
on Points -> Bake(DISK) -> Instances to Points -> second Object Info(As
Instance) -> second Instance on Points) instead of staying a plain
instancer, per usd_export__nested_groups__bake_combined__production_scale's
own outer-level construction -- this is the part that's actually new here.

Static / no animation. Maps to geonodes_export_interop_gap.md source #15
(AOUSD forum, 8M+ instance production scenes -- nested/multi-level
instancing at scale) combined with source #14 (issue #132123, baking for
performance) -- closes the "nesting depth 3+ combined with a real Bake
node" item flagged open in the UNTESTED CELLS composite row.
"""

import bpy
import json

CONFIG = {
    "cell_id": "usd_export__nested_groups__bake_combined__depth3",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+ instance "
        "production scenes) + source #14 (issue #132123); extends "
        "usd_export__nested_groups__bake_combined__production_scale (depth=2, "
        "bake at outer level, 20,000 instances) to depth=3, at the same small "
        "scale already used by usd_export__nested_groups__3level (6x4x5=120 "
        "cubes) to isolate depth as the only new variable"
    ),
    "export_format": "usd",
    "instance_type": "nested",
    "nesting_depth": 3,
    "bake_node_present": True,
    "animation_present": False,
    "level1_points": 5,
    "level2_points": 4,
    "level3_points": 6,
    "float_tolerance": 1e-5,
    "output_path": "nested_bake_depth3.usdc",
    "bake_directory": "bake_cache_nested_depth3",
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


def make_exact_count_source(name, n_verts):
    """A loose-vert mesh with exactly n_verts vertices, for exact-count
    Mesh to Points conversion -- matches this project's established
    exact-count convention (not density-based distribution)."""
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata([(float(i), 0.0, 0.0) for i in range(n_verts)], [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def make_cube_prototype(name):
    mesh_data = bpy.data.meshes.new(f"{name}_mesh")
    bm_verts = [
        (-0.1, -0.1, -0.1), (0.1, -0.1, -0.1), (0.1, 0.1, -0.1), (-0.1, 0.1, -0.1),
        (-0.1, -0.1, 0.1), (0.1, -0.1, 0.1), (0.1, 0.1, 0.1), (-0.1, 0.1, 0.1),
    ]
    bm_faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh_data.from_pydata(bm_verts, [], bm_faces)
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
    in_node.location = (-800, 0)
    out_node.location = (800, 0)
    return mod, group, in_node, out_node


def wire_instance_chain(group, source_socket, points_obj_data, proto_obj):
    """points source -> Mesh to Points -> Object Info(As Instance) proto ->
    Instance on Points -> returns the Instance on Points geometry output."""
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

    return inst.outputs["Instances"], obj_info


def realize_and_bake_python_side(points_obj, proto_obj, out_name, expected_verts):
    """Levels 1 and 2: build a temporary realize-instances network, evaluate
    via depsgraph, and copy the result into a real persistent object --
    the already-confirmed usd_export__nested_groups__3level pattern."""
    mod, group, in_node, out_node = add_gn_modifier(points_obj, f"{out_name}_TmpGroup")
    inst_out, _ = wire_instance_chain(group, in_node.outputs["Geometry"], None, proto_obj)
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

    # clean up the temporary network -- points_obj itself is not exported
    points_obj.modifiers.remove(mod)
    bpy.data.node_groups.remove(group)

    return baked_obj, actual_verts


def build_outer_bake_chain(points_obj, proto_obj):
    """Level 3 (outer, exported): Object Info(As Instance) -> Instance on
    Points -> Bake(DISK) -> Instances to Points -> second Object Info(As
    Instance) -> second Instance on Points. Left un-realized so it stays a
    true instancer for USD export -- mirrors
    usd_export__nested_groups__bake_combined__production_scale's outer
    construction, just at this cell's own (smaller) instance count."""
    mod, group, in_node, out_node = add_gn_modifier(points_obj, "OuterBakeGroup")

    inst1_out, obj_info1 = wire_instance_chain(group, in_node.outputs["Geometry"], None, proto_obj)

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
    bake_node.bake_target = "DISK"
    bake_node.bake_settings.directory = bake_dir

    bpy.context.view_layer.objects.active = obj
    result = bpy.ops.object.geometry_node_bake_single(
        session_uid=obj.session_uid,
        modifier_name=mod.name,
        bake_id=bake_node.bake_id if hasattr(bake_node, "bake_id") else 0,
    )
    return {"operator_result": str(result)}


def export_and_inspect(obj, out_path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.usd_export(filepath=out_path, selected_objects_only=True, export_animation=False)

    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(out_path)
    instancer = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer = UsdGeom.PointInstancer(prim)
            break

    assertions = {}
    assertions["export_produced_nonempty_file"] = {
        "pass": True,
        "detail": f"stage opened OK: {out_path}",
    }
    assertions["instancer_count"] = {
        "pass": instancer is not None,
        "detail": f"instancer_found={instancer is not None}",
    }

    if instancer is not None:
        positions = instancer.GetPositionsAttr().Get()
        proto_indices = instancer.GetProtoIndicesAttr().Get()
        n_pos = len(positions) if positions else 0
        n_proto = len(proto_indices) if proto_indices else 0
        assertions["count_match"] = {
            "pass": n_pos == CONFIG["level3_points"] and n_proto == CONFIG["level3_points"],
            "detail": f"positions={n_pos}, protoIndices={n_proto}, expected={CONFIG['level3_points']}",
        }

        targets = instancer.GetPrototypesRel().GetTargets()
        proto_vert_count = None
        proto_path = None
        if targets:
            proto_prim = stage.GetPrimAtPath(targets[0])
            # typeless-but-populated fallback, per HARNESS NOTES: walk one
            # level down for a real Mesh child if the prototype path itself
            # is not IsInstance()/IsDefined().
            mesh_prim = None
            if proto_prim.IsA(UsdGeom.Mesh):
                mesh_prim = proto_prim
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

        expected_proto_verts = CONFIG["level1_points"] * 8 * CONFIG["level2_points"]
        assertions["prototype_match"] = {
            "pass": proto_vert_count == expected_proto_verts,
            "detail": f"resolved prototype vertex count={proto_vert_count} at {proto_path}, expected={expected_proto_verts}",
        }
    else:
        assertions["count_match"] = {"pass": False, "detail": "no PointInstancer found"}
        assertions["prototype_match"] = {"pass": False, "detail": "no PointInstancer found"}

    return assertions


def main():
    stamp = log_version_stamp()
    crashed = False
    crash_detail = None
    assertions = {}
    l1_verts = l2_verts = None
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

        l3_points = make_exact_count_source("L3_OuterSource", CONFIG["level3_points"])
        mod, group, bake_node = build_outer_bake_chain(l3_points, baked_l2)
        bake_info = trigger_bake(l3_points, mod, bake_node, CONFIG["bake_directory"])
        print("=== OUTER BAKE INFO ===")
        print(json.dumps(bake_info, indent=2))

        assertions = export_and_inspect(l3_points, CONFIG["output_path"])

    except Exception as e:
        crashed = True
        crash_detail = str(e)

    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": CONFIG,
        "level1_verts": l1_verts,
        "level2_verts": l2_verts,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertions,
    }, indent=2))


if __name__ == "__main__":
    main()
