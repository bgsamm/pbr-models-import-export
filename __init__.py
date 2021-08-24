bl_info = {
    "name": "PBR Model Importer",
    "author": "pjsamm",
    "blender": (2, 80, 0),
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

import bpy, bmesh
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from mathutils import Euler, Matrix, Vector

import os, math
from .importer import sdr
from .importer.const import *

class ImportModel(Operator, ImportHelper):
    """Import a model from Pokémon Battle Revolution"""
    bl_idname = "pbr.import"
    bl_label = "PBR Model (.sdr)"
    bl_options = {'REGISTER', 'UNDO'}

    def addMirror(self, node_tree):
        texCoord = node_tree.nodes.new('ShaderNodeTexCoord')
        separateXYZ = node_tree.nodes.new('ShaderNodeSeparateXYZ')
        node_tree.links.new(texCoord.outputs['UV'], separateXYZ.inputs['Vector'])
        pingPongX = node_tree.nodes.new('ShaderNodeMath')
        pingPongX.operation = 'PINGPONG'
        pingPongX.inputs[1].default_value = 1.0
        pingPongY = node_tree.nodes.new('ShaderNodeMath')
        pingPongY.operation = 'PINGPONG'
        pingPongY.inputs[1].default_value = 1.0
        node_tree.links.new(separateXYZ.outputs['X'], pingPongX.inputs['Value'])
        node_tree.links.new(separateXYZ.outputs['Y'], pingPongY.inputs['Value'])
        combineXYZ = node_tree.nodes.new('ShaderNodeCombineXYZ')
        node_tree.links.new(pingPongX.outputs['Value'], combineXYZ.inputs['X'])
        node_tree.links.new(pingPongY.outputs['Value'], combineXYZ.inputs['Y'])
        return combineXYZ

    def createMaterial(self, matData, texData, image):
        mat = bpy.data.materials.new(matData.name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes['Principled BSDF']
        texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texImage.image = image
        if texData.extensionType == GX_CLAMP:
            texImage.extension = 'EXTEND'
        elif texData.extensionType == GX_REPEAT:
            texImage.extension = 'REPEAT'
        elif texData.extensionType == GX_MIRROR:
            mirror = self.addMirror(mat.node_tree)
            mat.node_tree.links.new(mirror.outputs['Vector'], texImage.inputs['Vector'])
        mat.node_tree.links.new(texImage.outputs['Color'], bsdf.inputs['Base Color'])
        mat.node_tree.links.new(texImage.outputs['Alpha'], bsdf.inputs['Alpha'])
        mat.use_backface_culling = True
        mat.blend_method = 'CLIP'
        return mat

    def uvMap(self, obj, meshData, partData, material):
        obj.data.materials.append(material)
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.verify()
        for face in bm.faces:
            for loop in face.loops:
                fdata = partData.faces[face.index]
                idx = fdata.getMatchingTexCoord(loop.vert.index)
                loop[uv_layer].uv = meshData.texCoords[idx]
        bpy.ops.object.mode_set(mode='OBJECT')

    def applyWeights(self, meshData, bones):
        vertices = []
        normals = []
        for i in range(len(meshData.vertices)):
            transform = Matrix.Diagonal((0, 0, 0, 0))
            for idx, w in meshData.weights[i].items():
                transform = transform + \
                            w * (bones[idx].globalTransform @ \
                                 bones[idx].inverseBindMatrix)
            vert = transform @ Vector(meshData.vertices[i])
            vertices.append(tuple(vert))
            transform = transform.to_3x3() # remove translation
            norm = (transform @ Vector(meshData.vertNormals[i])).normalized()
            normals.append(tuple(norm))
        return vertices, normals

    def makeMesh(self, meshData, partData, bones):
        m = bpy.data.meshes.new('mesh')
        # define mesh geometry
        if meshData.weights is not None:
            v, n = self.applyWeights(meshData, bones)
        else:
            v = meshData.vertices
            n = meshData.vertNormals
        f = [face.vertexIndices for face in partData.faces]
        m.from_pydata(v, [], f)
        # set mesh vertex normals
        m.use_auto_smooth = True
        m.normals_split_custom_set_from_vertices(meshData.vertNormals) 
        return m

    def makeObject(self, context, meshData, partData, material, bones):
        m = self.makeMesh(meshData, partData, bones)
        o = bpy.data.objects.new('mesh', m)
        context.collection.objects.link(o)
        context.view_layer.objects.active = o
        # UV map object
        if partData.usesTexCoords:
            self.uvMap(o, meshData, partData, material)
        # define vertex groups
        if meshData.weights is not None:
            for i in range(len(meshData.vertices)):
                for idx, w in meshData.weights[i].items():
                    name = bones[idx].name
                    if name not in o.vertex_groups:
                        o.vertex_groups.new(name=name)
                    o.vertex_groups[name].add([i], w, 'REPLACE')
        return o

    def makeArmature_r(self, edit_bones, bones, boneIndex):
        boneData = bones[boneIndex]
        bone = edit_bones.new(boneData.name)
        bone.tail = (0, 0, 1) # length = 1
        bone.transform(boneData.globalTransform)
        for childIndex in boneData.childIndices:
            child = self.makeArmature_r(edit_bones, bones, childIndex)
            child.parent = bone
        return bone

    def makeArmature(self, context, skele):
        bpy.ops.object.armature_add(enter_editmode=True)
        
        arma = context.object
        arma.name = skele.name
        
        edit_bones = arma.data.edit_bones
        edit_bones.remove(edit_bones['Bone'])

        self.makeArmature_r(edit_bones, skele.bones, 0)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return arma
    
    def execute(self, context):
        model_data = sdr.parseSDR(self.filepath)

        # save images
        images = model_data['images']
        for i in range(len(images)):
            img = images[i]
            image = bpy.data.images.new(f'image{i}', img.width, img.height)
            # Blender expects values to be normalized
            image.pixels = [(x / 255) for x in img.pixels]
            path = f'{os.path.dirname(self.filepath)}\\texture{i}.png'
            image.filepath_raw = path
            image.file_format = 'PNG'
            image.save()
            images[i] = image
        
        # create materials
        materials = model_data['materials']
        textures = model_data['textures']

        for i in range(len(materials)):
            mat = materials[i]
            if mat.textureIndex is not None:
                tex = textures[mat.textureIndex]
                img = images[tex.imageIndex]
                materials[i] = self.createMaterial(mat, tex, img)
            else:
                materials[i] = bpy.data.materials.new('empty')

        # make armatures
        skeletons = model_data['skeletons']
        meshes = model_data['meshes']
        for skele in skeletons:
            arma = self.makeArmature(context, skele)
            arma.select_set(False)
            for bone in skele.bones:
                if bone.meshIndex != None:
                    mesh = meshes[bone.meshIndex]
                    parts = []
                    for part in mesh.parts:
                        mat = materials[part.materialIndex]
                        obj = self.makeObject(context, mesh, part, mat, skele.bones)
                        obj.select_set(True)
                        parts.append(obj)
                    context.view_layer.objects.active = parts[0]
                    bpy.ops.object.join()
                    
                    arma.select_set(True)
                    context.view_layer.objects.active = arma
                    bpy.ops.object.parent_set(type='ARMATURE')
            arma.rotation_euler = Euler((math.pi / 2, 0, 0), 'XYZ')
                    
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(ImportModel.bl_idname)

def register():
    bpy.utils.register_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.append(menu_func)

def unregister():
    bpy.utils.unregister_class(ImportModel)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)

if __name__ == "__main__":
    register()
