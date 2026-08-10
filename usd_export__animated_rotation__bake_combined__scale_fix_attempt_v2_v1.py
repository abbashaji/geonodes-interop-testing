"""
Cell: usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2
Maps to: geonodes_export_interop_gap.md source #2 (issue #139654, production
USD pipeline) + source #14 (issue #132123, baking for performance) +
sources #11/#15 (production-scale instance counts). Same failure family as
usd_export__animated_rotation__bake_combined__production_scale (CONFIRMED
BROKEN) and __threshold_bisection (CONFIRMED BROKEN, onset in (~320,330]):
at production scale, USD's `orientations` attribute GetTimeSamples() drops
the padding frame, the real start frame, and the real end frame, with the
first surviving sample stale and the last sample clamped to the prior held
value.

Fix under test (v1 of this cell -- prior cells only padded the START of the
range with one frame holding frame-5's value): pad BOTH ends symmetrically
-- one extra frame before the real start (holding the start value) AND one
extra frame after the real end (holding the end value) -- then widen the
export frame range to cover both padding frames. This mirrors the
padding-fix pattern already CONFIRMED WORKING for the position and scale
channels on usd_export__animated_instances__{rotation,scale}__drift_padding_fix_retest,
applied here to the bake_combined/production-scale topology instead.
"""

import bpy
import os
import json
from pxr import Usd, UsdGeom

CONFIG = {
    "cell_id": "usd_export__animated_rotation__bake_combined__scale_fix_attempt_v2",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #2 (#139654) + source #14 "
        "(#132123) + sources #11/#15 (production-scale instance counts)"
    ),
    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": True,
    "nesting_depth": 1,
    "instance_count": 20000,
    "float_tolerance": 1e-5,
    "output_path": "/tmp/usd_rotation_bake_combined_scale_fix_v2",
    "rot_keys_deg": {3: 0.0, 4: 0.0, 5: 0.0, 24: 90.0, 25: 90.0},
    "export_frame_start": 3,
    "export_frame_end": 25,
}


def log_version_stamp():
    stamp = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode() if bpy.app.build_hash else None,
        "cell_id": CONFIG["cell_id"],
    }
    print("=== VERSION STAMP ===")
    print(json.dumps(stamp, separators=(",", ":")))
    return stamp


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.frame_start = CONFIG["export_frame_start"]
    scn.frame_end = CONFIG["export_frame_end"]

    n = CONFIG["instance_count"]
    src_mesh = bpy.data.meshes.new("SourcePlane_mesh")
    src_mesh.from_pydata([(i, 0.0, 0.0) for i in range(n)], [], [])
    src_mesh.update()
    src_obj = bpy.data.objects.new("SourcePlane", src_mesh)
    bpy.context.collection.objects.link(src_obj)

    proto_mesh = bpy.data.meshes.new("ProtoCube_mesh")
    proto_bm_verts = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    ]
    proto_mesh.from_pydata(proto_bm_verts, [], [])
    proto_mesh.update()
    proto_obj = bpy.data.objects.new("ProtoCube", proto_mesh)
    bpy.context.collection.objects.link(proto_obj)
    proto_obj.hide_render = True
    proto_obj.hide_viewport = True

    mod = src_obj.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_ScaleFixV2", "GeometryNodeTree")
    mod.node_group = ng
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes = ng.nodes
    links = ng.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")

    mesh_to_points = nodes.new("GeometryNodeMeshToPoints")
    links.new(group_in.outputs["Geometry"], mesh_to_points.inputs["Mesh"])

    proto_info = nodes.new("GeometryNodeObjectInfo")
    proto_info.inputs["Object"].default_value = proto_obj
    proto_info.transform_space = "RELATIVE"

    instance_1 = nodes.new("GeometryNodeInstanceOnPoints")
    links.new(mesh_to_points.outputs["Points"], instance_1.inputs["Points"])
    links.new(proto_info.outputs["Geometry"], instance_1.inputs["Instance"])

    bake = nodes.new("GeometryNodeBake")
    bake.bake_items.clear()
    bake.bake_items.new("GEOMETRY", "Geometry")
    links.new(instance_1.outputs["Instances"], bake.inputs["Geometry"])
    # bake_mode/bake_target live on the modifier's bake entry, not the node
    # itself -- see harness note "GeometryNodeBake node has no bake_mode/
    # bake_target attrs".
    bake_entry = next(b for b in mod.bakes if b.bake_id == bake.bake_id)
    bake_entry.bake_mode = "STILL"
    bake_entry.bake_target = "DISK"
    bake_entry.directory = "/tmp/gn_bake_cache_scale_fix_v2"

    instances_to_points = nodes.new("GeometryNodeInstancesToPoints")
    links.new(bake.outputs["Geometry"], instances_to_points.inputs["Instances"])

    proto_info_2 = nodes.new("GeometryNodeObjectInfo")
    proto_info_2.inputs["Object"].default_value = proto_obj
    proto_info_2.transform_space = "RELATIVE"

    instance_2 = nodes.new("GeometryNodeInstanceOnPoints")
    links.new(instances_to_points.outputs["Points"], instance_2.inputs["Points"])
    links.new(proto_info_2.outputs["Geometry"], instance_2.inputs["Instance"])

    combine_rot = nodes.new("ShaderNodeCombineXYZ")
    combine_rot.inputs["X"].default_value = 0.0
    combine_rot.inputs["Y"].default_value = 0.0
    links.new(combine_rot.outputs["Vector"], instance_2.inputs["Rotation"])

    links.new(instance_2.outputs["Instances"], group_out.inputs["Geometry"])

    import math
    for frame, deg in CONFIG["rot_keys_deg"].items():
        combine_rot.inputs["Z"].default_value = math.radians(deg)
        combine_rot.inputs["Z"].keyframe_insert(data_path="default_value", frame=frame)

    return src_obj


