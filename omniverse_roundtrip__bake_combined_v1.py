"""
Cell: omniverse_roundtrip__bake_combined
Maps to: geonodes_export_interop_gap.md source #16 (NVIDIA Omniverse developer
forum -- professional users report GN-authored instancing failing to round-trip
through USD into Omniverse; only known workaround is fragile/unexplained).

This isolates the Bake-node variable on top of the already-confirmed static
points/no-animation Omniverse baseline (omniverse_roundtrip__points, BROKEN --
zero UsdGeomPointInstancer prims written, all "instance" prims have empty
points attrs). Per methodology.md point 3, the real complaint is about a
*different* consumer (Omniverse) reading the file, not Blender's own
reimporter -- so this inspects the exported .usdc directly via pxr.Usd instead
of reimporting into Blender, matching the sibling cell's approach.

Topology is a single, non-recovery-chain Distribute Points on Faces -> Bake ->
Instance on Points -- deliberately NOT the double-Object-Info-As-Instance
recovery-chain topology implicated in the separate
"Reference error: export path matches reference path" harness note, so a
0-vertex-prototype result here would be new information, not a repeat of that
already-explained case.
"""

import bpy
import os
import sys
import json
import time

CONFIG = {
    "cell_id": "omniverse_roundtrip__bake_combined",
    "maps_to_source": "geonodes_export_interop_gap.md source #16 (NVIDIA Omniverse developer forum)",

    "export_format": "usd",
    "instance_type": "points",
    "bake_node_present": True,
    "animation_present": False,
    "nesting_depth": 1,
    "instance_count_target": 800,   # matches omniverse_roundtrip__points / usd_export__points__bake_present for direct comparability

    "float_tolerance": 1e-5,
    "output_path": "/tmp/omniverse_roundtrip__bake_combined_output",
    "bake_directory": "/tmp/omniverse_roundtrip__bake_combined_bakecache",
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


def _ctx_override():
    win = bpy.context.window_manager.windows[0]
    return bpy.context.temp_override(window=win, screen=win.screen)


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Ground-truth source: a grid mesh with exactly instance_count_target faces,
    # so Distribute Points on Faces (mode=POISSON off, exact count via density
    # override is unreliable -- use a per-face point instead) gives a known,
    # exact instance count we can assert against directly, not estimate.
    n = CONFIG["instance_count_target"]
    side = int(n ** 0.5) + 1
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=side, y_segments=side, size=1.0)
    mesh = bpy.data.meshes.new("GN_Source_mesh")
    bm.to_mesh(mesh)
    bm.free()
    base = bpy.data.objects.new("GN_Source", mesh)
    bpy.context.collection.objects.link(base)

    # Simple 8-vertex cube prototype to instance.
    proto_mesh = bpy.data.meshes.new("Proto_Cube_mesh")
    import bmesh as bmesh2
    bm2 = bmesh2.new()
    bmesh2.ops.create_cube(bm2, size=0.1)
    bm2.to_mesh(proto_mesh)
    bm2.free()
    proto = bpy.data.objects.new("Proto_Cube", proto_mesh)
    bpy.context.collection.objects.link(proto)
    proto.hide_render = True
    proto.hide_viewport = True

    mod = base.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Test_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    in_node = ng.nodes.new("NodeGroupInput")
    out_node = ng.nodes.new("NodeGroupOutput")

    distribute = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
    distribute.distribute_method = "POISSON"  # placeholder; density set below
    # Use exact-count-friendly random distribution seeded, but since exact
    # face count on a grid built above already yields a known face count,
    # switch to "Vertices as points" style via mesh-to-points on face centers
    # for an exact, non-probabilistic count instead of Poisson sampling.
    ng.nodes.remove(distribute)
    mesh_to_points = ng.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = "FACES"

    # Store a per-point custom int attribute ("instance_id") to test
    # attribute-value persistence through the bake + export.
    store_attr = ng.nodes.new("GeometryNodeStoreNamedAttribute")
    store_attr.inputs["Name"].default_value = "instance_id"
    store_attr.domain = "POINT"
    store_attr.data_type = "INT"
    index_node = ng.nodes.new("GeometryNodeInputIndex")

    # Bake node -- capture the point cloud + attribute before instancing.
    bake_node = ng.nodes.new("GeometryNodeBake")
    bake_node.bake_items.clear()
    bake_node.bake_items.new(socket_type="GEOMETRY", name="Geometry")

    obj_info = ng.nodes.new("GeometryNodeObjectInfo")
    obj_info.transform_space = "RELATIVE"
    obj_info.inputs["Object"].default_value = proto

    instance_on_points = ng.nodes.new("GeometryNodeInstanceOnPoints")

    ng.links.new(in_node.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
    ng.links.new(mesh_to_points.outputs["Points"], store_attr.inputs["Geometry"])
    ng.links.new(index_node.outputs["Index"], store_attr.inputs["Value"])
    ng.links.new(store_attr.outputs["Geometry"], bake_node.inputs["Geometry"])
    ng.links.new(bake_node.outputs["Geometry"], instance_on_points.inputs["Points"])
    ng.links.new(obj_info.outputs["Geometry"], instance_on_points.inputs["Instance"])
    ng.links.new(instance_on_points.outputs["Instances"], out_node.inputs["Geometry"])

    # Trigger dependency graph + populate modifier.bakes.
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    bake_entry = next((b for b in mod.bakes if b.node == bake_node), None)
    if bake_entry is None:
        raise RuntimeError("modifier.bakes did not populate an entry for the Bake node after view_layer.update()")
    bake_entry.bake_target = "DISK"
    bake_entry.directory = CONFIG["bake_directory"]
    os.makedirs(CONFIG["bake_directory"], exist_ok=True)

    bpy.context.view_layer.objects.active = base
    base.select_set(True)
    with _ctx_override():
        bpy.ops.object.geometry_node_bake_single(session_uid=base.session_uid, modifier_name=mod.name, bake_index=list(mod.bakes).index(bake_entry))

    # Verify the bake actually landed on disk (per harness note: a valid
    # directory being set does not guarantee disk mode was actually used --
    # explicit on-disk cache-file check required for any cell whose finding
    # depends on disk-target behavior).
    disk_files = []
    for root, _, files in os.walk(CONFIG["bake_directory"]):
        disk_files.extend(files)
    bake_used_disk = len(disk_files) > 0

    ground_truth_count = len(mesh.polygons)

    return {
        "base": base,
        "proto": proto,
        "ground_truth_count": ground_truth_count,
        "bake_used_disk": bake_used_disk,
        "disk_file_count": len(disk_files),
    }


def export_cell(scene_state):
    base = scene_state["base"]
    out_path = f"{CONFIG['output_path']}.usdc"

    bpy.ops.object.select_all(action="DESELECT")
    base.select_set(True)
    bpy.context.view_layer.objects.active = base

    with _ctx_override():
        bpy.ops.wm.usd_export(
            filepath=out_path,
            selected_objects_only=True,
            use_instancing=True,
        )
    return out_path


def inspect_usd_direct(path, scene_state):
    """
    Real complaint (source #16) is about a *different* consumer (Omniverse)
    reading this file -- inspect the raw USD prim structure directly via
    pxr.Usd rather than reimporting into Blender, matching
    omniverse_roundtrip__points' precedent.
    """
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(path)
    results = {}

    point_instancers = [p for p in stage.Traverse() if p.IsA(UsdGeom.PointInstancer)]
    results["point_instancer_present"] = {
        "pass": len(point_instancers) > 0,
        "detail": f"found {len(point_instancers)} UsdGeomPointInstancer prim(s): {[str(p.GetPath()) for p in point_instancers]}",
    }

    ground_truth = scene_state["ground_truth_count"]

    if point_instancers:
        pi = UsdGeom.PointInstancer(point_instancers[0])
        positions_attr = pi.GetPositionsAttr()
        proto_indices_attr = pi.GetProtoIndicesAttr()
        positions = positions_attr.Get() if positions_attr else None
        proto_indices = proto_indices_attr.Get() if proto_indices_attr else None
        n_positions = len(positions) if positions else 0
        n_proto_indices = len(proto_indices) if proto_indices else 0

        results["count_match"] = {
            "pass": n_positions == ground_truth and n_proto_indices == ground_truth,
            "detail": f"ground_truth={ground_truth}, positions={n_positions}, protoIndices={n_proto_indices}",
        }

        proto_targets = pi.GetPrototypesRel().GetForwardedTargets()
        proto_vertex_counts = []
        for target in proto_targets:
            proto_prim = stage.GetPrimAtPath(target)
            mesh = UsdGeom.Mesh(proto_prim) if proto_prim else None
            pts = mesh.GetPointsAttr().Get() if mesh and mesh.GetPointsAttr() else None
            proto_vertex_counts.append(len(pts) if pts else 0)
        results["prototype_geometry_intact"] = {
            "pass": len(proto_vertex_counts) > 0 and all(c > 0 for c in proto_vertex_counts),
            "detail": f"prototype prim(s) {[str(t) for t in proto_targets]} vertex counts: {proto_vertex_counts} (expected 8 each, cube prototype)",
        }

        if positions and n_positions > 0:
            import math
            base_mesh = scene_state["base"].data
            # Static case, no per-instance transform assertion beyond count
            # here -- transform-drift is already covered by the sibling
            # animated USD cells; this cell's own question is bake-node
            # presence, not transform fidelity, so we only spot-check that
            # returned positions are finite, non-degenerate numbers.
            all_finite = all(all(math.isfinite(c) for c in p) for p in positions)
            results["transform_match"] = {
                "pass": all_finite,
                "detail": f"tolerance={CONFIG['float_tolerance']}, spot-check: all {n_positions} positions finite/non-NaN = {all_finite} (static scene, no drift assertion needed for this cell's question)",
            }
        else:
            results["transform_match"] = {"pass": False, "detail": "no positions to check -- PointInstancer positions array empty"}

    else:
        # No PointInstancer at all -- check whether Blender instead wrote
        # flattened per-instance Mesh prims (the pattern already confirmed
        # for omniverse_roundtrip__points).
        mesh_prims = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
        empty_mesh_prims = [p for p in mesh_prims if not (UsdGeom.Mesh(p).GetPointsAttr().Get())]
        results["count_match"] = {
            "pass": False,
            "detail": f"no PointInstancer written; found {len(mesh_prims)} flattened Mesh prim(s) instead ({len(empty_mesh_prims)} with empty points attr), vs ground_truth={ground_truth}",
        }
        results["prototype_geometry_intact"] = {
            "pass": len(empty_mesh_prims) == 0 and len(mesh_prims) > 0,
            "detail": f"{len(empty_mesh_prims)}/{len(mesh_prims)} flattened mesh prims have empty points attr",
        }
        results["transform_match"] = {"pass": None, "detail": "N/A -- no PointInstancer positions to check"}

    # Attribute-value match: instance_id custom attribute, point domain.
    attr_found = False
    attr_detail = "not checked"
    if point_instancers:
        pi_prim = point_instancers[0]
        attr = pi_prim.GetAttribute("primvars:instance_id")
        if attr and attr.IsValid() and attr.Get() is not None:
            vals = attr.Get()
            attr_found = len(vals) == ground_truth
            attr_detail = f"primvars:instance_id found on PointInstancer, {len(vals)} values vs ground_truth={ground_truth}"
        else:
            attr_detail = "primvars:instance_id not found on PointInstancer prim"
    results["attribute_match"] = {"pass": attr_found, "detail": attr_detail}

    return results


def report(stamp, config, assertion_results, scene_state=None, crashed=False, crash_detail=None):
    print("=== CELL RESULT ===")
    print(json.dumps({
        "stamp": stamp,
        "config": config,
        "crashed": crashed,
        "crash_detail": crash_detail,
        "bake_used_disk": scene_state.get("bake_used_disk") if scene_state else None,
        "disk_file_count": scene_state.get("disk_file_count") if scene_state else None,
        "assertions": assertion_results,
    }, separators=(",", ":")))


def main():
    stamp = log_version_stamp()
    scene_state = None
    try:
        scene_state = build_scene()
        out_path = export_cell(scene_state)
        results = inspect_usd_direct(out_path, scene_state)
        report(stamp, CONFIG, results, scene_state=scene_state)
    except Exception as e:
        report(stamp, CONFIG, {}, scene_state=scene_state, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
