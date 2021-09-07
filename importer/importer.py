import os, math, struct
from mathutils import Euler, Matrix, Vector

import bpy, bmesh

from ..shared import gtx
from ..shared.classes import *
from ..shared.const import *
from ..shared.file_io import BinaryReader

encodings = {
        #0x30: ???
        0x40: 'I4',
        0x41: 'IA4',
        0x42: 'I8',
        0x43: 'IA8',
        0x44: 'RGB565',
        0x45: 'RGBA32',
        0x90: 'RGB5A3',
        0xB0: 'CMPR',
    }

mesh_dict = {}
mat_dict = {}
tex_dict = {}
img_dict = {}

def readString(file, address):
    s = ''
    nextChar = file.read('uchar', address)
    while nextChar != 0:
        s += chr(nextChar)
        nextChar = file.read('uchar', 0, whence='current')
    return s

def toRotationMatrix(x, y, z):
    return Euler((x, y, z), 'XYZ').to_matrix().to_4x4()

def toScaleMatrix(x, y, z):
    return Matrix.Diagonal((x, y, z)).to_4x4()

def flattenIndexedDict(d):
    return [data['object'] for addr,data in
            sorted(d.items(), key=lambda item: item[1]['index'])]

def parseTextures(file, address, numTextures):
    for i in range(numTextures):
        textureAddr = file.read('uint', address, offset=(4 * i))
        imageOffset = file.read('uint', textureAddr, offset=0x28)
        imageAddr = textureAddr + imageOffset
        if imageAddr not in img_dict:
            img = decompressImage(file, textureAddr, imageAddr)
            img_dict[imageAddr] = {
                'object': img,
                'index': len(img_dict)
            }
        extrapX = file.read('uint', textureAddr, offset=0x10)
        extrapY = file.read('uint', textureAddr, offset=0x14)
        tex = Texture(img_dict[imageAddr]['index'], (extrapX, extrapY))
        tex_dict[textureAddr] = {
            'object': tex,
            'index': len(tex_dict)
        }
        
def decompressImage(file, texAddress, imageAddr):
    width = file.read('ushort', texAddress, offset=0)
    height = file.read('ushort', texAddress, offset=0x2)
    encoding = file.read('uint', texAddress, offset=0x8)
    size = file.read('uint', texAddress, offset=0x4c)
    compressedData = file.read_chunk(imageAddr, size)
    imageData = gtx.decompress(compressedData,
                               width, height,
                               encodings[encoding])
    image = Image(imageData, width, height)
    return image

def parseMaterial(file, address):
    nameAddr = file.read('uint', address, offset=0)
    name = file.read('string', nameAddr)
    textureAddr = file.read('uint', address, offset=0x18)
    mat = Material(name,
                   tex_dict[textureAddr]['index'] if textureAddr else None)
    return mat

def parseVertices(file, address, numEntries, stride):
    vertices = []
    for i in range(numEntries):
        x = file.read('float', address, offset=(i * stride))
        y = file.read('float', 0, whence='current')
        z = file.read('float', 0, whence='current')
        vertices.append((x, y, z))
    return vertices

def parseNormals(file, address, numEntries, stride):
    normals = []
    for i in range(numEntries):
        nx = file.read('float', address, offset=(i * stride + 0xc))
        ny = file.read('float', 0, whence='current')
        nz = file.read('float', 0, whence='current')
        normals.append((nx, ny, nz))
    return normals

def parseTextureCoords(file, address, numEntries, stride):
    texcoords = []
    for i in range(numEntries):
        x = file.read('float', address, offset=(i * stride))
        # mirror vertically
        y = 1.0 - file.read('float', 0, whence='current')
        texcoords.append((x, y))
    return texcoords

