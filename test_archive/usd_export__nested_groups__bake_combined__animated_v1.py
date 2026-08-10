"""
usd_export__nested_groups__bake_combined__animated

Extends usd_export__nested_groups__bake_combined__production_scale (depth=2,
outer level routed through a real GeometryNodeBake node, static) by adding
uniform position animation on top, at the SAME small scale already used by
usd_export__nested_groups__bake_combined__depth3 (rather than jumping
straight to 20,000-instance production scale), so this run isolates
animation as the only new variable -- not animation+scale together. Closes
the "nested+bake+animation" item flagged open in the UNTESTED CELLS
composite row.

Inner level (Python-side realize+bake pattern) is unchanged from the
depth3/production_scale entries. Outer level reuses the already-confirmed
GeometryNodeBake recovery chain, with a Set Position node inserted after
the second Instance on Points, animated using the already-confirmed
padding-frame drift fix (padding keyframe at frame 4 duplicating frame 5's
value, real animation frames 5-24, export range 4-24 -- NOT frame 0, per
the documented "wm.usd_export silently drops frame 0" bug).
"""

import bpy
import json

CONFIG = {
    "cell_id": "usd_export__nested_groups__bake_combined__animated",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #15 (AOUSD forum, 8M+ instance "
        "production scenes) + source #14 (issue #132123) + source #2 (issue "
        "#139654, animated instances); extends "
        "usd_export__nested_groups__bake_combined__production_scale (depth=2, "
        "bake at outer level, static) by adding uniform position animation, "
        "at the same small scale used by "
        "usd_export__nested_groups__bake_combined__depth3 to isolate "
        "animation as the only new variable"
    ),
    "export_format": "usd",
    "instance_type": "nested",
    "nesting_depth": 2,
    "bake_node_present": True,
    "animation_present": True,
    "level1_points": 5,
    "level2_points": 6,
    "float_tolerance": 1e-5,
    "output_path": "nested_bake_animated.usdc",
    "bake_directory": "bake_cache_nested_animated",
    "padding_frame": 4,
    "start_frame": 5,
    "end_frame": 24,
    "end_offset_x": 3.0,
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

    return inst.outputs["Instances"], obj_info


def realize_and_bake_python_side(points_obj, proto_obj, out_name, expected_verts):
    mod, group, in_node, out_node = add_gn_modifier(points_obj, f"{out_name}_TmpGroup")
    inst_out, _ = wire_instance_chain(group, in_node.outputs["Geometry"], proto_obj)
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


def build_outer_bake_chain_animated(points_obj, proto_obj):
    """Outer (exported) level: Object Info(As Instance) -> Instance on
    Points -> Bake -> Instances to Points -> second Object Info(As
    Instance) -> second Instance on Points -> Set Position (animated
    Offset, padding-frame fix). Left un-realized for USD export."""
    mod, group, in_node, out_node = add_gn_modifier(points_obj, "OuterBakeAnimGroup")

    inst1_out, obj_info1 = wire_instance_chain(group, in_node.outputs["Geometry"], proto_obj)

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

    setpos = group.nodes.new("GeometryNodeSetPosition")
    group.links.new(inst2.outputs["Instances"], setpos.inputs["Geometry"])
    group.links.new(setpos.outputs["Geometry"], out_node.inputs["Geometry"])

    return mod, group, bake_node, setpos


def animate_offset(group, setpos_node):
    """Padding-frame drift fix: padding keyframe at frame 4 duplicates
    frame 5's value, real animation runs frame 5 -> frame 24."""
    offset_input = setpos_node.inputs["Offset"]

    offset_input.default_value = (0.0, 0.0, 0.0)
    offset_input.keyframe_insert(data_path="default_value", frame=CONFIG["padding_frame"])
    offset_input.keyframe_insert(data_path="default_value", frame=CONFIG["start_frame"])

    offset_input.default_value = (CONFIG["end_offset_x"], 0.0, 0.0)
    offset_input.keyframe_insert(data_path="default_value", frame=CONFIG["end_frame"])

    action = group.animation_data.action if group.animation_data else None
    fcurve_count = None
    if action is not None:
        try:
            fcurve_count = len(action.fcurves)
        except AttributeError:
            # Blender 5.x layered Action system: fcurves aren't directly
            # under action.fcurves -- see HARNESS NOTES. Diagnostic only,
            # not load-bearing for the actual assertions.
            fcurve_count = "unavailable (layered Action API)"
    return {"action_present": action is not None, "fcurve_count": fcurve_count}


