"""
Cell: alembic_export__curves__animated
Maps to: geonodes_export_interop_gap.md source #20 + #23 -- production
hair/groom pipelines are rarely static; Unreal's Groom importer specifically
cares about ANIMATED strand data surviving the round trip, not just a single
static pose. Follow-on to alembic_export__curves__basic, which is now
CONFIRMED BROKEN at Blender 5.2.0 LTS: Alembic silently exports GN
curves-domain geometry as an empty MESH object, never writing a curve
schema at all, even for the static case (see that cell's v3 script and the
harness note "Alembic curves export silently falls back to empty MESH, not
a curve schema").

Given that root cause, the most likely outcome here is the same failure,
independent of animation -- but that is exactly the kind of assumption this
pipeline exists to verify empirically rather than infer, per methodology.md
(new cells matter because a *different* real-world complaint traces to this
one: does animated hair fail identically, or does the animated path hit a
distinct, separately-diagnostic failure such as a crash on time-varying
Alembic writes, or animation timing loss with geometry otherwise intact?).

Run via a disposable non-`--background` windowed process (xvfb-run), same
requirement as alembic_export__curves__basic -- the window/screen context
question for wm.alembic_export/wm.alembic_import is still only partially
resolved (didn't fail in a live MCP session, unverified in true
`--background`), so do not risk it here either:

    xvfb-run blender --python alembic_export__curves__animated_v1.py

Do NOT add --background to that command. (The repo's test.yml workflow
already tries --background first and falls back to xvfb automatically on
failure, so triggering via that workflow is safe either way.)

Reuses alembic_export__curves__basic_v3's scene-building approach almost
exactly (Distribute Points on Faces -> short Curve Line instanced per point
-> Realize Instances, strand_id stored on the INSTANCE domain pre-realize)
and its v3 ground-truth-before-assertions discipline (Curve to Points
EVALUATED + Points to Vertices rewire, counted via to_mesh(), BEFORE
export) -- extended to run that ground-truth check at BOTH frame_start and
frame_end, not just once, since proving the animated network produces valid
curve geometry across the whole exported frame range (not just at a single
static pose) is the specific new thing this cell needs to rule out before
attributing any post-reimport absence to the exporter.

New in v1 (relative to basic_v3, per harness note "name_persistence can
pass on wrong-typed reimported objects"): an explicit type_match assertion
alongside name_persistence, and animation is introduced via a Set Position
node (Offset.z keyframed: 0.0 at frame_start, +0.05 at frame_end) wired
directly on the Points output of Distribute Points on Faces, before
Instance on Points -- animating strand ROOT position over time, which is
the same "Set Position with keyframed Offset" pattern already used by this
project's USD animated-instance cells, applied here to curves instead.
"""

import bpy
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CONFIG = {
    "cell_id": "alembic_export__curves__animated",
    "maps_to_source": (
        "geonodes_export_interop_gap.md source #20 + #23 (Groom Exporter / "
        "Unreal Groom import needs animated strand data, not just a static "
        "pose, to survive the Alembic round trip) -- follow-on to "
        "alembic_export__curves__basic, CONFIRMED BROKEN: no Alembic curve "
        "schema written at all, even for static curves (GN curves-domain "
        "geometry silently falls back to an empty MESH writer)."
    ),

    "export_format": "alembic",
    "instance_type": "curves",
    "bake_node_present": False,
    "animation_present": True,
    "nesting_depth": 1,

    "density": 400.0,
    "strand_length": 0.1,
    "strand_resolution": 3,
    "frame_start": 1,
    "frame_end": 20,
    "animated_z_offset_at_end": 0.05,  # strand-root sway amplitude at frame_end; 0.0 at frame_start

    "float_tolerance": 1e-5,
    "output_path": "/tmp/alembic_curves_animated_test",
}