def parseWeights(file, address):
    weights = []
    
    n = file.read('ushort', address, offset=0)
    addr1 = file.read('uint', address, offset=0x4)
    file.seek(addr1)
    for i in range(n):
        numVerts = file.read('ushort', 0, whence='current')
        bone1 = file.read('ushort', 0, whence='current')
        for j in range(numVerts):
            weights.append({bone1: 1.0})

    n = file.read('ushort', address, offset=0x8)
    addr1 = file.read('uint', address, offset=0xc)
    addr2 = file.read('uint', address, offset=0x10)
    count = 0
    for i in range(n):
        numVerts = file.read('ushort', addr1, offset=(6 * i))
        bone1 = file.read('ushort', 0, whence='current')
        bone2 = file.read('ushort', 0, whence='current')
        file.seek(addr2 + 2 * count)
        for j in range(numVerts):
            # weights need to be normalized
            w = file.read('ushort', 0, whence='current') / 0xffff
            weights.append({bone1: w, bone2: 1 - w})
        count += numVerts

    n = file.read('ushort', address, offset=0x14)
    addr1 = file.read('uint', address, offset=0x18)
    file.seek(addr1)
    for i in range(n):
        vertNum = file.read('ushort', 0, whence='current')
        bone1 = file.read('ushort', 0, whence='current')
        bone2 = file.read('ushort', 0, whence='current')
        # weights need to be normalized
        w1 = file.read('ushort', 0, whence='current') / 0xffff
        w2 = file.read('ushort', 0, whence='current') / 0xffff
        for bone in weights[vertNum]:
            weights[vertNum][bone] *= (1 - w1 - w2)
        weights[vertNum][bone1] = w1
        if bone2 != 0xffff:
            weights[vertNum][bone2] = w2

    return weights

def parseFaces(file, address, numGroups, vertAttrs):
    faces = []
    file.seek(address)
    for i in range(numGroups):
        op = file.read('uchar', 0, whence='current')
        count = file.read('ushort', 0, whence='current')
        vertices = []
        for j in range(count):
            v = n = t = None
            for attr in vertAttrs:
                idx = file.read('ushort', 0, whence='current')
                if attr == GX_VA_POS:
                    v = idx
                elif attr in [GX_VA_NRM, GX_VA_NBT]:
                    n = idx
                elif attr == GX_VA_TEX0:
                    t = idx
            vertices.append((v, n, t))
        
        if op == GX_DRAW_QUADS:
            for i in range(0, count, 4):
                faces.append(
                    Face(*zip(vertices[i+1], vertices[i], vertices[i+2])))
                faces.append(
                    Face(*zip(vertices[i+2], vertices[i], vertices[i+3])))
        elif op == GX_DRAW_TRIANGLES:
            for i in range(0, count, 3):
                faces.append(
                    Face(*zip(vertices[i+1], vertices[i], vertices[i+2])))
        elif op == GX_DRAW_TRIANGLE_STRIP:
            for i in range(count - 2):
                if i % 2 == 0:
                    faces.append(
                        Face(*zip(vertices[i+1], vertices[i], vertices[i+2])))
                else:
                    faces.append(
                        Face(*zip(vertices[i], vertices[i+1], vertices[i+2])))
        else:
            raise Exception(f"Unknown opcode '{k}' at offset {hex(file.tell())}")
    return faces

def parseMesh(file, address):
    meshAddr = file.read('uint', address, offset=0x18)
    parts = []
    for mesh in parseMeshPart(file, meshAddr):
        parts.append(mesh)
    vertStride = max([part.vertStride for part in parts])
    assert vertStride != 0
    assert all([part.vertStride == vertStride for part in parts])
    texStride = max([part.texStride for part in parts])
    assert all([part.texStride == 0 or part.texStride == texStride
                for part in parts])
    
    # vertices
    numVertices = file.read('ushort', address, offset=0x2)
    verticesAddr = file.read('uint', address, offset=0x8)
    v = parseVertices(file, verticesAddr, numVertices, vertStride)
    # vertex normals
    n = parseNormals(file, verticesAddr, numVertices, vertStride)
    # texture coordinates
    uvLayerAddr = file.read('uint', address, offset=0x14)
    t = None
    if uvLayerAddr != 0 and texStride > 0:
        texCoordsAddr = file.read('uint', uvLayerAddr, offset=0)
        numTexCoords = file.read('ushort', uvLayerAddr, offset=0x4)
        t = parseTextureCoords(file, texCoordsAddr, numTexCoords, texStride)

    # bone weights
    boneWeightsAddr = file.read('uint', address, offset=0xc)
    if boneWeightsAddr != 0:
        w = parseWeights(file, boneWeightsAddr)
    else:
        w = None

    meshGroup = Mesh(v, n, t, w)
    meshGroup.parts = parts
    return meshGroup

