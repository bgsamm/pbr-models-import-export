bl_info = {
    'name': 'PBR Model Importer',
    'author': 'pjsamm',
    'blender': (2, 93, 0),
    'category': 'Import-Export',
}

if 'bpy' in locals():
    print('Reloading pbr-models-import-export...')
    import sys, importlib
    for name in list(sys.modules):
        if name.startswith('pbr-models-import-export'):
            if '.' not in name:
                print('   Reloaded .')
            else:
                print('   Reloaded', name[name.index('.'):])
            importlib.reload(sys.modules[name])

import bpy
from bpy.types import (
    Panel,
    Operator,
    Armature,
    Material,
    Action
)
from bpy.props import *
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import ExportHelper

from .importer import importer
from .exporter import exporter

### Animation selection tab

class PBR_PT_Panel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PBR'
    bl_context = 'objectmode'
    bl_options = { 'DEFAULT_CLOSED' }
    show_arma_prop = True

    @classmethod
    def poll(self, context):
        return context.object is not None and \
            context.object.type == 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        arma = obj.data

        if self.show_arma_prop:
            layout.prop_search(arma, f'prop_{self.anim_id}',
                                bpy.data, 'actions', text='Arma.')
        for child in obj.children:
            if child.type != 'MESH':
                continue
            # doesn't account for meshes sharing materials
            for slot in child.material_slots:
                mat = slot.material
                layout.prop_search(mat, f'prop_{self.anim_id}',
                                    bpy.data, 'actions', text=mat.name)

class PBR_PT_PropertiesPanel(PBR_PT_Panel):
    bl_options = set()
    bl_label = 'Animations'
    bl_idname = 'PBR_PT_properties_panel'

    def draw(self, context):
        return

class PBR_PT_IdleAnimPanel(PBR_PT_Panel):
    bl_label = 'Idle'
    bl_idname = 'PBR_PT_idle_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'idle'

class PBR_PT_RunAnimPanel(PBR_PT_Panel):
    bl_label = 'Run'
    bl_idname = 'PBR_PT_run_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'run'

class PBR_PT_DamageAnimPanel(PBR_PT_Panel):
    bl_label = 'Damage'
    bl_idname = 'PBR_PT_damage_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'damage'

class PBR_PT_FaintAnimPanel(PBR_PT_Panel):
    bl_label = 'Faint'
    bl_idname = 'PBR_PT_faint_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'faint'

class PBR_PT_PhysAnimPanel(PBR_PT_Panel):
    bl_label = 'Phys'
    bl_idname = 'PBR_PT_phys_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'move_phys'

class PBR_PT_SpecAnimPanel(PBR_PT_Panel):
    bl_label = 'Spec'
    bl_idname = 'PBR_PT_spec_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'move_spec'

class PBR_PT_BlinkAnimPanel(PBR_PT_Panel):
    bl_label = 'Blink'
    bl_idname = 'PBR_PT_blink_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'tx_wink'
    show_arma_prop = False

class PBR_PT_SleepAnimPanel(PBR_PT_Panel):
    bl_label = 'Sleep'
    bl_idname = 'PBR_PT_sleep_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'tx_sleep'
    show_arma_prop = False

class PBR_PT_WakeupAnimPanel(PBR_PT_Panel):
    bl_label = 'Wake Up'
    bl_idname = 'PBR_PT_wakeup_anim_panel'
    bl_parent_id = 'PBR_PT_properties_panel'
    anim_id = 'tx_wakeup'
    show_arma_prop = False

subpanels = (
    PBR_PT_IdleAnimPanel,
    PBR_PT_RunAnimPanel,
    PBR_PT_DamageAnimPanel,
    PBR_PT_FaintAnimPanel,
    PBR_PT_PhysAnimPanel,
    PBR_PT_SpecAnimPanel,
    PBR_PT_BlinkAnimPanel,
    PBR_PT_SleepAnimPanel,
    PBR_PT_WakeupAnimPanel
)

### Import/export operators

class ImportModel(Operator, ImportHelper):
    '''Import a model from Pokémon Battle Revolution'''
    bl_idname = 'pbr.import'
    bl_label = 'PBR Model (.sdr/.odr/.mdr)'
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(
        default='*.sdr;*.mdr;*.odr',
        options={'HIDDEN'}
    )

    use_default_pose: BoolProperty(
        name='Import In Default Pose',
        description="Some models' bind poses are pretty funky at " + \
                    "the moment. Enable\nthis to import models in " + \
                    "their default pose instead.",
        default=True
    )

    join_meshes: BoolProperty(
        name='Merge Objects',
        description="Enable to merge objects into a single mesh " + \
                    "when importing. Meshes from different skin nodes " + \
                    "will remain separate.",
        default=False
    )

    def execute(self, context):
        importer.importSDR(context, self.filepath,
                           useDefaultPose=self.use_default_pose,
                           joinMeshes=self.join_meshes)
        # set viewport shading to Material Preview in Layout view
        view = [space for area in bpy.data.screens['Layout'].areas
                for space in area.spaces if space.type == 'VIEW_3D'][0]
        view.shading.type = 'MATERIAL'
        return {'FINISHED'}

class ExportModel(Operator, ExportHelper):
    '''Export a model for use in Pokémon Battle Revolution'''
    bl_idname = 'pbr.export'
    bl_label = 'PBR Model (.sdr)'
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = '.sdr'

    filter_glob: bpy.props.StringProperty(
        default='*.sdr',
        options={'HIDDEN'}
    )

    def execute(self, context):
        exporter.writeSDR(self.filepath, context)
        self.report({'INFO'}, 'Export successful.')
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(ImportModel.bl_idname)

def menu_func_export(self, context):
    self.layout.operator(ExportModel.bl_idname)

def poll_obj(self, object):
    return object.id_root == 'OBJECT'

def poll_node(self, object):
    return object.id_root == 'NODETREE'

def register():
    from bpy.utils import register_class
    # import/export operators
    register_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    register_class(ExportModel)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    # animations tab
    register_class(PBR_PT_PropertiesPanel)
    for cls in subpanels:
        register_class(cls)
        setattr(Armature, f'prop_{cls.anim_id}',
                PointerProperty(type=Action, poll=poll_obj))
        setattr(Material, f'prop_{cls.anim_id}',
                PointerProperty(type=Action, poll=poll_node))


def unregister():
    from bpy.utils import unregister_class
    # import/export operators
    unregister_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    unregister_class(ExportModel)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    # animations tab
    unregister_class(PBR_PT_PropertiesPanel)
    for cls in subpanels:
        unregister_class(cls)
        RemoveProperty(Armature, attr=f'prop_{cls.anim_id}')

if __name__ == '__main__':
    register()
