bl_info = {
    "name": "PBR Model Importer",
    "author": "pjsamm",
    "blender": (2, 93, 0),
    "category": "Import-Export",
}

if 'bpy' in locals():
    print('Reloading modules...')
    import sys, importlib
    for name in list(sys.modules):
        if name.startswith('pbr-models-import-export'):
            if '.' not in name:
                print('Reloaded .')
            else:
                print('Reloaded', name[name.index('.'):])
            importlib.reload(sys.modules[name])

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy_extras.io_utils import ExportHelper

import os, math
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
    
    def execute(self, context):
        importer.importSDR(self.filepath, context)
        return {'FINISHED'}

class ExportModel(Operator, ExportHelper):
    """Import a model from Pokémon Battle Revolution"""
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