def parseMeshPart(file, address):
    vertInfoAddr = file.read('uint', address, offset=0x10)
    vas = {}
    va = list(file.read_chunk(vertInfoAddr, 6))
    while va[0] != 0xff:
        vas[va[0]] = va
        va = list(file.read_chunk(0x2, 6, whence='current'))
    
    materialAddr = file.read('uint', address, offset=0x8)
    numGroups = file.read('ushort', address, offset=0xc)
    facesAddr = file.read('uint', address, offset=0x14)
    f = parseFaces(file, facesAddr, numGroups, vas)
    mesh = MeshPart(f, mat_dict[materialAddr]['index'])
    if GX_VA_POS in vas:
        mesh.vertStride = vas[GX_VA_POS][5]
    if GX_VA_TEX0 in vas:
        mesh.texStride = vas[GX_VA_TEX0][5]
    yield mesh
    
    # check if there is a next part of the mesh
    nextMeshAddr = file.read('uint', address, offset=0x1c)
    if nextMeshAddr != 0:
        for mesh in parseMeshPart(file, nextMeshAddr):
            yield mesh

def parseSkeleton(file, address, useDefaultPose=False):
    objNameAddr = file.read('uint', address, offset=0)
    name = file.read('string', objNameAddr)
    numBones = file.read('ushort', address, offset=0x6)
    rootAddr = file.read('uint', address, offset=0x10)
    bones = [None] * numBones
    rootBone = next(parseBones(file, rootAddr, bones, useDefaultPose))
    return Skeleton(name, numBones, bones)

def parseBones(file, address, bones, useDefaultPose=False):
    k = file.read('uint', address, offset=0)
    nameAddr = file.read('uint', address, offset=0x4)
    name = file.read('string', nameAddr)
    idx = file.read('ushort', address, offset=0x8)

    pos = Matrix.Identity(4)
    posAddr = file.read('uint', address, offset=0xc)
    if posAddr != 0:
        x = file.read('float', posAddr)
        y = file.read('float', 0, whence='current')
        z = file.read('float', 0, whence='current')
        pos = Matrix.Translation((x, y, z))
    else:
        pos = Matrix.Identity(4)

    if useDefaultPose:
        rotAddr = file.read('uint', address, offset=0x10)
        if rotAddr != 0:
            rx = file.read('float', rotAddr)
            ry = file.read('float', 0, whence='current')
            rz = file.read('float', 0, whence='current')
            rot = toRotationMatrix(rx, ry, rz)
        else:
            rot = Matrix.Identity(4)
    else:
        rot = Matrix.Identity(4)
    
    scaAddr = file.read('uint', address, offset=0x14)
    if scaAddr != 0:
        file.seek(scaAddr)
        sx = file.read('float', scaAddr)
        sy = file.read('float', 0, whence='current')
        sz = file.read('float', 0, whence='current')
        sca = toScaleMatrix(sx, sy, sz)
    else:
        sca = Matrix.Identity(4)
    
    if k == 0x2:
        # bind pose rotation
        rx = file.read('float', address, offset=0x34)
        ry = file.read('float', 0, whence='current')
        rz = file.read('float', 0, whence='current')
        rot2 = toRotationMatrix(rx, ry, rz)
        rot = rot2 @ rot
        # inverse bind matrix
        mat = []
        file.seek(address + 0x44)
        for r in range(3):
            row = []
            for c in range(4):
                row.append(file.read('float', 0, whence='current'))
            mat.append(row)
        mat.append([0.0, 0.0, 0.0, 1.0])
    else:
        mat = [[1.0, 0.0, 0.0, 0.0],
               [0.0, 1.0, 0.0, 0.0],
               [0.0, 0.0, 1.0, 0.0],
               [0.0, 0.0, 0.0, 1.0]]
    mat = Matrix(mat)
    bone = Bone(idx, name, (pos @ rot @ sca), mat)
    bones[idx] = bone
    
    childAddr = file.read('uint', address, offset=0x24)
    if childAddr != 0:
        for child in parseBones(file, childAddr, bones, useDefaultPose):
            bone.childIndices.append(child.index)
            child.parentIndex = idx
            
    if k == 0x3: # skin node
        meshAddr = file.read('uint', address, offset=0x30)
        if meshAddr not in mesh_dict:
            mesh_dict[meshAddr] = {
                'object': parseMesh(file, meshAddr),
                'index': len(mesh_dict)
            }
        bone.meshIndex = mesh_dict[meshAddr]['index']
    yield bone
    
    nextAddr = file.read('uint', address, offset=0x28)
    if nextAddr != 0:
        for sibling in parseBones(file, nextAddr, bones, useDefaultPose):
            yield sibling