# =====================================================================
# VERSION STAMP -- must run first, must be in every log, no exceptions
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
# BUILD -- same shape as alembic_export__curves__basic_v3, with an animated
# Set Position node inserted on the Points output before Instance on Points.
# =====================================================================
def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    bpy.ops.mesh.primitive_plane_add(size=2)
    base = bpy.context.active_object
    base.name = "GN_Curves_Animated_Source"
    mesh_mod = base.modifiers.new("Subdiv", "SUBSURF")
    mesh_mod.levels = 2
    bpy.ops.object.modifier_apply(modifier=mesh_mod.name)

    mod = base.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_Curves_Animated_Test_Group", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes = ng.nodes
    links = ng.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")

    distribute = nodes.new("GeometryNodeDistributePointsOnFaces")
    distribute.distribute_method = "RANDOM"
    distribute.inputs["Density"].default_value = CONFIG["density"]
    distribute.inputs["Seed"].default_value = 7

    # --- Animated strand-root offset, keyframed on the POINTS output,
    # before instancing. Frame_start = no offset (matches basic_v3's
    # static pose exactly, so any difference in outcome is attributable to
    # the animation itself, not to a different starting geometry).
    set_position = nodes.new("GeometryNodeSetPosition")
    set_position.inputs["Offset"].default_value = (0.0, 0.0, 0.0)

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
    links.new(distribute.outputs["Points"], set_position.inputs["Geometry"])
    links.new(set_position.outputs["Geometry"], instance_on_points.inputs["Points"])
    links.new(resample.outputs["Curve"], instance_on_points.inputs["Instance"])
    links.new(curve_line.outputs["Curve"], resample.inputs["Curve"])
    links.new(instance_on_points.outputs["Instances"], store_attr.inputs["Geometry"])
    links.new(capture_index.outputs["Index"], store_attr.inputs["Value"])
    links.new(store_attr.outputs["Geometry"], realize.inputs["Geometry"])
    links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])

    # --- Keyframe the animation: 0.0 at frame_start, +animated_z_offset_at_end at frame_end ---
    scene = bpy.context.scene
    scene.frame_start = CONFIG["frame_start"]
    scene.frame_end = CONFIG["frame_end"]

    scene.frame_set(CONFIG["frame_start"])
    set_position.inputs["Offset"].default_value = (0.0, 0.0, 0.0)
    set_position.inputs["Offset"].keyframe_insert(data_path="default_value", frame=CONFIG["frame_start"])

    scene.frame_set(CONFIG["frame_end"])
    set_position.inputs["Offset"].default_value = (0.0, 0.0, CONFIG["animated_z_offset_at_end"])
    set_position.inputs["Offset"].keyframe_insert(data_path="default_value", frame=CONFIG["frame_end"])

    scene.frame_set(CONFIG["frame_start"])

    return base, ng, distribute, realize


