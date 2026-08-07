import bpy, os, json, math, sys, shutil

CELL_ID = "usd_export__animated_rotation__bake_combined__threshold_bisection_blender52_reverify"
TARGET_COUNT = 330  # smallest confirmed-defective count from the 5.0.1 session
OUT_USD = "/tmp/bisect330_blender52.usdc"
BAKE_DIR = "/tmp/bisect330_blender52_bake"

result = {
    "stamp": {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else bpy.app.build_hash,
        "cell_id": CELL_ID,
    },
    "config": {
        "cell_id": CELL_ID,
        "maps_to_source": "re-verification of usd_export__animated_rotation__bake_combined__threshold_bisection's 330-instance result, first test on Blender 5.2.0 LTS (never previously logged)",
        "export_format": "usd",
        "instance_type": "points",
        "bake_node_present": True,
        "animation_present": "rotation",
        "nesting_depth": 1,
        "num_points_target": TARGET_COUNT,
        "output_path": OUT_USD,
    },
    "crashed": False,
    "crash_detail": None,
    "assertions": {},
}

print("=== VERSION STAMP ===")
print(json.dumps(result["stamp"], indent=2))

try:
    # --- clean scene ---
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.mesh.primitive_plane_add(size=100, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "SourcePlane"

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    proto = bpy.context.active_object
    proto.name = "ProtoCube"
    proto.hide_render = True
    proto.hide_viewport = True

    mod = plane.modifiers.new("GN_Bisect330_52", 'NODES')
    group = bpy.data.node_groups.new("Bisect330_52_Group", 'GeometryNodeTree')
    mod.node_group = group
    group.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nodes = group.nodes
    links = group.links
    nodes.clear()

    n_in = nodes.new("NodeGroupInput")
    n_out = nodes.new("NodeGroupOutput")

    dpof = nodes.new("GeometryNodeDistributePointsOnFaces")
    dpof.distribute_method = 'RANDOM'

    objinfo1 = nodes.new("GeometryNodeObjectInfo")
    objinfo1.inputs['Object'].default_value = proto
    objinfo1.inputs['As Instance'].default_value = True
    objinfo1.transform_space = 'RELATIVE'

    iop1 = nodes.new("GeometryNodeInstanceOnPoints")

    links.new(n_in.outputs['Geometry'], dpof.inputs['Mesh'])
    links.new(dpof.outputs['Points'], iop1.inputs['Points'])
    links.new(objinfo1.outputs['Geometry'], iop1.inputs['Instance'])

    # --- calibrate density to hit TARGET_COUNT exactly, via temp probe ---
    p2v = nodes.new("GeometryNodePointsToVertices")
    links.new(dpof.outputs['Points'], p2v.inputs['Points'])
    links.new(p2v.outputs['Mesh'], n_out.inputs['Geometry'])

    def count_points(density):
        dpof.inputs['Density'].default_value = density
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = plane.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        n = len(mesh.vertices)
        eval_obj.to_mesh_clear()
        return n

    lo, hi = 0.001, 0.2
    for _ in range(40):
        mid = (lo + hi) / 2
        n = count_points(mid)
        if n < TARGET_COUNT:
            lo = mid
        elif n > TARGET_COUNT:
            hi = mid
        else:
            break

    final_density = dpof.inputs['Density'].default_value
    ground_truth_count = count_points(final_density)
    nodes.remove(p2v)

    # --- wire full bake-recovery + rotation chain ---
    bake = nodes.new("GeometryNodeBake")
    bake.bake_items.new('GEOMETRY', 'geometry')

    i2p = nodes.new("GeometryNodeInstancesToPoints")

    objinfo2 = nodes.new("GeometryNodeObjectInfo")
    objinfo2.inputs['Object'].default_value = proto
    objinfo2.inputs['As Instance'].default_value = True
    objinfo2.transform_space = 'RELATIVE'

    iop2 = nodes.new("GeometryNodeInstanceOnPoints")

    links.new(iop1.outputs['Instances'], bake.inputs['geometry'])
    links.new(bake.outputs['geometry'], i2p.inputs['Instances'])
    links.new(i2p.outputs['Points'], iop2.inputs['Points'])
    links.new(objinfo2.outputs['Geometry'], iop2.inputs['Instance'])
    links.new(iop2.outputs['Instances'], n_out.inputs['Geometry'])

    # bake target: DISK
    bake_entry = mod.bakes[0]
    bake_entry.bake_target = 'DISK'
    bake_entry.use_custom_path = True
    os.makedirs(BAKE_DIR, exist_ok=True)
    bake_entry.directory = BAKE_DIR

    # rotation keyframes: padding frame 4 holds (0,0,0) from frame 5, animate to 90deg at frame 24
    rot_socket = iop2.inputs['Rotation']
    scene = bpy.context.scene
    scene.frame_start = 4
    scene.frame_end = 24

    def set_rot_kf(frame, deg_z):
        rot_socket.default_value = (0.0, 0.0, math.radians(deg_z))
        rot_socket.keyframe_insert("default_value", frame=frame)

    set_rot_kf(4, 0.0)
    set_rot_kf(5, 0.0)
    set_rot_kf(24, 90.0)

    # --- read true authored curve for comparison ---
    action = group.animation_data.action
    fc = None
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for f in cb.fcurves:
                    if f.array_index == 2:
                        fc = f
    true_curve = {frame: math.degrees(fc.evaluate(frame)) for frame in [4, 5, 6, 7, 10, 15, 24]}

    # --- export ---
    bpy.ops.object.select_all(action='DESELECT')
    plane.select_set(True)
    proto.select_set(True)
    bpy.context.view_layer.objects.active = plane

    if os.path.exists(OUT_USD):
        os.remove(OUT_USD)

    bpy.ops.wm.usd_export(
        filepath=OUT_USD,
        selected_objects_only=False,
        export_animation=True,
        use_instancing=True,
    )

    export_ok = os.path.exists(OUT_USD) and os.path.getsize(OUT_USD) > 0
    result["config"]["ground_truth_point_count"] = ground_truth_count
    result["config"]["export_file_size_bytes"] = os.path.getsize(OUT_USD) if export_ok else 0
    result["config"]["true_curve_deg"] = true_curve

    result["assertions"]["export_produced_nonempty_file"] = {
        "pass": export_ok,
        "detail": f"size={os.path.getsize(OUT_USD) if export_ok else 0} bytes",
    }

    # --- inspect via pxr if available inside Blender's python ---
    try:
        from pxr import Usd, UsdGeom
        pxr_available = True
    except ImportError:
        pxr_available = False

    if not pxr_available:
        result["assertions"]["pxr_inspection"] = {
            "pass": None,
            "detail": "pxr.Usd not importable inside this Blender's bundled Python -- structural/orientation assertions could not be run in-process. Export file was produced; needs external pxr-based inspection.",
        }
    else:
        stage = Usd.Stage.Open(OUT_USD)
        instancer_prim = None
        for prim in stage.Traverse():
            if prim.IsA(UsdGeom.PointInstancer):
                instancer_prim = prim
                break

        if instancer_prim is None:
            result["assertions"]["count_match"] = {"pass": False, "detail": "no PointInstancer found in exported stage"}
        else:
            instancer = UsdGeom.PointInstancer(instancer_prim)
            positions = instancer.GetPositionsAttr().Get(4)
            protoidx = instancer.GetProtoIndicesAttr().Get(4)
            n_pos = len(positions) if positions else 0
            n_proto = len(protoidx) if protoidx else 0

            result["assertions"]["count_match"] = {
                "pass": (n_pos == ground_truth_count and n_proto == ground_truth_count),
                "detail": f"positions={n_pos}, protoIndices={n_proto}, ground_truth={ground_truth_count}",
            }

            orient_attr = instancer.GetOrientationsAttr()
            time_samples = orient_attr.GetTimeSamples()
            expected_full_range = [4.0, 5.0] + [float(f) for f in range(6, 24)] + [24.0]
            transform_clean = (set(time_samples) == set(expected_full_range))

            frame6_val = orient_attr.Get(6)
            frame24_val = orient_attr.Get(24)
            frame23_val = orient_attr.Get(23)

            result["assertions"]["transform_match"] = {
                "pass": transform_clean,
                "detail": (
                    f"orientations.GetTimeSamples()={time_samples}; "
                    f"frame6={frame6_val}; frame23={frame23_val}; frame24={frame24_val}; "
                    f"frame24==frame23: {frame24_val == frame23_val if (frame24_val is not None and frame23_val is not None) else None}"
                ),
            }

except Exception as e:
    import traceback
    result["crashed"] = True
    result["crash_detail"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

print("=== CELL RESULT ===")
print(json.dumps(result, indent=2, default=str))
