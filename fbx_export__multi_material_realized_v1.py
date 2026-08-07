"""
Cell: fbx_export__multi_material_realized
Maps to: geonodes_export_interop_gap.md source #6 (issue #95102), follow-up
to fbx_export__materials -- does per-instance MATERIAL VARIATION (not just
one shared material) survive Realize Instances + FBX export?

Ad-hoc interactive session against a live Blender instance via a connector
(same approach as prior entries' v4 scripts) -- this file is the
consolidated, verified-working scaffold for reuse via
`blender --background --python <this_file>` or by pasting into a connected
session's scripting console.
"""

import bpy
import os
import tempfile
import json

CONFIG = {
    "cell_id": "fbx_export__multi_material_realized",
    "maps_to_source": "geonodes_export_interop_gap.md source #6 (issue #95102)",
    "export_format": "fbx",
    "instance_type": "object_instances",
    "bake_node_present": False,
    "animation_present": False,
    "nesting_depth": 1,
    "num_points": 4,
    "output_path": os.path.join(tempfile.gettempdir(), "fbx_multimat_realized_v1.fbx"),
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


def reset_scene_manually():
    # Never call bpy.ops.wm.read_factory_settings() in a live connector
    # session -- see HARNESS NOTES. Manual teardown instead.
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for ng in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(ng)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def build_scene():
    mat_a = bpy.data.materials.new("MatA_Red")
    mat_a.diffuse_color = (1, 0, 0, 1)
    mat_b = bpy.data.materials.new("MatB_Blue")
    mat_b.diffuse_color = (0, 0, 1, 1)

    bpy.ops.mesh.primitive_cube_add(size=0.3, location=(0, 0, -5))
    inst_obj = bpy.context.active_object
    inst_obj.name = "InstSourceCube"

    mesh = bpy.data.meshes.new("PointsMesh")
    mesh.from_pydata([(0, 0, 0), (2, 0, 0), (0, 2, 0), (2, 2, 0)], [], [])
    mesh.update()
    points_obj = bpy.data.objects.new("PointsObj", mesh)
    bpy.context.collection.objects.link(points_obj)
    points_obj.data.materials.append(mat_a)
    points_obj.data.materials.append(mat_b)

    gnmod = points_obj.modifiers.new("GeometryNodes", "NODES")
    ng = bpy.data.node_groups.new("GN_MultiMat", "GeometryNodeTree")
    gnmod.node_group = ng

    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nin = ng.nodes.new("NodeGroupInput")
    nout = ng.nodes.new("NodeGroupOutput")
    n_objinfo = ng.nodes.new("GeometryNodeObjectInfo")
    n_objinfo.inputs['Object'].default_value = inst_obj
    n_iop = ng.nodes.new("GeometryNodeInstanceOnPoints")
    n_index = ng.nodes.new("GeometryNodeInputIndex")
    n_store = ng.nodes.new("GeometryNodeStoreNamedAttribute")
    n_store.domain = 'INSTANCE'
    n_store.data_type = 'INT'
    n_store.inputs['Name'].default_value = "inst_idx"
    n_realize = ng.nodes.new("GeometryNodeRealizeInstances")
    n_named_attr = ng.nodes.new("GeometryNodeInputNamedAttribute")
    n_named_attr.data_type = 'INT'
    n_named_attr.inputs['Name'].default_value = "inst_idx"
    n_math = ng.nodes.new("ShaderNodeMath")
    n_math.operation = 'MODULO'
    n_compare = ng.nodes.new("FunctionNodeCompare")
    n_compare.data_type = 'FLOAT'
    n_compare.operation = 'EQUAL'
    n_not = ng.nodes.new("FunctionNodeBooleanMath")
    n_not.operation = 'NOT'

    # CORRECT pattern (see HARNESS NOTES: Set Material's Material socket
    # does NOT support per-element fields -- use Selection-masked Set
    # Material calls instead, one per material, chained).
    n_setmat_a = ng.nodes.new("GeometryNodeSetMaterial")
    n_setmat_b = ng.nodes.new("GeometryNodeSetMaterial")

    links = ng.links
    links.new(nin.outputs['Geometry'], n_iop.inputs['Points'])
    links.new(n_objinfo.outputs['Geometry'], n_iop.inputs['Instance'])
    links.new(n_iop.outputs['Instances'], n_store.inputs['Geometry'])
    links.new(n_index.outputs['Index'], n_store.inputs['Value'])
    links.new(n_store.outputs['Geometry'], n_realize.inputs['Geometry'])

    links.new(n_named_attr.outputs['Attribute'], n_math.inputs[0])
    n_math.inputs[1].default_value = 2.0
    links.new(n_math.outputs['Value'], n_compare.inputs[0])  # index 0 = enabled Float A
    n_compare.inputs[1].default_value = 0.0                  # index 1 = enabled Float B

    links.new(n_realize.outputs['Geometry'], n_setmat_a.inputs['Geometry'])
    links.new(n_compare.outputs['Result'], n_setmat_a.inputs['Selection'])
    n_setmat_a.inputs['Material'].default_value = mat_a

    links.new(n_setmat_a.outputs['Geometry'], n_setmat_b.inputs['Geometry'])
    links.new(n_compare.outputs['Result'], n_not.inputs[0])
    links.new(n_not.outputs['Boolean'], n_setmat_b.inputs['Selection'])
    n_setmat_b.inputs['Material'].default_value = mat_b

    links.new(n_setmat_b.outputs['Geometry'], nout.inputs['Geometry'])

    return points_obj


def export_cell(obj):
    out_path = CONFIG["output_path"]
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, use_mesh_modifiers=True)
    return out_path


def reimport_cell(path):
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=path)
    after = set(bpy.data.objects.keys())
    new_name = list(after - before)[0]
    return bpy.data.objects[new_name]


def run_assertions(source_obj, reimported_obj):
    results = {}
    me = reimported_obj.data

    results["count_match"] = {
        "pass": len(me.vertices) == 32 and len(me.polygons) == 24,
        "detail": f"verts={len(me.vertices)}, polys={len(me.polygons)} (expected 32 verts / 24 polys = 4 instances x 8-vert cube)",
    }

    slot_names = [s.material.name if s.material else None for s in reimported_obj.material_slots]
    results["material_slots_present"] = {
        "pass": len(reimported_obj.material_slots) == 2 and all(slot_names),
        "detail": f"slots={slot_names}",
    }

    counts = {}
    for p in me.polygons:
        slotmat = reimported_obj.material_slots[p.material_index].material
        name = slotmat.name if slotmat else "NONE"
        counts[name] = counts.get(name, 0) + 1
    results["material_variation_fidelity"] = {
        "pass": len(counts) == 2 and sorted(counts.values()) == [12, 12],
        "detail": f"faces per material: {counts} (expected 12/12 split across 2 distinct materials)",
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
    }, indent=2))


def main():
    stamp = log_version_stamp()
    try:
        reset_scene_manually()
        obj = build_scene()
        out_path = export_cell(obj)
        reimp = reimport_cell(out_path)
        results = run_assertions(obj, reimp)
        report(stamp, CONFIG, results)
    except Exception as e:
        report(stamp, CONFIG, {}, crashed=True, crash_detail=str(e))
        raise


if __name__ == "__main__":
    main()