def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.usdc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.usd_export(
        filepath=out_path,
        selected_objects_only=True,
        export_animation=True,
        use_instancing=True,
    )
    return out_path


def inspect_cell(path):
    stage = Usd.Stage.Open(path)
    point_instancers = [p for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer)]
    return stage, point_instancers


def run_assertions(stage, point_instancers):
    results = {}
    tol = CONFIG["float_tolerance"]
    n = CONFIG["instance_count"]

    if not point_instancers:
        results["count_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        results["prototype_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        results["transform_match"] = {"pass": False, "detail": "no PointInstancer prim found"}
        return results

    pi = UsdGeom.PointInstancer(point_instancers[0])
    positions_attr = pi.GetPositionsAttr()
    proto_idx_attr = pi.GetProtoIndicesAttr()
    orientations_attr = pi.GetOrientationsAttr()

    positions = positions_attr.Get()
    proto_indices = proto_idx_attr.Get()

    results["count_match"] = {
        "pass": (len(positions) == n) and (len(proto_indices) == n),
        "detail": f"expected={n}, positions={len(positions)}, protoIndices={len(proto_indices)}",
    }
    results["prototype_match"] = {
        "pass": all(pi_ == 0 for pi_ in proto_indices),
        "detail": "single prototype expected, all protoIndices==0",
    }

    time_samples = orientations_attr.GetTimeSamples()
    expected_frames = sorted(CONFIG["rot_keys_deg"].keys())
    boundary_frames_present = all(f in time_samples for f in expected_frames)

    per_frame_checks = {}
    for f in expected_frames:
        sample = orientations_attr.Get(f)
        per_frame_checks[f] = {
            "sampled": sample is not None,
            "raw": str(sample),
        }

    results["transform_match"] = {
        "pass": boundary_frames_present,
        "detail": (
            f"tolerance={tol}, expected_frames={expected_frames}, "
            f"actual_time_samples={sorted(time_samples)}, "
            f"boundary_frames_present={boundary_frames_present}, "
            f"per_frame={per_frame_checks}"
        ),
    }

    results["attribute_match"] = {
        "pass": None,
        "detail": "not asserted for this cell -- rotation/count/prototype only, per scope",
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
    }, separators=(",", ":"), default=str))


def main():
    stamp = log_version_stamp()
    try:
        obj = build_scene()
        out_path = export_cell(obj)
        stage, point_instancers = inspect_cell(out_path)
        results = run_assertions(stage, point_instancers)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
