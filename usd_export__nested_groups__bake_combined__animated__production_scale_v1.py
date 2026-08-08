"""
Cell: usd_export__nested_groups__bake_combined__animated__production_scale
Extends usd_export__nested_groups__bake_combined__animated (small scale, depth=2,
6 outer instances) to 20,000-instance production scale, and separately
investigates the prototype-geometry resolution failure left open by that
small-scale run (GetPrototypesRel().GetTargets() returned empty).
"""

import bpy
import json

CONFIG = {
    "cell_id": "usd_export__nested_groups__bake_combined__animated__production_scale",
    "maps_to_source": "geonodes_export_interop_gap.md source #15 (AOUSD 8M+ production scenes) "
                       "+ source #14 (issue #132123, baking) + source #2 (issue #139654, animated instances)",
    "export_format": "usd",
    "instance_type": "nested",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 2,
    "float_tolerance": 1e-5,
    "output_path": "/tmp/nested_bake_animated_production_scale",
    "n_outer_points": 200 * 100,  # 20,000, exact by construction
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


def build_inner_cluster():
    """Level 1 (not exported): 5 exact points -> Cube instances -> realized
    into a persistent BakedInnerCluster object (40 vertices = 5 x 8-vert Cube),
    matching every prior nested+bake entry's Level-1 construction exactly."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 1000))
    cube_obj = bpy.context.active_object
    cube_obj.name = "L1_Cube_Prototype"

    src_mesh = bpy.data.meshes.new("L1_Source_mesh")
    verts = [(i * 2.0, 0.0, 1000.0) for i in range(5)]
    src_mesh.from_pydata(verts, [], [])
    src_mesh.update()
    src_obj = bpy.data.objects.new("L1_Source", src_mesh)
    bpy.context.collection.objects.link(src_obj)

    mod = src_obj.modifiers.new("GN_L1", "NODES")
    ng = bpy.data.node_groups.new("L1_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    n_input = ng.nodes.new("NodeGroupInput")
    n_output = ng.nodes.new("NodeGroupOutput")
    n_objinfo = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo.inputs["Object"].default_value = cube_obj
    n_objinfo.inputs["As Instance"].default_value = True
    n_iop = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_realize = ng.nodes.new("GeometryNodeRealizeInstances")

    links = ng.links
    links.new(n_input.outputs["Geometry"], n_iop.inputs["Points"])
    links.new(n_objinfo.outputs["Geometry"], n_iop.inputs["Instance"])
    links.new(n_iop.outputs["Instances"], n_realize.inputs["Geometry"])
    links.new(n_realize.outputs["Geometry"], n_output.inputs["Geometry"])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    src_eval = src_obj.evaluated_get(depsgraph)
    eval_mesh = bpy.data.meshes.new_from_object(src_eval)

    baked_obj = bpy.data.objects.new("BakedInnerCluster", eval_mesh)
    bpy.context.collection.objects.link(baked_obj)

    n_verts = len(eval_mesh.vertices)
    print(f"=== LEVEL 1 BAKE: BakedInnerCluster vertex count = {n_verts} (expected 40) ===")

    bpy.data.objects.remove(src_obj, do_unlink=True)
    bpy.data.objects.remove(cube_obj, do_unlink=True)

    return baked_obj, n_verts


def build_outer_scene(baked_obj):
    """Level 2 (exported): 20,000-point exact-count scatter, through the
    established GeometryNodeBake recovery chain, with an animated Set
    Position applying the padding-frame drift fix on top."""
    grid_x, grid_y = 200, 100
    n_points = grid_x * grid_y

    mesh = bpy.data.meshes.new("Outer_Source_mesh")
    verts = [(x * 1.0, y * 1.0, 0.0) for y in range(grid_y) for x in range(grid_x)]
    mesh.from_pydata(verts, [], [])
    mesh.update()
    obj = bpy.data.objects.new("Outer_Source", mesh)
    bpy.context.collection.objects.link(obj)

    mod = obj.modifiers.new("GN_Outer", "NODES")
    ng = bpy.data.node_groups.new("Outer_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    n_input = ng.nodes.new("NodeGroupInput")
    n_output = ng.nodes.new("NodeGroupOutput")

    n_m2p = ng.nodes.new("GeometryNodeMeshToPoints")
    n_m2p.mode = 'VERTICES'

    n_objinfo1 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo1.inputs["Object"].default_value = baked_obj
    n_objinfo1.inputs["As Instance"].default_value = True
    n_iop1 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    n_bake = ng.nodes.new("GeometryNodeBake")
    n_bake.bake_items.new(socket_type="GEOMETRY", name="Geometry")

    n_i2p = ng.nodes.new("GeometryNodeInstancesToPoints")

    n_objinfo2 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo2.inputs["Object"].default_value = baked_obj
    n_objinfo2.inputs["As Instance"].default_value = True
    n_iop2 = ng.nodes.new("GeometryNodeInstanceOnPoints")

    n_setpos = ng.nodes.new("GeometryNodeSetPosition")

    links = ng.links
    links.new(n_input.outputs["Geometry"], n_m2p.inputs["Mesh"])
    links.new(n_m2p.outputs["Points"], n_iop1.inputs["Points"])
    links.new(n_objinfo1.outputs["Geometry"], n_iop1.inputs["Instance"])
    links.new(n_iop1.outputs["Instances"], n_bake.inputs["Geometry"])
    links.new(n_bake.outputs["Geometry"], n_i2p.inputs["Instances"])
    links.new(n_i2p.outputs["Points"], n_iop2.inputs["Points"])
    links.new(n_objinfo2.outputs["Geometry"], n_iop2.inputs["Instance"])
    links.new(n_iop2.outputs["Instances"], n_setpos.inputs["Geometry"])
    links.new(n_setpos.outputs["Geometry"], n_output.inputs["Geometry"])

    # --- Trigger the outer-level bake ---
    # Note: the GeometryNodeBake node itself has no `bake_id` attribute in
    # this Blender version -- only modifier.bakes[i] does. Since this node
    # group has exactly one Bake node, modifier.bakes[0] is unambiguous.
    bpy.context.view_layer.update()
    assert len(mod.bakes) == 1, f"expected exactly 1 bake entry on the modifier, got {len(mod.bakes)}"
    bake_cfg = mod.bakes[0]
    bake_cfg.directory = "/tmp/outer_bake_cache_prod_scale"

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bake_result = bpy.ops.object.geometry_node_bake_single(
        session_uid=obj.session_uid, modifier_name=mod.name, bake_id=bake_cfg.bake_id
    )
    print(f"=== BAKE TRIGGER RESULT: {bake_result} ===")
    print(f"=== BAKE CFG AFTER TRIGGER: directory={bake_cfg.directory} ===")

    # --- Animate Set Position offset: padding-frame drift fix ---
    offset_socket = n_setpos.inputs["Offset"]
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

    return obj, n_points


def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.usdc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.usd_export(
        filepath=out_path,
        selected_objects_only=True,
        use_instancing=True,
        export_animation=True,
    )
    return out_path


def run_assertions(out_path, ground_truth_count, inner_vert_count):
    from pxr import Usd, UsdGeom

    results = {}
    stage = Usd.Stage.Open(out_path)

    instancer_prim = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer_prim = prim
            break

    if instancer_prim is None:
        results["instancer_found"] = {"pass": False, "detail": "No PointInstancer prim in exported stage at all"}
        return results

    instancer = UsdGeom.PointInstancer(instancer_prim)
    results["instancer_found"] = {"pass": True, "detail": str(instancer_prim.GetPath())}

    # --- Count match (positions + protoIndices, at frame 5 and frame 24) ---
    positions_attr = instancer.GetPositionsAttr()
    proto_indices_attr = instancer.GetProtoIndicesAttr()

    pos_f4 = positions_attr.Get(4)
    pos_f5 = positions_attr.Get(5)
    pos_f24 = positions_attr.Get(24)
    proto_indices = proto_indices_attr.Get(5)

    count_f5 = len(pos_f5) if pos_f5 else 0
    count_f24 = len(pos_f24) if pos_f24 else 0
    proto_count = len(proto_indices) if proto_indices else 0

    results["count_match"] = {
        "pass": (count_f5 == ground_truth_count and count_f24 == ground_truth_count
                  and proto_count == ground_truth_count),
        "detail": f"ground_truth={ground_truth_count}, frame5_positions={count_f5}, "
                  f"frame24_positions={count_f24}, protoIndices={proto_count}",
    }

    proto_indices_all_zero = proto_indices is not None and all(pi == 0 for pi in proto_indices)
    results["proto_indices_single_prototype"] = {
        "pass": proto_indices_all_zero,
        "detail": "all protoIndex==0 expected (single shared prototype)",
    }

    # --- Timing/drift: spot-check first, middle, last instance ---
    sample_indices = [0, ground_truth_count // 2, ground_truth_count - 1]
    tol = CONFIG["float_tolerance"]

    padding_drift_ok = True
    padding_details = []
    delta_ok = True
    delta_details = []

    if pos_f4 and pos_f5 and pos_f24:
        for i in sample_indices:
            d4 = pos_f4[i]
            d5 = pos_f5[i]
            d24 = pos_f24[i]
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

    # --- Prototype-geometry resolution (the dimension left open by the
    # small-scale animated run). Relationships are not time-varying in USD,
    # so instead of retrying at different UsdTimeCodes, check both the raw
    # and forwarded targets, and re-discover the instancer/prototype path
    # rather than assuming it matches the non-animated cell's layout. ---
    rel = instancer.GetPrototypesRel()
    raw_targets = rel.GetTargets()
    forwarded_targets = rel.GetForwardedTargets()

    resolved_vertex_count = None
    resolved_via = None
    resolved_path = None

    for label, targets in (("raw", raw_targets), ("forwarded", forwarded_targets)):
        for t in targets:
            p = stage.GetPrimAtPath(t)
            if not p:
                continue
            mesh_prim = None
            if p.IsInstance():
                proto_p = p.GetPrototype()
                for child in Usd.PrimRange(proto_p):
                    if child.IsA(UsdGeom.Mesh):
                        mesh_prim = child
                        break
            elif p.IsA(UsdGeom.Mesh):
                mesh_prim = p
            else:
                for child in Usd.PrimRange(p):
                    if child.IsA(UsdGeom.Mesh):
                        mesh_prim = child
                        break
            if mesh_prim is not None:
                pts = UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()
                resolved_vertex_count = len(pts) if pts else 0
                resolved_via = label
                resolved_path = str(mesh_prim.GetPath())
                break
        if resolved_vertex_count is not None:
            break

    results["prototype_geometry_resolution"] = {
        "pass": resolved_vertex_count == inner_vert_count,
        "detail": {
            "raw_targets": [str(t) for t in raw_targets],
            "forwarded_targets": [str(t) for t in forwarded_targets],
            "resolved_via": resolved_via,
            "resolved_path": resolved_path,
            "resolved_vertex_count": resolved_vertex_count,
            "expected_vertex_count": inner_vert_count,
        },
    }

    return results


def report(stamp, config, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, indent=2, default=str))


def main():
    stamp = log_version_stamp()
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        baked_obj, inner_vert_count = build_inner_cluster()
        outer_obj, ground_truth_count = build_outer_scene(baked_obj)
        out_path = export_cell(outer_obj)
        results = run_assertions(out_path, ground_truth_count, inner_vert_count)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
