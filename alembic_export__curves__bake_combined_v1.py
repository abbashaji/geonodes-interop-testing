"""
Correctness test: alembic_export__curves__bake_combined
Maps to source #20 (Groom Exporter gap). Adds a Bake node to the same
curves-domain chain used by alembic_export__curves__basic/animated.
"""

import bpy
import json

CONFIG = {
    "cell_id": "alembic_export__curves__bake_combined",
    "maps_to_source": "geonodes_export_interop_gap.md source #20 (Groom Exporter gap)",
    "export_format": "alembic",
    "instance_type": "curves",
    "bake_node_present": True,
    "animation_present": False,
    "nesting_depth": 1,
    "float_tolerance": 1e-5,
    "output_path": "/tmp/gn_interop_test_output",
    "expected_strand_count": 1062,
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

    base = bpy.data.objects.new("GN_Curves_Source", bpy.data.meshes.new("GN_Curves_Source_mesh"))
    bpy.context.collection.objects.link(base)

    mod = base.modifiers.new("GeometryNodes", "NODES")
    group = bpy.data.node_groups.new("GN_Curves_Bake_Group", "GeometryNodeTree")
    mod.node_group = group

    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    out_node = group.nodes.new("NodeGroupOutput")

    grid = group.nodes.new("GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = 2.0
    grid.inputs["Size Y"].default_value = 2.0
    grid.inputs["Vertices X"].default_value = 33
    grid.inputs["Vertices Y"].default_value = 33

    distribute = group.nodes.new("GeometryNodeDistributePointsOnFaces")
    distribute.distribute_method = "RANDOM"
    distribute.inputs["Density"].default_value = 265.0

    points_to_curves = group.nodes.new("GeometryNodePointsToCurves")

    set_radius = group.nodes.new("GeometryNodeSetCurveRadius")
    set_radius.inputs["Radius"].default_value = 0.01

    bake = group.nodes.new("GeometryNodeBake")

    links = group.links
    links.new(grid.outputs["Mesh"], distribute.inputs["Mesh"])
    links.new(distribute.outputs["Points"], points_to_curves.inputs["Points"])
    links.new(points_to_curves.outputs["Curves"], set_radius.inputs["Curve"])
    links.new(set_radius.outputs["Curve"], bake.inputs[0])
    links.new(bake.outputs[0], out_node.inputs["Geometry"])

    bpy.context.scene.frame_set(1)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()

    eval_obj = base.evaluated_get(depsgraph)
    eval_geo = eval_obj.data
    pre_export_point_count = len(getattr(eval_geo, "vertices", [])) if hasattr(eval_geo, "vertices") else None
    print("=== PRE-EXPORT GROUND TRUTH ===")
    print(json.dumps({"pre_export_point_count": pre_export_point_count}))

    return base


def export_cell(obj):
    out_path = f"{CONFIG['output_path']}.abc"
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.alembic_export(filepath=out_path, selected=True)
    return out_path


def reimport_cell(path):
    bpy.ops.wm.alembic_import(filepath=path)


def run_assertions(source_obj, reimported_objs):
    results = {}

    results["name_persistence"] = {
        "pass": any(o.name.startswith(source_obj.name) for o in reimported_objs),
        "detail": f"source={source_obj.name}, reimported={[o.name for o in reimported_objs]}",
    }

    types_found = [o.type for o in reimported_objs]
    results["type_match"] = {
        "pass": any(t in ("CURVES", "CURVE") for t in types_found),
        "detail": f"reimported_types={types_found}",
    }

    curve_objs = [o for o in reimported_objs if o.type in ("CURVES", "CURVE")]
    if curve_objs:
        strand_count = sum(len(o.data.splines) if o.type == "CURVE" else len(o.data.curves) for o in curve_objs)
    else:
        strand_count = 0
    results["count_match"] = {
        "pass": strand_count == CONFIG["expected_strand_count"],
        "detail": f"expected={CONFIG['expected_strand_count']}, found={strand_count}, reimported_types={types_found}",
    }

    results["transform_match"] = {
        "pass": None,
        "detail": "N/A -- static (non-animated) cell, no transform channel to check",
    }

    results["attribute_match"] = {
        "pass": None,
        "detail": "not evaluated -- count_match/type_match already sufficient to characterize this cell's failure mode" if strand_count == 0 else "NOT YET IMPLEMENTED",
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
    }, separators=(",", ":")))


def main():
    stamp = log_version_stamp()
    try:
        obj = build_scene()
        out_path = export_cell(obj)
        reimport_cell(out_path)
        reimported = [o for o in bpy.data.objects if o != obj]
        results = run_assertions(obj, reimported)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()
