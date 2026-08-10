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
the extreme-scale blocker" entry:

    xvfb-run blender --python alembic_export__curves__basic_v3.py

Do NOT add --background to that command.

v2->v3: v2 confirmed count_match FAIL (0 curve-typed objects reimported vs
1062 expected) and left transform_match/attribute_match as "DELIBERATELY
UNRESOLVED -- first-probe data captured" because their probes only ran
`if curve_objs:`, and curve_objs was empty, so probe=None both times. That
is not actually unresolved -- it's a determinate result once you know WHY
curve_objs was empty. v3 adds one new measurement to make sure the reason is
"Alembic lost the data on export/reimport" and not "our own GN network never
produced valid curve data in the first place":

  - get_ground_truth_curve_point_count(): rewires the group output to a
    Curve to Points (mode=EVALUATED) -> Points to Vertices chain, evaluates,
    counts real vertices via to_mesh(). This runs BEFORE export, on the
    live evaluated GeometrySet, so a non-zero count here proves our node
    network genuinely produces curve geometry -- isolating any subsequent
    failure to the export/reimport step, not to a harness bug.

Given that, transform_match and attribute_match are resolved as FAIL (not
left null) whenever ground-truth curve data was confirmed present pre-export
but zero curve-typed objects exist post-reimport: there is no curve point/
attribute data left to compare against, so the assertion fails on the
strength of that absence -- not on a guess about API shape, which is the
thing v2 correctly refused to do.
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
    "instance_type": "curves",
    "bake_node_present": False,
    "animation_present": False,
    "nesting_depth": 1,

    "n_points": 64,
    "strand_length": 0.1,
    "strand_resolution": 3,

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
# BUILD -- unchanged from v2: Distribute Points on Faces -> Instance a short
# Curve Line on each point -> Realize Instances -> single multi-spline
# Curves-domain geometry attached to a Mesh-type source object.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

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
    distribute.inputs["Density"].default_value = 400.0
    distribute.inputs["Seed"].default_value = 7

    curve_line = nodes.new("GeometryNodeCurvePrimitiveLine")
    curve_line.inputs["Start"].default_value = (0.0, 0.0, 0.0)
    curve_line.inputs["End"].default_value = (0.0, 0.0, CONFIG["strand_length"])
    resample = nodes.new("GeometryNodeResampleCurve")
    resample.inputs["Count"].default_value = CONFIG["strand_resolution"]

    capture_index = nodes.new("GeometryNodeInputIndex")
    store_attr = nodes.new("GeometryNodeStoreNamedAttribute")
    store_attr.data_type = "INT"
    store_attr.domain = "INSTANCE"
    store_attr.inputs["Name"].default_value = "strand_id"

    instance_on_points = nodes.new("GeometryNodeInstanceOnPoints")
    realize = nodes.new("GeometryNodeRealizeInstances")

    links.new(group_in.outputs["Geometry"], distribute.inputs["Mesh"])
    links.new(distribute.outputs["Points"], instance_on_points.inputs["Points"])
    links.new(resample.outputs["Curve"], instance_on_points.inputs["Instance"])
    links.new(curve_line.outputs["Curve"], resample.inputs["Curve"])
    links.new(instance_on_points.outputs["Instances"], store_attr.inputs["Geometry"])
    links.new(capture_index.outputs["Index"], store_attr.inputs["Value"])
    links.new(store_attr.outputs["Geometry"], realize.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])

    return base, ng, distribute, realize