def parseModel(path, useDefaultPose=False):
    global mesh_dict, mat_dict, tex_dict, img_dict
    mesh_dict = {}
    mat_dict = {}
    tex_dict = {}
    img_dict = {}

    file = BinaryReader(path)

    # skeleton
    skeletons = []

    if path[-4:] == '.mdr':
        texturesListAddr = file.read('uint', 0x8)
        numTextures = file.read('ushort', 0xc)
        parseTextures(file, texturesListAddr, numTextures)

        materialAddr = file.read('uint', 0x18)
        mat_dict[materialAddr] = {
            'object': parseMaterial(file, materialAddr),
            'index': len(mat_dict)
        }

    elif path[-4:] == '.odr':
        texturesListAddr = file.read('uint', 0xc)
        numTextures = file.read('ushort', 0x18)
        parseTextures(file, texturesListAddr, numTextures)

        materialsListAddr = file.read('uint', 0x14)
        numMaterials = file.read('ushort', 0x1c)
        for i in range(numMaterials):
            materialAddr = file.read('uint', materialsListAddr, offset=(4 * i))
            mat_dict[materialAddr] = {
                'object': parseMaterial(file, materialAddr),
                'index': len(mat_dict)
            }

        skeletonHeaderAddr = file.read('uint', 0x8)
        skele = parseSkeleton(file, skeletonHeaderAddr, useDefaultPose)
        skeletons.append(skele)
    else:
        texturesListAddr = file.read('uint', 0xc)
        numTextures = file.read('ushort', 0x1a)
        parseTextures(file, texturesListAddr, numTextures)

        materialsListAddr = file.read('uint', 0x14)
        numMaterials = file.read('ushort', 0x1e)
        for i in range(numMaterials):
            materialAddr = file.read('uint', materialsListAddr, offset=(4 * i))
            mat_dict[materialAddr] = {
                'object': parseMaterial(file, materialAddr),
                'index': len(mat_dict)
            }

        skeletonsListAddrPtr = file.read('uint', 0x8)
        numSkeletons = file.read('ushort', 0x18)
        for i in range(numSkeletons):
            skeletonHeaderAddr = file.read('uint', skeletonsListAddrPtr + 4 * i)
            skele = parseSkeleton(file, skeletonHeaderAddr, useDefaultPose)
            skeletons.append(skele)
        
    
    file.close()
    
    sdr = {
        'skeletons': skeletons,
        'meshes': flattenIndexedDict(mesh_dict),
        'materials': flattenIndexedDict(mat_dict),
        'textures': flattenIndexedDict(tex_dict),
        'images': flattenIndexedDict(img_dict)
    }
    return sdr

def createExtensionNodes(node_tree, extension_x, extension_y):
    texCoord = node_tree.nodes.new('ShaderNodeTexCoord')
    separateXYZ = node_tree.nodes.new('ShaderNodeSeparateXYZ')
    node_tree.links.new(texCoord.outputs['UV'], separateXYZ.inputs['Vector'])
    mathNodeX = node_tree.nodes.new('ShaderNodeMath')
    mathNodeY = node_tree.nodes.new('ShaderNodeMath')
    for node, ext in [(mathNodeX, extension_x), (mathNodeY, extension_y)]:
        if ext == GX_CLAMP:
            node.operation = 'MINIMUM'
            node.inputs[1].default_value = 1.0
        elif ext == GX_REPEAT:
            node.operation = 'WRAP'
            node.inputs[1].default_value = 1.0
            node.inputs[2].default_value = 0.0
        elif ext == GX_MIRROR:
            node.operation = 'PINGPONG'
            node.inputs[1].default_value = 1.0
    node_tree.links.new(separateXYZ.outputs['X'], mathNodeX.inputs['Value'])
    node_tree.links.new(separateXYZ.outputs['Y'], mathNodeY.inputs['Value'])
    combineXYZ = node_tree.nodes.new('ShaderNodeCombineXYZ')
    node_tree.links.new(mathNodeX.outputs['Value'], combineXYZ.inputs['X'])
    node_tree.links.new(mathNodeY.outputs['Value'], combineXYZ.inputs['Y'])
    return combineXYZ