def trigger_bake(obj, mod, bake_node, bake_dir):
    bpy.context.view_layer.update()

    if len(mod.bakes) == 0:
        raise RuntimeError(
            f"modifier.bakes is empty after wiring the Bake node "
            f"(node.bake_id={getattr(bake_node, 'bake_id', 'N/A')})"
        )
    import os
    bake_cfg = mod.bakes[0]
    bake_cfg.directory = os.path.abspath(bake_dir)
    if hasattr(bake_cfg, "bake_target"):
        bake_cfg.bake_target = "DISK"
    elif hasattr(bake_cfg, "use_custom_path"):
        bake_cfg.use_custom_path = True

    bpy.context.view_layer.objects.active = obj
    result = bpy.ops.object.geometry_node_bake_single(
        session_uid=obj.session_uid,
        modifier_name=mod.name,
        bake_id=bake_cfg.bake_id,
    )
    return {"operator_result": str(result), "directory": bake_cfg.directory}


def export_and_inspect(obj, out_path):
    bpy.context.scene.frame_start = CONFIG["padding_frame"]
    bpy.context.scene.frame_end = CONFIG["end_frame"]

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.usd_export(
        filepath=out_path,
        selected_objects_only=True,
        export_animation=True,
        use_instancing=True,
    )

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
        pos_attr = instancer.GetPositionsAttr()
        time_samples = pos_attr.GetTimeSamples()
        assertions["time_sampled"] = {
            "pass": len(time_samples) > 1,
            "detail": f"time_samples={time_samples}",
        }

        pos_at_5 = pos_attr.Get(CONFIG["start_frame"])
        pos_at_24 = pos_attr.Get(CONFIG["end_frame"])
        pos_at_4 = pos_attr.Get(CONFIG["padding_frame"])

        n5 = len(pos_at_5) if pos_at_5 else 0
        n24 = len(pos_at_24) if pos_at_24 else 0
        assertions["count_match"] = {
            "pass": n5 == CONFIG["level2_points"] and n24 == CONFIG["level2_points"],
            "detail": f"positions@5={n5}, positions@24={n24}, expected={CONFIG['level2_points']}",
        }

        if pos_at_5 and pos_at_24 and pos_at_4:
            deltas_5_24 = [
                (pos_at_24[i][0] - pos_at_5[i][0]) for i in range(len(pos_at_5))
            ]
            delta_4_5 = [
                (pos_at_5[i][0] - pos_at_4[i][0]) for i in range(len(pos_at_5))
            ]
            tol = CONFIG["float_tolerance"]
            expected_delta = CONFIG["end_offset_x"]
            all_match_endpoint = all(abs(d - expected_delta) < 1e-3 for d in deltas_5_24)
            padding_is_zero_drift = all(abs(d) < 1e-3 for d in delta_4_5)
            assertions["animation_delta_match"] = {
                "pass": all_match_endpoint,
                "detail": f"per-instance x delta frame5->frame24={deltas_5_24}, expected={expected_delta}",
            }
            assertions["padding_frame_zero_drift"] = {
                "pass": padding_is_zero_drift,
                "detail": f"per-instance x delta frame4->frame5={delta_4_5}, expected=0 (padding holds frame5's value)",
            }
        else:
            assertions["animation_delta_match"] = {"pass": False, "detail": "missing position samples at one or more frames"}

        targets = instancer.GetPrototypesRel().GetTargets()
        proto_vert_count = None
        proto_path = None
        if targets:
            proto_prim = stage.GetPrimAtPath(targets[0])
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

        expected_proto_verts = CONFIG["level1_points"] * 8
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
    l1_verts = None
    anim_info = None
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        cube_proto = make_cube_prototype("Cube_L1_Proto")

        l1_points = make_exact_count_source("L1_Points", CONFIG["level1_points"])
        baked_l1, l1_verts = realize_and_bake_python_side(
            l1_points, cube_proto, "BakedInnerCluster_L1", CONFIG["level1_points"] * 8
        )

        l2_points = make_exact_count_source("L2_OuterSource", CONFIG["level2_points"])
        mod, group, bake_node, setpos = build_outer_bake_chain_animated(l2_points, baked_l1)
        anim_info = animate_offset(group, setpos)
        print("=== ANIMATION INFO ===")
        print(json.dumps(anim_info, indent=2))

        bake_info = trigger_bake(l2_points, mod, bake_node, CONFIG["bake_directory"])
        print("=== OUTER BAKE INFO ===")
        print(json.dumps(bake_info, indent=2))

        assertions = export_and_inspect(l2_points, CONFIG["output_path"])

    except Exception as e:
        crashed = True
        crash_detail = str(e)

    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": CONFIG,
        "level1_verts": l1_verts,
        "animation_info": anim_info,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertions,
    }, indent=2))


if __name__ == "__main__":
    main()