def get_ground_truth_point_count(obj, ng, distribute_node):
    """Unchanged from v2 -- pre-instancing point count via rewire+to_mesh()."""
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

    ng.links.remove(next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"]))
    ng.links.new(original_from_socket, group_out.inputs["Geometry"])
    ng.nodes.remove(points_to_verts)

    return count


def get_ground_truth_curve_point_count(obj, ng, realize_node):
    """
    NEW in v3. Proves the REALIZED (post-instancing) geometry genuinely
    contains curve data before export, so a later export/reimport failure
    can be attributed to the exporter rather than to our own node network.
    Rewires group output to realize_node -> Curve to Points (EVALUATED
    mode, so it samples the resampled 3-point-per-strand curves as built,
    not some default) -> Points to Vertices -> to_mesh(), counts vertices.
    Expected = n_points-actually-distributed * strand_resolution (NOT
    CONFIG["n_points"], which is only a density-tuning target -- compare
    against the measured expected_strand_count from
    get_ground_truth_point_count(), multiplied by strand_resolution).
    """
    group_out = next(n for n in ng.nodes if n.type == "GROUP_OUTPUT")
    original_link = next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"])
    original_from_socket = original_link.from_socket

    curve_to_points = ng.nodes.new("GeometryNodeCurveToPoints")
    curve_to_points.mode = "EVALUATED"
    points_to_verts = ng.nodes.new("GeometryNodePointsToVertices")

    ng.links.new(realize_node.outputs["Geometry"], curve_to_points.inputs["Curve"])
    ng.links.new(curve_to_points.outputs["Points"], points_to_verts.inputs["Points"])
    ng.links.new(points_to_verts.outputs["Mesh"], group_out.inputs["Geometry"])

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    count = len(mesh_eval.vertices)
    obj_eval.to_mesh_clear()

    ng.links.remove(next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"]))
    ng.links.new(original_from_socket, group_out.inputs["Geometry"])
    ng.nodes.remove(points_to_verts)
    ng.nodes.remove(curve_to_points)

    return count


# =====================================================================
# EXPORT + REIMPORT -- unchanged from v2
# =====================================================================
def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.abc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.alembic_export(filepath=out_path, selected=True)
    return out_path


def reimport_cell(path):
    before = set(bpy.data.objects.keys())
    bpy.ops.wm.alembic_import(filepath=path)
    after = set(bpy.data.objects.keys())
    new_names = after - before
    return [bpy.data.objects[n] for n in new_names]


# =====================================================================
# ASSERTIONS
# =====================================================================
def run_assertions(source_obj, reimported_objs, expected_strand_count, expected_curve_point_count, ground_truth_curve_point_count):
    results = {}
    tol = CONFIG["float_tolerance"]

    results["name_persistence"] = {
        "pass": len(reimported_objs) > 0,
        "detail": f"source={source_obj.name}, reimported={[o.name for o in reimported_objs]}",
    }

    # NEW in v3: log the type of EVERY reimported object, not just the ones
    # that happen to be curve-typed -- v2 silently filtered this to zero
    # without ever showing what actually came back.
    all_reimported_types = {o.name: o.type for o in reimported_objs}

    curve_objs = [o for o in reimported_objs if o.type in ("CURVES", "CURVE")]
    total_splines = 0
    for o in curve_objs:
        if o.type == "CURVES":
            total_splines += len(o.data.curves)
        else:
            total_splines += len(o.data.splines)
    results["count_match"] = {
        "pass": total_splines == expected_strand_count,
        "detail": f"reimported curve objects={len(curve_objs)}, total splines={total_splines}, "
                  f"expected={expected_strand_count}. ALL reimported objects (name: type): "
                  f"{all_reimported_types}",
    }

    # --- Ground-truth confirmation that our own GN network is not at fault ---
    harness_confirmed_valid = ground_truth_curve_point_count == expected_curve_point_count and ground_truth_curve_point_count > 0
    ground_truth_detail = (
        f"pre-export realized curve-point count (via Curve to Points + Points to Vertices rewire, "
        f"EVALUATED mode) = {ground_truth_curve_point_count}, expected = {expected_curve_point_count} "
        f"({expected_strand_count} strands x {CONFIG['strand_resolution']} resolution). "
        f"{'MATCHES -- our GN network genuinely produces the expected curve geometry pre-export.' if harness_confirmed_valid else 'MISMATCH -- treat count_match/transform_match/attribute_match verdicts with caution, our own harness may be at fault.'}"
    )

    # --- Transform match: resolved as FAIL, not left null, once ground
    # truth confirms real curve data existed pre-export but zero curve
    # objects exist post-reimport -- there is nothing left to compare
    # transforms against. This is a determinate conclusion from measured
    # data (count_match + ground truth), not a guess about API shape.
    if curve_objs:
        # (kept for completeness/future cells where curve_objs is non-empty)
        first = curve_objs[0]
        results["transform_match"] = {
            "pass": None,
            "detail": f"curve objects DID reimport this run ({first.name}) -- transform comparison logic "
                      f"still not implemented for the non-empty case, needs its own follow-up script version.",
        }
    elif harness_confirmed_valid:
        results["transform_match"] = {
            "pass": False,
            "detail": f"FAIL -- no curve-typed object exists post-reimport (see count_match), so there is no "
                      f"point-transform data to compare against source. This is not a guess: pre-export ground "
                      f"truth confirms real curve geometry existed ({ground_truth_detail}), so the absence is "
                      f"attributable to the export/reimport step, not to a harness bug.",
        }
    else:
        results["transform_match"] = {
            "pass": None,
            "detail": f"UNRESOLVED -- {ground_truth_detail} Cannot attribute the post-reimport absence of curve "
                      f"data to Alembic specifically until the harness's own pre-export geometry is fixed.",
        }

    # --- Attribute-value match: same resolution logic as transform_match ---
    if curve_objs:
        d = curve_objs[0].data
        attr_probe = {"attribute_names": [a.name for a in getattr(d, "attributes", [])]}
        results["attribute_match"] = {
            "pass": None,
            "detail": f"curve objects DID reimport this run -- attribute survival check ('strand_id') still not "
                      f"implemented for the non-empty case. First-probe attribute list: {attr_probe}.",
        }
    elif harness_confirmed_valid:
        results["attribute_match"] = {
            "pass": False,
            "detail": f"FAIL -- no curve-typed object exists post-reimport (see count_match), so the 'strand_id' "
                      f"custom attribute (stored on the INSTANCE domain pre-realize) has nothing to survive on. "
                      f"Pre-export ground truth confirms the attribute-bearing geometry existed before export "
                      f"({ground_truth_detail}), so this is attributable to the export/reimport step.",
        }
    else:
        results["attribute_match"] = {
            "pass": None,
            "detail": f"UNRESOLVED -- {ground_truth_detail} Cannot attribute attribute loss to Alembic "
                      f"specifically until the harness's own pre-export geometry is fixed.",
        }

    results["_ground_truth_curve_check"] = {
        "pass": harness_confirmed_valid,
        "detail": ground_truth_detail,
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
        obj, ng, distribute_node, realize_node = build_scene()
        expected_strand_count = get_ground_truth_point_count(obj, ng, distribute_node)
        print(f"=== GROUND TRUTH: expected strand count = {expected_strand_count} ===")
        expected_curve_point_count = expected_strand_count * CONFIG["strand_resolution"]
        ground_truth_curve_point_count = get_ground_truth_curve_point_count(obj, ng, realize_node)
        print(f"=== GROUND TRUTH: realized curve point count (pre-export) = {ground_truth_curve_point_count}, "
              f"expected = {expected_curve_point_count} ===")

        out_path = export_cell(obj)
        reimported = reimport_cell(out_path)
        results = run_assertions(
            obj, reimported, expected_strand_count,
            expected_curve_point_count, ground_truth_curve_point_count,
        )
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