def createMaterial(matData, texData, image):
    mat = bpy.data.materials.new(matData.name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    texImage = mat.node_tree.nodes.new('ShaderNodeTexImage')
    texImage.image = image
    texImage.extension = 'EXTEND'
    extension = createExtensionNodes(mat.node_tree, *texData.extensionType)
    mat.node_tree.links.new(extension.outputs['Vector'], texImage.inputs['Vector'])
    mat.node_tree.links.new(texImage.outputs['Color'], bsdf.inputs['Base Color'])
    mat.node_tree.links.new(texImage.outputs['Alpha'], bsdf.inputs['Alpha'])
    mat.use_backface_culling = True
    mat.blend_method = 'CLIP'
    return mat

def uvMap(obj, meshData, partData, material):
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

def applyWeights(meshData, bones):
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

def makeMesh(meshData, partData, bones):
    m = bpy.data.meshes.new('mesh')
    # define mesh geometry
    if meshData.weights is not None:
        v, n = applyWeights(meshData, bones)
    else:
        v = meshData.vertices
        n = meshData.vertNormals
    f = [face.vertexIndices for face in partData.faces]
    m.from_pydata(v, [], f)
    # set mesh vertex normals
    m.use_auto_smooth = True
    m.normals_split_custom_set_from_vertices(meshData.vertNormals) 
    return m

def makeObject(context, meshData, partData, material, bones):
    m = makeMesh(meshData, partData, bones)
    o = bpy.data.objects.new('mesh', m)
    context.collection.objects.link(o)
    context.view_layer.objects.active = o
    # UV map object
    if partData.texStride > 0:
        uvMap(o, meshData, partData, material)
    # define vertex groups
    if meshData.weights is not None:
        for i in range(len(meshData.vertices)):
            for idx, w in meshData.weights[i].items():
                name = bones[idx].name
                if name not in o.vertex_groups:
                    o.vertex_groups.new(name=name)
                o.vertex_groups[name].add([i], w, 'REPLACE')
    return o

def makeArmature_r(edit_bones, bones, boneIndex):
    boneData = bones[boneIndex]
    bone = edit_bones.new(boneData.name)
    bone.tail = (0, 0, 0.5) # length = 0.5
    bone.transform(boneData.globalTransform)
    for childIndex in boneData.childIndices:
        child = makeArmature_r(edit_bones, bones, childIndex)
        child.parent = bone
    return bone

def makeArmature(context, skele):
    bpy.ops.object.armature_add(enter_editmode=True)
    
    arma = context.object
    arma.name = skele.name
    
    edit_bones = arma.data.edit_bones
    edit_bones.remove(edit_bones['Bone'])

    makeArmature_r(edit_bones, skele.bones, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    return arma

def importSDR(context, path, useDefaultPose=False, joinMeshes=False):
    model_data = parseModel(path, useDefaultPose)

    # save images
    images = model_data['images']
    for i in range(len(images)):
        img = images[i]
        image = bpy.data.images.new(f'image{i}', img.width, img.height)
        # Blender expects values to be normalized
        image.pixels = [(x / 255) for x in img.pixels]
        path = f'{os.path.dirname(path)}\\texture{i}.png'
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
            materials[i] = createMaterial(mat, tex, img)
        else:
            materials[i] = bpy.data.materials.new('empty')

    # make armatures
    skeletons = model_data['skeletons']
    meshes = model_data['meshes']
    for skele in skeletons:
        arma = makeArmature(context, skele)
        arma.select_set(False)
        for bone in skele.bones:
            if bone.meshIndex != None:
                mesh = meshes[bone.meshIndex]
                parts = []
                bpy.ops.object.select_all(action='DESELECT')
                for part in mesh.parts:
                    mat = materials[part.materialIndex]
                    obj = makeObject(context, mesh, part, mat, skele.bones)
                    obj.name = bone.name
                    obj.select_set(True)
                    parts.append(obj)
                context.view_layer.objects.active = parts[0]
                if joinMeshes:
                    bpy.ops.object.join()
                
                arma.select_set(True)
                context.view_layer.objects.active = arma
                bpy.ops.object.parent_set(type='ARMATURE')
        arma.rotation_euler = Euler((math.pi / 2, 0, 0), 'XYZ')
