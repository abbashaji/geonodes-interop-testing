"""
Cell: alembic_export__curves__basic
Maps to: geonodes_export_interop_gap.md source #20 (Groom Exporter, Gumroad --
a paid product exists specifically because native Blender export doesn't
carry Curves objects to Unreal's Groom schema via Alembic cleanly) and the
general #9/#10 convergence that GN's GeometrySet output isn't understood by
Blender's exporters. First curves/hair cell in the matrix -- everything
tested to date is points/mesh instancing only.

Run via a disposable non-`--background` windowed process (xvfb-run), per
HARNESS NOTES' "Disposable non-`--background` windowed subprocess resolves
the extreme-scale blocker" entry -- same reasoning applies here since
wm.alembic_export/import's window-context requirement is only PARTIALLY
resolved (confirmed fine in a live-connector session, which always has a
window; NOT yet confirmed for true --background). Don't risk a false
"crashed" result from the window-context gap when a known-good invocation
shape already exists:

    xvfb-run blender --python alembic_export__curves__basic_v2.py

Do NOT add --background to that command.

v1->v2: removed an unwired, incorrectly-named "align to normal" attempt
that crashed build_scene() before any export was attempted -- see
HARNESS NOTES "Wrong bl_idname for Align Rotation to Vector" for detail.
Not needed for this cell's fidelity goals (count/attribute survival, not
orientation), so simply dropped rather than fixed-and-wired.
"""

import bpy
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "alembic_export__curves__basic",
    "maps_to_source": "geonodes_export_interop_gap.md source #20 (Groom Exporter) + #9/#10",

    "export_format": "alembic",
    "instance_type": "curves",       # new category for this matrix -- not points/object_instances/mixed
    "bake_node_present": False,
    "animation_present": False,
    "nesting_depth": 1,

    "n_points": 64,                  # how many hair-strand curves to distribute
    "strand_length": 0.1,
    "strand_resolution": 3,          # points per strand curve line

    "float_tolerance": 1e-5,
    "output_path": "/tmp/alembic_curves_basic_test",
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
# BUILD -- GN network: Distribute Points on Faces -> Instance a short Curve
# Line on each point (oriented by normal) -> Realize Instances -> a single
# multi-spline Curves-domain geometry attached to a Mesh-type source object.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Emitter surface: a simple 4x4 subdivided plane, enough faces to
    # distribute n_points across without relying on a single huge face.
    bpy.ops.mesh.primitive_plane_add(size=2)
    base = bpy.context.active_object
    base.name = "GN_Curves_Source"
    mesh_mod = base.modifiers.new("Subdiv", "SUBSURF")
    mesh_mod.levels = 2
    bpy.ops.object.modifier_apply(modifier=mesh_mod.name)

    mod = base.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Curves_Test_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes = ng.nodes
    links = ng.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")

    distribute = nodes.new("GeometryNodeDistributePointsOnFaces")
    distribute.distribute_method = "RANDOM"
    distribute.inputs["Density"].default_value = 400.0  # tuned against the plane's area to land near n_points
    distribute.inputs["Seed"].default_value = 7  # fixed seed -- same mesh+seed+Blender build => deterministic
    # count is NOT hardcoded/guessed -- see get_ground_truth_point_count() below,
    # called before export so the assertion compares against a measured value.

    curve_line = nodes.new("GeometryNodeCurvePrimitiveLine")
    curve_line.inputs["Start"].default_value = (0.0, 0.0, 0.0)
    curve_line.inputs["End"].default_value = (0.0, 0.0, CONFIG["strand_length"])
    resample = nodes.new("GeometryNodeResampleCurve")
    resample.inputs["Count"].default_value = CONFIG["strand_resolution"]

    # Per-strand custom attribute: stash the point index onto each instance
    # via Store Named Attribute BEFORE realize, so it's a real per-strand
    # (not per-point-of-the-strand) value to check survival of after export.
    capture_index = nodes.new("GeometryNodeInputIndex")
    store_attr = nodes.new("GeometryNodeStoreNamedAttribute")
    store_attr.data_type = "INT"
    store_attr.domain = "INSTANCE"
    store_attr.inputs["Name"].default_value = "strand_id"

    instance_on_points = nodes.new("GeometryNodeInstanceOnPoints")
    # NOTE (v1->v2): dropped an unwired, incorrectly-named "align to normal"
    # attempt here (GeometryNodeAlignRotationToVector isn't a real bl_idname
    # -- see HARNESS NOTES). Strand orientation isn't needed for this cell's
    # fidelity goals (count/attribute survival), so default rotation is fine.

    realize = nodes.new("GeometryNodeRealizeInstances")

    links.new(group_in.outputs["Geometry"], distribute.inputs["Mesh"])
    links.new(distribute.outputs["Points"], instance_on_points.inputs["Points"])
    links.new(resample.outputs["Curve"], instance_on_points.inputs["Instance"])
    links.new(curve_line.outputs["Curve"], resample.inputs["Curve"])
    links.new(instance_on_points.outputs["Instances"], store_attr.inputs["Geometry"])
    links.new(capture_index.outputs["Index"], store_attr.inputs["Value"])
    links.new(store_attr.outputs["Geometry"], realize.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])

    return base, ng, distribute


