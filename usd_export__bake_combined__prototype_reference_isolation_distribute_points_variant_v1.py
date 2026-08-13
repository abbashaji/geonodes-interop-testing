"""
Cell: usd_export__bake_combined__prototype_reference_isolation_distribute_points_variant
Script version: v1

Question this cell answers:
  usd_export__bake_combined__prototype_reference_isolation_small_scale (CONFIRMED
  BROKEN across every Blender version/scale/headless-vs-headful combination
  tested) found "Reference error: export path matches reference path" and an
  empty (0-vertex) prototype on read-back, using Mesh to Points (VERTS mode)
  on an exact-count grid for point generation. The confirmed-working baseline
  (usd_export__animated_rotation__bake_combined) used Distribute Points on
  Faces instead, built interactively rather than scripted.

  Does swapping Mesh to Points for Distribute Points on Faces (RANDOM method),
  with everything else held constant (same double Object-Info-As-Instance +
  Bake recovery-chain topology, same animation, same ~320-instance target
  scale, same Blender version/headless mode as the confirmed-broken cell),
  resolve the defect? If yes: point-generation method is the root cause. If
  no: it rules that out too, pointing toward topology/object-reuse instead.

  NOTE: Distribute Points on Faces does not give an exact, guaranteed
  instance count the way the grid+Mesh-to-Points convention does. This
  script does not attempt to hit exactly 320 -- it targets "approximately
  320" via density tuning and asserts self-consistency (protoIndices count
  == positions count, both > 0 and in a sane range) rather than an exact
  fixed value. The actual question under test is prototype resolution, not
  precise count.

Traces to: geonodes_export_interop_gap.md source #2 (#139654).
"""

import bpy
import os
import json
import math

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "usd_export__bake_combined__prototype_reference_isolation_distribute_points_variant",
    "script_version": "v1",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (#139654). Isolation follow-up "
        "to usd_export__bake_combined__prototype_reference_isolation_small_scale "
        "(CONFIRMED BROKEN). Swaps Mesh to Points for Distribute Points on Faces "
        "as the point-generation node, holding topology/animation/scale constant, "
        "to isolate point-generation method as a candidate root cause."
    ),

    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "target_instance_count_approx": 320,  # NOT exact -- see module docstring
    "expected_count_min": 250,
    "expected_count_max": 400,

    "output_path": "/tmp/gn_interop_distribute_points_variant_v1",
    "bake_directory": "/tmp/gn_interop_distribute_points_variant_v1_bake",

    "keyframes_deg": {
        4: 0.0,
        5: 0.0,
        24: 90.0,
    },
    "export_frame_start": 4,
    "export_frame_end": 24,

    "distribute_seed": 42,
    "distribute_density": 3.2,  # tuned for ~320 points on a 10x10 plane
}


# =====================================================================
# VERSION STAMP
# =====================================================================
def log_version_stamp():
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": CONFIG["cell_id"],
        "script_version": CONFIG["script_version"],
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, separators=(",", ":")))
    return stamp


# =====================================================================
# BUILD -- single-face plane -> Distribute Points on Faces (RANDOM) ->
# Object Info(As Instance) -> Instance on Points -> Bake (DISK) ->
# Instances to Points -> second Object Info(As Instance) -> Instance on
# Points, with Rotation keyframed on the second Instance-on-Points node.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    bpy.ops.mesh.primitive_plane_add(size=10)
    source = bpy.context.view_layer.objects.active
    source.name = "GN_Source_Plane"

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 5))
    proto = bpy.context.view_layer.objects.active
    proto.name = "ProtoCube"
    proto.hide_render = True
    proto.hide_viewport = False

    bpy.context.view_layer.objects.active = source
    mod = source.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_DistributeVariant", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n_in = ng.nodes.new("NodeGroupInput")
    n_out = ng.nodes.new("NodeGroupOutput")
    n_in.location = (-1400, 0)
    n_out.location = (1400, 0)

    # THE VARIABLE UNDER TEST: Distribute Points on Faces instead of Mesh to Points
    n_dist = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
    n_dist.distribute_method = 'RANDOM'
    n_dist.inputs["Density"].default_value = CONFIG["distribute_density"]
    n_dist.inputs["Seed"].default_value = CONFIG["distribute_seed"]
    n_dist.location = (-1100, 0)
    ng.links.new(n_in.outputs["Geometry"], n_dist.inputs["Mesh"])

    n_objinfo1 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo1.inputs["Object"].default_value = proto
    n_objinfo1.inputs["As Instance"].default_value = True
    n_objinfo1.location = (-1100, -300)

    n_iop1 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_iop1.location = (-800, 0)
    ng.links.new(n_dist.outputs["Points"], n_iop1.inputs["Points"])
    ng.links.new(n_objinfo1.outputs["Geometry"], n_iop1.inputs["Instance"])

    n_bake = ng.nodes.new("GeometryNodeBake")
    n_bake.bake_items.new(socket_type="GEOMETRY", name="Geometry")
    n_bake.location = (-500, 0)
    ng.links.new(n_iop1.outputs["Instances"], n_bake.inputs["Geometry"])

    n_i2p = ng.nodes.new("GeometryNodeInstancesToPoints")
    n_i2p.location = (-200, 0)
    ng.links.new(n_bake.outputs["Geometry"], n_i2p.inputs["Instances"])

    n_objinfo2 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo2.inputs["Object"].default_value = proto
    n_objinfo2.inputs["As Instance"].default_value = True
    n_objinfo2.location = (-200, -300)

    n_iop2 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_iop2.location = (200, 0)
    ng.links.new(n_i2p.outputs["Points"], n_iop2.inputs["Points"])
    ng.links.new(n_objinfo2.outputs["Geometry"], n_iop2.inputs["Instance"])

    ng.links.new(n_iop2.outputs["Instances"], n_out.inputs["Geometry"])

    rot_socket = n_iop2.inputs["Rotation"]
    for frame, deg in CONFIG["keyframes_deg"].items():
        rot_socket.default_value = (0.0, 0.0, math.radians(deg))
        rot_socket.keyframe_insert(data_path="default_value", frame=frame)

    bpy.context.view_layer.objects.active = source
    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)

    mod.bake_target = 'DISK'
    mod.bake_directory = CONFIG["bake_directory"]
    bpy.context.view_layer.update()

    bake_id = mod.bakes[0].bake_id
    with bpy.context.temp_override(
        active_object=source,
        selected_objects=[source],
        object=source,
        view_layer=bpy.context.view_layer,
    ):
        bpy.ops.object.geometry_node_bake_single(
            session_uid=source.session_uid,
            modifier_name=mod.name,
            bake_id=bake_id,
        )

    meta_dir = os.path.join(CONFIG["bake_directory"], "meta")
    disk_bake_confirmed = os.path.isdir(meta_dir) and len(os.listdir(meta_dir)) > 0

    return source, proto, {"disk_bake_confirmed": disk_bake_confirmed, "meta_dir": meta_dir}


