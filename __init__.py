bl_info = {
    "name": "PBR Model Importer",
    "author": "pjsamm",
    "blender": (2, 93, 0),
    "category": "Import-Export",
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
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import ExportHelper

from .importer import importer
from .exporter import exporter

class ImportModel(Operator, ImportHelper):
    """Import a model from Pokémon Battle Revolution"""
    bl_idname = "pbr.import"
    bl_label = "PBR Model (.sdr)"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(
        default='*.sdr',
        options={'HIDDEN'}
    )

    use_default_pose: bpy.props.BoolProperty(
        name='Import In Default Pose',
        description="Some models' bind poses are pretty funky at " + \
                    "the moment. Enable\nthis to import models in " + \
                    "their default pose instead",
        default=False
    )
    
    def execute(self, context):
        importer.importSDR(context, self.filepath,
                           useDefaultPose=self.use_default_pose)
        # set viewport shading to Material Preview in Layout view
        view = [space for area in bpy.data.screens['Layout'].areas
                for space in area.spaces if space.type == 'VIEW_3D'][0]
        view.shading.type = 'MATERIAL'
        return {'FINISHED'}

class ExportModel(Operator, ExportHelper):
    """Export a model for use in Pokémon Battle Revolution"""
    bl_idname = "pbr.export"
    bl_label = "PBR Model (.sdr)"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".sdr"

    filter_glob: bpy.props.StringProperty(
        default='*.sdr',
        options={'HIDDEN'}
    )
    
    def execute(self, context):
        exporter.writeSDR(self.filepath, context)
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(ImportModel.bl_idname)

def menu_func_export(self, context):
    self.layout.operator(ExportModel.bl_idname)

def register():
    bpy.utils.register_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.utils.register_class(ExportModel)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(ExportModel)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
