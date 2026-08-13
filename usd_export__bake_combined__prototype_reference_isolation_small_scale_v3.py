"""
Cell: usd_export__bake_combined__prototype_reference_isolation_small_scale
Script version: v3 (v1 crashed under xvfb on bpy.context.active_object
AttributeError -- fixed in v2 via view_layer.objects.active. v2 then
crashed under xvfb on geometry_node_bake_single.poll() "Context missing
active object" despite view_layer.objects.active being set correctly --
setting it via Python does not reliably propagate to operator poll()
context under a real xvfb window the way it does in headless mode. Fixed
here via bpy.context.temp_override(active_object=..., selected_objects=...,
object=...) around both the bake and export operator calls, directly
supplying the context attributes poll() checks rather than relying on
view_layer state alone.)

Question this cell answers:
  usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2 (CONFIRMED
  BROKEN at 20,000 instances) found a SEPARATE defect from its own headline
  question: the USD exporter logs "Reference error: export path matches
  reference path: /GN_Source_Grid/ProtoCube_7031_0" repeatedly, and the
  referenced prototype prim reads back with 0 vertices instead of 8 -- i.e.
  instance placement/count survives export but the actual geometry doesn't.

  Is this scale-triggered, or does it also occur at the SAME small scale
  (320 instances) that usd_export__animated_rotation__bake_combined already
  confirmed working (on Blender 5.0.1)? This script reproduces that exact
  topology/animation/count on Blender 5.2.0 LTS, changing nothing but the
  Blender version (uncontrolled secondary variable, flagged) to see whether
  the reference-error defect appears at 320 instances too.

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
    "cell_id": "usd_export__bake_combined__prototype_reference_isolation_small_scale",
    "script_version": "v3",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (#139654). Isolation follow-up "
        "to the 'Reference error: export path matches reference path' harness note "
        "discovered in usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2 "
        "(CONFIRMED BROKEN, 20,000 instances). Same topology/animation, 320 instances "
        "instead of 20,000 -- isolating scale as the variable."
    ),

    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "instance_count": 320,

    "float_tolerance": 1e-4,

    "output_path": "/tmp/gn_interop_prototype_isolation_small_scale_v1",
    "bake_directory": "/tmp/gn_interop_prototype_isolation_small_scale_v1_bake",

    # Same rotation keyframes as the confirmed-working baseline cell
    # (usd_export__animated_rotation__bake_combined): padding at frame 4
    # holding frame 5's value, real motion 5->24, export range 4-24.
    "keyframes_deg": {
        4: 0.0,     # padding, holds frame 5's value
        5: 0.0,     # REAL motion start
        24: 90.0,   # REAL motion end
    },
    "export_frame_start": 4,
    "export_frame_end": 24,
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
# BUILD -- exact-count grid (Mesh to Points, 320 verts) -> Object
# Info(As Instance) -> Instance on Points -> Bake (DISK) -> Instances to
# Points -> second Object Info(As Instance) -> Instance on Points, with
# Rotation keyframed on the second Instance-on-Points node.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Exact-count grid: 320 = 20 * 16. x_subdivisions/y_subdivisions give
    # (N+1) vertices per axis -- see harness note from the scale_fix_attempt_v2
    # session. Use 19/15 subdivisions -> 20*16 = 320 vertices exactly.
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=19, y_subdivisions=15, size=10)
    # Read via view_layer.objects.active, not bpy.context.active_object --
    # the latter raises AttributeError early in an xvfb-launched (non
    # --background) context, per this session's confirmed finding.
    source = bpy.context.view_layer.objects.active
    source.name = "GN_Source_Grid"
    n_verts = len(source.data.vertices)
    assert n_verts == CONFIG["instance_count"], (
        f"Grid vertex count mismatch: got {n_verts}, expected {CONFIG['instance_count']}"
    )

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 5))
    proto = bpy.context.view_layer.objects.active
    proto.name = "ProtoCube"
    proto.hide_render = True
    proto.hide_viewport = False

    bpy.context.view_layer.objects.active = source
    mod = source.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_PrototypeIsolation", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n_in = ng.nodes.new("NodeGroupInput")
    n_out = ng.nodes.new("NodeGroupOutput")
    n_in.location = (-1400, 0)
    n_out.location = (1400, 0)

    n_m2p = ng.nodes.new("GeometryNodeMeshToPoints")
    n_m2p.mode = 'VERTICES'
    n_m2p.location = (-1100, 0)
    ng.links.new(n_in.outputs["Geometry"], n_m2p.inputs["Mesh"])

    n_objinfo1 = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo1.inputs["Object"].default_value = proto
    n_objinfo1.inputs["As Instance"].default_value = True
    n_objinfo1.location = (-1100, -300)

    n_iop1 = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_iop1.location = (-800, 0)
    ng.links.new(n_m2p.outputs["Points"], n_iop1.inputs["Points"])
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
    # Headful (xvfb) mode: view_layer.objects.active alone doesn't satisfy
    # this operator's poll() -- see harness note "Headful (xvfb) mode:
    # view_layer.objects.active set via Python does not satisfy
    # geometry_node_bake_single.poll()...". Use temp_override to directly
    # supply the context attributes the poll() checks, rather than relying
    # on a window/screen/area (which may not exist/resolve the same way
    # under xvfb as under a real desktop session).
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

    # Same defensive temp_override as the bake call, in case wm.usd_export's
    # poll() has the same headful-mode context sensitivity -- untested until
    # a headful run actually reaches this point.
    with bpy.context.temp_override(
        active_object=obj,
        selected_objects=[obj],
        object=obj,
        view_layer=bpy.context.view_layer,
    ):
        bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            export_animation=True,
            use_instancing=True,
        )
    return out_path


# =====================================================================
# ASSERTIONS -- focused specifically on prototype resolution, since
# that's the sole question this isolation cell exists to answer.
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
    results["count_match"] = {
        "pass": (n_proto_idx == CONFIG["instance_count"] and n_pos == CONFIG["instance_count"]),
        "detail": f"protoIndices={n_proto_idx}, positions={n_pos}, expected={CONFIG['instance_count']}",
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

    results["transform_match"] = {"pass": None, "detail": "N/A -- this isolation cell targets prototype resolution only, not orientations timing (already separately confirmed broken elsewhere)."}
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