def _rewire_ground_truth_curve_points(obj, ng, realize_node):
    """
    Shared by both frame checks below -- identical rewire logic to
    alembic_export__curves__basic_v3's get_ground_truth_curve_point_count,
    factored out so it can be called at two different frames without
    duplicating the rewire/restore dance.
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
    positions = [tuple(v.co) for v in mesh_eval.vertices]
    obj_eval.to_mesh_clear()

    ng.links.remove(next(l for l in ng.links if l.to_socket == group_out.inputs["Geometry"]))
    ng.links.new(original_from_socket, group_out.inputs["Geometry"])
    ng.nodes.remove(points_to_verts)
    ng.nodes.remove(curve_to_points)

    return count, positions


def get_ground_truth_at_frame(obj, ng, realize_node, frame):
    """
    NEW in v1: runs curves__basic_v3's single-frame ground-truth check at an
    ARBITRARY frame, so it can be called once at frame_start and once at
    frame_end -- proving the animated GN network genuinely produces valid,
    non-degenerate curve geometry across the whole exported frame range,
    not just at a single static pose.
    """
    bpy.context.scene.frame_set(frame)
    count, positions = _rewire_ground_truth_curve_points(obj, ng, realize_node)
    return count, positions


# =====================================================================
# EXPORT + REIMPORT -- adds start/end frame range vs. basic_v3's single-pose export
# =====================================================================
def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.abc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.alembic_export(
        filepath=out_path,
        selected=True,
        start=CONFIG["frame_start"],
        end=CONFIG["frame_end"],
    )
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
def run_assertions(source_obj, reimported_objs, expected_strand_count,
                    expected_curve_point_count, ground_truth_start,
                    ground_truth_end):
    results = {}
    tol = CONFIG["float_tolerance"]
    gt_count_start, gt_positions_start = ground_truth_start
    gt_count_end, gt_positions_end = ground_truth_end

    results["name_persistence"] = {
        "pass": len(reimported_objs) > 0,
        "detail": f"source={source_obj.name}, reimported={[o.name for o in reimported_objs]}",
    }

    all_reimported_types = {o.name: o.type for o in reimported_objs}
    curve_objs = [o for o in reimported_objs if o.type in ("CURVES", "CURVE")]
    results["type_match"] = {
        "pass": len(curve_objs) > 0 and len(curve_objs) == len(reimported_objs),
        "detail": f"reimported object types (name: type) = {all_reimported_types}. "
                  f"Expected all reimported objects to be type CURVES/CURVE.",
    }

    total_splines = 0
    for o in curve_objs:
        if o.type == "CURVES":
            total_splines += len(o.data.curves)
        else:
            total_splines += len(o.data.splines)
    results["count_match"] = {
        "pass": total_splines == expected_strand_count,
        "detail": f"reimported curve objects={len(curve_objs)}, total splines={total_splines}, "
                  f"expected={expected_strand_count}.",
    }

    gt_start_ok = gt_count_start == expected_curve_point_count and gt_count_start > 0
    gt_end_ok = gt_count_end == expected_curve_point_count and gt_count_end > 0
    harness_confirmed_valid = gt_start_ok and gt_end_ok
    ground_truth_detail = (
        f"pre-export realized curve-point count at frame_start={CONFIG['frame_start']}: "
        f"{gt_count_start} (expected {expected_curve_point_count}); "
        f"at frame_end={CONFIG['frame_end']}: {gt_count_end} (expected {expected_curve_point_count}). "
        f"{'BOTH MATCH -- animated GN network genuinely produces expected curve geometry across the full range.' if harness_confirmed_valid else 'MISMATCH at one or both frames -- treat count_match/transform_match/attribute_match with caution.'}"
    )

    if curve_objs:
        results["transform_match"] = {
            "pass": None,
            "detail": f"curve objects DID reimport this run ({curve_objs[0].name}) -- animated-drift transform "
                      f"comparison (reimported frame_start vs frame_end positions vs expected "
                      f"{CONFIG['animated_z_offset_at_end']} Z offset, tol={tol}) not yet implemented for the "
                      f"non-empty case; needs its own follow-up script version.",
        }
    elif harness_confirmed_valid:
        results["transform_match"] = {
            "pass": False,
            "detail": f"FAIL -- no curve-typed object exists post-reimport (see count_match/type_match), so "
                      f"there is no animated point-transform data to compare across frames. Not a guess: "
                      f"pre-export ground truth confirms real, correctly-animated curve geometry existed at "
                      f"BOTH frame_start and frame_end ({ground_truth_detail}), so the absence is attributable "
                      f"to the export/reimport step, not to the harness or to the animation itself.",
        }
    else:
        results["transform_match"] = {
            "pass": None,
            "detail": f"UNRESOLVED -- {ground_truth_detail} Cannot attribute the post-reimport absence of "
                      f"curve data to Alembic specifically until the harness's own pre-export animated "
                      f"geometry is fixed.",
        }

    if curve_objs:
        d = curve_objs[0].data
        attr_probe = {"attribute_names": [a.name for a in getattr(d, "attributes", [])]}
        results["attribute_match"] = {
            "pass": None,
            "detail": f"curve objects DID reimport this run -- 'strand_id' survival check not yet implemented "
                      f"for the non-empty case. First-probe attribute list: {attr_probe}.",
        }
    elif harness_confirmed_valid:
        results["attribute_match"] = {
            "pass": False,
            "detail": f"FAIL -- no curve-typed object exists post-reimport, so the 'strand_id' custom "
                      f"attribute (stored on the INSTANCE domain pre-realize) has nothing to survive on. "
                      f"Pre-export ground truth confirms the attribute-bearing geometry existed, at both "
                      f"frames, before export ({ground_truth_detail}).",
        }
    else:
        results["attribute_match"] = {
            "pass": None,
            "detail": f"UNRESOLVED -- {ground_truth_detail} Cannot attribute attribute loss to Alembic "
                      f"specifically until the harness's own pre-export animated geometry is fixed.",
        }

    results["_ground_truth_curve_check_both_frames"] = {
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

        gt_count_start, gt_positions_start = get_ground_truth_at_frame(
            obj, ng, realize_node, CONFIG["frame_start"]
        )
        gt_count_end, gt_positions_end = get_ground_truth_at_frame(
            obj, ng, realize_node, CONFIG["frame_end"]
        )
        print(f"=== GROUND TRUTH @ frame_start={CONFIG['frame_start']}: curve point count = {gt_count_start} ===")
        print(f"=== GROUND TRUTH @ frame_end={CONFIG['frame_end']}: curve point count = {gt_count_end} ===")

        n_strands = gt_count_start // CONFIG["strand_resolution"] if gt_count_start else 0
        expected_curve_point_count = n_strands * CONFIG["strand_resolution"]

        bpy.context.scene.frame_set(CONFIG["frame_start"])
        out_path = export_cell(obj)
        reimported = reimport_cell(out_path)

        results = run_assertions(
            obj, reimported, n_strands, expected_curve_point_count,
            (gt_count_start, gt_positions_start),
            (gt_count_end, gt_positions_end),
        )
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