# =====================================================================
# EXPORT
# =====================================================================
def export_cell(obj):
    scene = bpy.context.scene
    scene.frame_start = CONFIG["export_frame_start"]
    scene.frame_end = CONFIG["export_frame_end"]

    out_path = f"{CONFIG['output_path']}.usdc"

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    wm = bpy.context.window_manager
    window = wm.windows[0] if wm.windows else None
    override_kwargs = dict(
        active_object=obj,
        selected_objects=[obj],
        object=obj,
        view_layer=bpy.context.view_layer,
    )
    if window is not None:
        override_kwargs["window"] = window
        override_kwargs["screen"] = window.screen

    with bpy.context.temp_override(**override_kwargs):
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
def run_assertions(out_path, bake_info):
    from pxr import Usd, UsdGeom

    results = {}
    stage = Usd.Stage.Open(out_path)

    instancer = None
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.PointInstancer):
            instancer = UsdGeom.PointInstancer(prim)
            break

    if instancer is None:
        results["count_match"] = {"pass": False, "detail": "No PointInstancer prim found in exported stage."}
        results["prototype_match"] = {"pass": False, "detail": "No PointInstancer prim found."}
        results["transform_match"] = {"pass": None, "detail": "N/A -- this isolation cell targets prototype resolution, not orientations timing."}
        results["attribute_match"] = {"pass": None, "detail": "N/A for this cell."}
        return results

    proto_indices_attr = instancer.GetProtoIndicesAttr()
    positions_attr = instancer.GetPositionsAttr()
    proto_indices = proto_indices_attr.Get(Usd.TimeCode.EarliestTime())
    positions = positions_attr.Get(Usd.TimeCode.EarliestTime())
    n_proto_idx = len(proto_indices) if proto_indices else 0
    n_pos = len(positions) if positions else 0

    self_consistent = (n_proto_idx == n_pos) and n_pos > 0
    in_range = CONFIG["expected_count_min"] <= n_pos <= CONFIG["expected_count_max"]
    results["count_match"] = {
        "pass": self_consistent and in_range,
        "detail": (
            f"protoIndices={n_proto_idx}, positions={n_pos} "
            f"(self_consistent={self_consistent}, in_range[{CONFIG['expected_count_min']},"
            f"{CONFIG['expected_count_max']}]={in_range} -- Distribute Points on Faces "
            f"does not give an exact count, unlike the Mesh-to-Points grid convention)"
        ),
    }

    proto_targets = instancer.GetPrototypesRel().GetTargets()
    proto_ok = False
    proto_detail = f"targets={proto_targets}"
    if proto_targets:
        proto_prim = stage.GetPrimAtPath(proto_targets[0])
        resolved_mesh = None
        if proto_prim.IsInstance():
            resolved_mesh = proto_prim.GetPrototype()
        if resolved_mesh is None or not resolved_mesh:
            for child in Usd.PrimRange(proto_prim):
                if child.IsA(UsdGeom.Mesh):
                    resolved_mesh = child
                    break
        if resolved_mesh:
            mesh_geom = UsdGeom.Mesh(resolved_mesh)
            pts = mesh_geom.GetPointsAttr().Get()
            n_proto_verts = len(pts) if pts else 0
            proto_ok = (n_proto_verts == 8)
            proto_detail = f"resolved prototype vertex count={n_proto_verts} (expected 8), targets={proto_targets}"
    results["prototype_match"] = {"pass": proto_ok, "detail": proto_detail}

    results["transform_match"] = {"pass": None, "detail": "N/A -- this isolation cell targets prototype resolution only."}
    results["attribute_match"] = {"pass": None, "detail": "N/A for this cell."}
    results["_bake_diagnostics"] = bake_info

    return results


# =====================================================================
# REPORT
# =====================================================================
def report(stamp, config, assertion_results, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "assertions": assertion_results,
    }, separators=(",", ":"), default=str))


def main():
    stamp = log_version_stamp()
    try:
        obj, proto, bake_info = build_scene()
        out_path = export_cell(obj)
        results = run_assertions(out_path, bake_info)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