def get_ground_truth_point_count(obj, ng, distribute_node):
    """
    Per HARNESS NOTES' Measurement bugs (v3->v4) and Ground-truth measurement
    bug (v4): don't trust evaluated_geometry.instances or to_mesh() on a raw
    Points-domain output. Temporarily rewire the group output to the
    pre-instancing distribute stage through a GeometryNodePointsToVertices
    node, evaluate, count real vertices via to_mesh(), then rewire back.
    """
    group_out = next(n for n in ng.nodes if n.type == "GROUP_OUTPUT")
    original_link = next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"])
    original_from_socket = original_link.from_socket

    points_to_verts = ng.nodes.new("GeometryNodePointsToVertices")
    ng.links.new(distribute_node.outputs["Points"], points_to_verts.inputs["Points"])
    ng.links.new(points_to_verts.outputs["Mesh"], group_out.inputs["Geometry"])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    count = len(mesh_eval.vertices)
    obj_eval.to_mesh_clear()

    # Rewire back to the real (curves) output before returning.
    ng.links.remove(next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"]))
    ng.links.new(original_from_socket, group_out.inputs["Geometry"])
    ng.nodes.remove(points_to_verts)

    return count


# =====================================================================
# EXPORT + REIMPORT
# =====================================================================
def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.abc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # evaluation_mode defaults to 'RENDER' -- modifiers (incl. GN) applied
    # by default per HARNESS NOTES, no explicit apply-modifiers flag needed.
    bpy.ops.wm.alembic_export(filepath=out_path, selected=True)
    return out_path


def reimport_cell(path):
    before = set(bpy.data.objects.keys())
    bpy.ops.wm.alembic_import(filepath=path)
    after = set(bpy.data.objects.keys())
    new_names = after - before  # set-difference per HARNESS NOTES, never substring match
    return [bpy.data.objects[n] for n in new_names]


# =====================================================================
# ASSERTIONS
# =====================================================================
def run_assertions(source_obj, reimported_objs, expected_strand_count):
    results = {}
    tol = CONFIG["float_tolerance"]

    results["name_persistence"] = {
        "pass": len(reimported_objs) > 0,
        "detail": f"source={source_obj.name}, reimported={[o.name for o in reimported_objs]}",
    }

    # --- Count match: reimported spline count vs the MEASURED (not guessed)
    # ground-truth point count captured pre-export via get_ground_truth_point_count() ---
    curve_objs = [o for o in reimported_objs if o.type in ("CURVES", "CURVE")]
    total_splines = 0
    for o in curve_objs:
        if o.type == "CURVES":
            total_splines += len(o.data.curves)
        else:
            total_splines += len(o.data.splines)
    results["count_match"] = {
        "pass": total_splines == expected_strand_count,
        "detail": f"reimported curve objects={len(curve_objs)} (types: {[o.type for o in curve_objs]}), "
                  f"total splines={total_splines}, expected={expected_strand_count} "
                  f"(measured pre-export via ground-truth rewire, seed={7}, not guessed)",
    }

    # --- Transform match: first-probe unknown, deliberately left unresolved
    # rather than guessed. Per HARNESS NOTES' TRANSFORM_CACHE precedent for
    # reimported *object* transforms on USD -- it is NOT yet established
    # whether reimported Alembic curve POINT positions (as opposed to a
    # whole object's matrix_world) go through an equivalent live-evaluated
    # cache mechanism or land as static point data directly on o.data. This
    # must be probed on the first real run (print obj.data attributes /
    # check for a constraint) before this assertion can be written correctly
    # -- guessing which API to trust here is exactly the mistake HARNESS
    # NOTES already caught once for to_mesh() and object.location.
    # =====================================================================
    if curve_objs:
        first = curve_objs[0]
        probe = {
            "object_type": first.type,
            "constraints": [c.type for c in first.constraints],
            "has_evaluated_get": hasattr(first, "evaluated_get"),
        }
    else:
        probe = None
    results["transform_match"] = {
        "pass": None,
        "detail": f"tolerance={tol}; DELIBERATELY UNRESOLVED -- first-probe data captured for the next "
                  f"script version: {probe}. Do not infer pass/fail from this alone.",
    }

    # --- Attribute-value match: does strand_id survive per-spline? ---
    attr_probe = None
    if curve_objs:
        d = curve_objs[0].data
        attr_probe = {
            "attribute_names": [a.name for a in getattr(d, "attributes", [])],
        }
    results["attribute_match"] = {
        "pass": None,
        "detail": f"DELIBERATELY UNRESOLVED -- checking whether 'strand_id' (stored on the INSTANCE "
                  f"domain pre-realize) survives under any name/domain post-Alembic-reimport. "
                  f"First-probe attribute list captured for the next script version: {attr_probe}.",
    }

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
    }, indent=2))


def main():
    stamp = log_version_stamp()
    try:
        obj, ng, distribute_node = build_scene()
        expected_count = get_ground_truth_point_count(obj, ng, distribute_node)
        print(f"=== GROUND TRUTH: expected strand count = {expected_count} ===")
        out_path = export_cell(obj)
        reimported = reimport_cell(out_path)
        results = run_assertions(obj, reimported, expected_count)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
