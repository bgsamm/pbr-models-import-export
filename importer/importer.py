import os, math, struct
from mathutils import Euler, Matrix, Vector, Quaternion
import numpy as np
import time

import bpy, bmesh

from . import gtx
from .classes import *
from ..shared.const import *
from ..shared.file_io import BinaryReader

encodings = {
        0x00: 'C4',
        0x01: 'C8',
        0x30: 'C14X2',
        0x40: 'I4',
        0x41: 'IA4',
        0x42: 'I8',
        0x43: 'IA8',
        0x44: 'RGB565',
        0x45: 'RGBA32',
        0x90: 'RGB5A3',
        0xB0: 'CMPR',
    }

palEncodings = {
        0x0: 'UNUSED',
        0x1: 'IA8', 
        0x2: 'RGB565',
        0x3: 'RGB5A3',
    }

mesh_dict = {}
mat_dict = {}
tex_dict = {}
img_dict = {}
anim_dict = {}

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
    palEncoding = file.read('uint', texAddress, offset=0xC)
    palAddr = file.read('uint', texAddress, offset=0x48)
    size = file.read('uint', texAddress, offset=0x4c)
    compressedData = file.read_chunk(imageAddr, size)
    imageData = gtx.decompress(compressedData,
                               width, height,
                               encodings[encoding],
                               palEncodings[palEncoding],
                               palAddr - imageAddr)
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

def parseActions(file, address, numActions):
    for i in range(numActions):
        actionAddr = address + i * 0x30
        nameAddr = file.read('uint', actionAddr)
        name = file.read('string', nameAddr)
        anim_dict[i] = {'name': name,
                        'bones': {}}

# these are the types used in the game code as far as I can tell
keyframeDataTypes = {
    0 : 'float',
    2 : 'quat',
    5 : 'uchar',
    6 : 'char',
    7 : 'ushort',
    8 : 'short', 
}
# for vector quantities, component 0 implies 3 component float and 4, 5, 6 imply 2 component float values

# these data types are suggested by some setup code
# they could correspond to the types implied by certain components
unknownKeyFrameDataTypes = {
    1 : 'unknown 1',
    3 : 'unknown 3',
    4 : 'unknown 4',
    10 : 'unknown 10',
    11 : 'unknown 11',
}

def parseFCurves(file, address, boneName):
    nextAddr = address
    while nextAddr != 0:
        actionIndex = file.read('ushort', nextAddr, offset=0)
        numFCurves = file.read('ushort', nextAddr, offset=0x2)
        fcurveListAddr = file.read('uint', nextAddr, offset=0x4)
        anim_dict[actionIndex]['bones'][boneName] = []
        for i in range(numFCurves):
            fcurveAddr = fcurveListAddr + i * 0x10
            axis = file.read('uchar', fcurveAddr, offset=0x2)
            if axis == 0:
                # implies vec3 values
                dataType = 'vec3'
            elif (axis == 4 or axis == 5 or axis == 6):
                # the actual ingame implementation of this looks broken so I don't expect it to be used outside of texture animation which uses different code
                print('vec2 animation found in 3d anim: ', boneName)

            compIndex = file.read('uchar', fcurveAddr, offset=0x1)
            dataType = file.read('uchar', fcurveAddr, offset=0x6)
            if dataType in keyframeDataTypes:
                dataType = keyframeDataTypes[dataType]
            elif dataType in unknownKeyFrameDataTypes:
                print('found one of the expected but undocumented data types: ', dataType)
            else:
                print('completely undocumented data type: ', dataType)
            channelIndex = file.read('uchar', fcurveAddr, offset=0x3)
            unkIndex = file.read('uchar', fcurveAddr, offset=0x4)
            idk = file.read('uchar', fcurveAddr, offset=0x0)
            if compIndex >= 3:
                print(f'Unknown component type: {compIndex} ({boneName}, {hex(fcurveAddr)})')
                continue
            component = ['location', 'rotation_euler', 'scale'][compIndex]
            exp = file.read('uchar', fcurveAddr, offset=0x7)
            if dataType == 'float' or dataType == 'quat' or dataType == 'vec3' or dataType == 'vec2':
                # float values, no scaling required
                exp = 0.0
            keyframeAddr = file.read('uint', fcurveAddr, offset=0x8)
            keyframes = parseKeyframes(file, keyframeAddr, exp, dataType)
            if len(keyframes) == 0:
                continue
            fcurve = {'axis': axis,
                      'component': component,
                      'keyframes': keyframes}
            anim_dict[actionIndex]['bones'][boneName].append(fcurve)
        nextAddr = file.read('uint', nextAddr, offset=0xc)

def parseKeyframes(file, address, scale_exp, dataType):
    valsAddr = file.read('uint', address, offset=0)
    derivsAddr = file.read('uint', address, offset=0x4)
    valueCount = file.read('ushort', address, offset=0x8)
    keyframesAddr = file.read('uint', address, offset=0x10)
    numKeyframes = file.read('ushort', address, offset=0x14)
    keyframes = []
    if numKeyframes > 0:
        for i in range(numKeyframes):
            keyframeAddr = keyframesAddr + i * 0xc
            interpIndex = file.read('ushort', keyframeAddr)
            interpolation = ['CONSTANT', 'LINEAR', 'BEZIER'][interpIndex]
            valueIndex = file.read('ushort', keyframeAddr, offset=0x2)
            value = readKeyframeValue(file, dataType, valsAddr, valueIndex)
            if derivsAddr > 0:
                if dataType == 'quat' or dataType == 'vec3' or dataType == 'vec2':
                    derivLIndex = file.read('ushort', keyframeAddr, offset=0x4)
                    derivLeft = readKeyframeValue(file, dataType, derivsAddr, derivLIndex)
                    derivRIndex = file.read('ushort', keyframeAddr, offset=0x6)
                    derivRight = readKeyframeValue(file, dataType, derivsAddr, derivRIndex)
                else:
                    derivLIndex = file.read('ushort', keyframeAddr, offset=0x4)
                    derivLeft = file.read('float', derivsAddr, offset=(4 * derivLIndex))
                    derivRIndex = file.read('ushort', keyframeAddr, offset=0x6)
                    derivRight = file.read('float', derivsAddr, offset=(4 * derivRIndex))
            else:
                print('derivative data not present even though it should be ...')
                derivLeft = 0.0
                derivRight = 0.0
            time = file.read('float', keyframeAddr, offset=0x8)
            keyframe = {'value': value / (2 ** scale_exp),
                        'derivativeL': derivLeft,
                        'derivativeR': derivRight,
                        'interpolation': interpolation,
                        'time': time}
            keyframes.append(keyframe)
    elif valueCount > 0:
        # "keyframe" animation. stores data for each individual frame
        # probably used for baked data, such as animation data from constraints and IK
        framerate = file.read('ushort', address, offset=0x16) & 0xFF
        for i in range(valueCount):
            value = readKeyframeValue(file, dataType, valsAddr, i)
            time = (0.5 + (i - 1)) / framerate
            keyframe = {'value': value / (2 ** scale_exp),
                        'derivativeL': 0.0,
                        'derivativeR': 0.0,
                        'interpolation': 'CONSTANT',
                        'time': time}
            keyframes.append(keyframe)
    return keyframes

def readKeyframeValue(file, type, baseAdress, index):

    if BinaryReader.is_primitive(type):
        size = BinaryReader.primitive_size(type)
        return file.read(type, baseAdress, offset=(size * index))
    elif type == 'quat' or type == 'vec3' or type == 'vec2':
        # multicomponent stuff needs to be handled separately
        size = 4
        if type == 'vec2':
            n = 2
            return Vector([file.read(type, baseAdress, offset=(size * (index * n + i))) for i in range(n)])
        elif type == 'vec3':
            n = 3
            return Vector([file.read(type, baseAdress, offset=(size * (index * n + i))) for i in range(n)])
        elif type == 'quat':
            n = 4
            return Quaternion([file.read(type, baseAdress, offset=(size * (index * n + i))) for i in range(n)])
    else:
        print('unknown data type: ', type)
        return None

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

def parseSkeleton(file, address, useDefaultPose=False, sceneSettings=None):
    objNameAddr = file.read('uint', address, offset=0)
    name = file.read('string', objNameAddr)
    # actions
    actionsAddr = file.read('uint', address, offset=0xc)
    numActions = file.read('ushort', address, offset=0x8)
    parseActions(file, actionsAddr, numActions)
    # bones
    numBones = file.read('ushort', address, offset=0x6)
    rootAddr = file.read('uint', address, offset=0x10)
    bones = [None] * numBones
    rootBone = next(parseBones(file, rootAddr, bones, useDefaultPose, sceneSettings))
    return Skeleton(name, numBones, bones)

def parseBones(file, address, bones, useDefaultPose=False, sceneSettings=None):
    k = file.read('uint', address, offset=0)
    nameAddr = file.read('uint', address, offset=0x4)
    name = file.read('string', nameAddr)
    idx = file.read('ushort', address, offset=0x8)
    nodeFlags = file.read('ushort', address, offset=0xA)

    if k == 2:
        boneFlags = file.read('uint', address, offset=0x30)
    else:
        boneFlags = 0
    

    i = 1
    blenderName = name
    boneNames = [bone.name for bone in bones if bone]
    while blenderName in boneNames:
        blenderName = f'{name}.{i:03d}'
        i += 1
    name = blenderName

    pos = Matrix.Identity(4)
    posAddr = file.read('uint', address, offset=0xc)
    if posAddr != 0:
        x = file.read('float', posAddr)
        y = file.read('float', 0, whence='current')
        z = file.read('float', 0, whence='current')
        pos = Matrix.Translation((x, y, z))
    else:
        pos = Matrix.Identity(4)
        (x, y, z) = (0, 0, 0)
    
    if useDefaultPose:
        rotAddr = file.read('uint', address, offset=0x10)
        if rotAddr != 0:
            rx = file.read('float', rotAddr)
            ry = file.read('float', 0, whence='current')
            rz = file.read('float', 0, whence='current')
            rot = toRotationMatrix(rx, ry, rz)
        else:
            rot = Matrix.Identity(4)
            (rx, ry, rz) = (0, 0, 0)
    else:
        rot = Matrix.Identity(4)
        (rx, ry, rz) = (0, 0, 0)
    
    scaAddr = file.read('uint', address, offset=0x14)
    if scaAddr != 0:
        file.seek(scaAddr)
        sx = file.read('float', scaAddr)
        sy = file.read('float', 0, whence='current')
        sz = file.read('float', 0, whence='current')
        sca = toScaleMatrix(sx, sy, sz)
    else:
        sca = Matrix.Identity(4)
        (sx, sy, sz) = (1, 1, 1)


    sp = Vector((0.0, 0.0, 0.0))
    st = Vector((0.0, 0.0, 0.0))
    rp = Vector((0.0, 0.0, 0.0))
    rt = Vector((0.0, 0.0, 0.0))
    pivots = [sp, st, rp, rt]
    
    if k == 0x2:
        # bind pose rotation
        brx = file.read('float', address, offset=0x34)
        bry = file.read('float', 0, whence='current')
        brz = file.read('float', 0, whence='current')
        rot2 = toRotationMatrix(brx, bry, brz)
        orot = rot
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
        transPointer = file.read('uint', address, offset=0x18)
        if transPointer:
            print("MAYA MEME DETECTED IN ", name)
            precomputed = sceneSettings['precomputedPivots']
            file.seek(transPointer)
            if precomputed:
                length = 3
                rt[0] = rt[1] = rt[2] = float('inf')
            else:
                length = 4 #len(pivots)

            for i in range(length):
                V = pivots[i]
                for j in range(3):
                    V[j] = file.read('float', 0, whence='current')

        mat = [[1.0, 0.0, 0.0, 0.0],
               [0.0, 1.0, 0.0, 0.0],
               [0.0, 0.0, 1.0, 0.0],
               [0.0, 0.0, 0.0, 1.0]]
        rot2 = Matrix.Identity(4)
        orot = Matrix.Identity(4)

    mat = Matrix(mat)
    bone = Bone(idx, name, k, pivots, (pos @ rot @ sca), mat, rot2, (rx, ry, rz), (sx, sy, sz), (x, y, z), nodeFlags, boneFlags)
    bone.type = k
    bone.idk1 = file.read('uint', address, offset=0x40)
    bone.idk2 = file.read('uint', address, offset=0x74)
    bones[idx] = bone

    animDataAddr = file.read('uint', address, offset=0x20)
    if animDataAddr != 0:
        parseFCurves(file, animDataAddr, name)
    
    childAddr = file.read('uint', address, offset=0x24)
    if childAddr != 0:
        for child in parseBones(file, childAddr, bones, useDefaultPose, sceneSettings):
            bone.childIndices.append(child.index)
            child.parentIndex = idx
            
    if k == 0x3: # skin node
        meshAddr = file.read('uint', address, offset=0x30)
        # very hack-y fix to a bug I need to look closer at
        meshStartAddr = file.read('uint', meshAddr, offset=0x18)
        if meshStartAddr != 0:
            if meshAddr not in mesh_dict:
                mesh_dict[meshAddr] = {
                    'object': parseMesh(file, meshAddr),
                    'index': len(mesh_dict)
                }
            bone.meshIndex = mesh_dict[meshAddr]['index']
    yield bone
    
    nextAddr = file.read('uint', address, offset=0x28)
    if nextAddr != 0:
        for sibling in parseBones(file, nextAddr, bones, useDefaultPose, sceneSettings):
            yield sibling

def parseModel(path, useDefaultPose=False):
    global mesh_dict, mat_dict, tex_dict, img_dict, anim_dict
    mesh_dict = {}
    mat_dict = {}
    tex_dict = {}
    img_dict = {}
    anim_dict = {}

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

        idk = file.read('uchar', 0x0)
        idk1 = file.read('ushort', 0x2)
        idk2 = file.read('uchar', 0x4)

        sceneSettings = {'precomputedPivots': (idk < 1) or (idk1 < 3) or (idk2 == 0)}

        materialsListAddr = file.read('uint', 0x14)
        numMaterials = file.read('ushort', 0x1c)
        for i in range(numMaterials):
            materialAddr = file.read('uint', materialsListAddr, offset=(4 * i))
            mat_dict[materialAddr] = {
                'object': parseMaterial(file, materialAddr),
                'index': len(mat_dict)
            }

        skeletonHeaderAddr = file.read('uint', 0x8)
        skele = parseSkeleton(file, skeletonHeaderAddr, useDefaultPose, sceneSettings)
        skeletons.append(skele)
    else:
        texturesListAddr = file.read('uint', 0xc)
        numTextures = file.read('ushort', 0x1a)
        parseTextures(file, texturesListAddr, numTextures)

        idk = file.read('uchar', 0x0)
        idk1 = file.read('ushort', 0x2)
        idk2 = file.read('uchar', 0x4)

        sceneSettings = {'precomputedPivots': (idk < 1) or (idk1 < 3) or (idk2 == 0)}

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
            skele = parseSkeleton(file, skeletonHeaderAddr, useDefaultPose, sceneSettings)
            skeletons.append(skele)
        
    
    file.close()
    
    sdr = {
        'skeletons': skeletons,
        'meshes': flattenIndexedDict(mesh_dict),
        'materials': flattenIndexedDict(mat_dict),
        'textures': flattenIndexedDict(tex_dict),
        'images': flattenIndexedDict(img_dict),
        'actions': anim_dict
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
                         w * (Matrix.Identity(4))
        #                w * (bones[idx].globalTransform @ \
        #                     bones[idx].inverseBindMatrix)
        #                 w * (bones[idx].inverseBindMatrix)
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

def makeAction(actionData, arma, skele):
    sampleFramerate = max(60, bpy.context.scene.render.fps) # hardcoded for now
    action = bpy.data.actions.new(actionData['name'])
    ttimes = []
    for boneName in actionData['bones']:
        for bone in skele.bones:
            if bone.name == boneName:
                break

        b = bpy.context.object.pose.bones[bone.name]

        # temp components and static values
        temporaryComponents = {
            'location': ('t', bone.initialTrans),
            'rotation_euler': ('r', bone.initialRot),
            'scale': ('s', bone.initialScale),
        }
        # bake animation

        times = [0] * 7
        times[0] = time.time()

        # move normal channels into temporary ones for sampling
        endTime = 0 
        temporaryCurves = {}
        for fcurveData in actionData['bones'][boneName]:
            tempComponent = temporaryComponents[fcurveData['component']][0]
            axis = fcurveData['axis'] - 1
            tempDatapath = f'pose.bones["{boneName}"].{tempComponent}'
            existingCurve = action.fcurves.find(tempDatapath, index = axis)
            if existingCurve:
                action.fcurves.remove(existingCurve)
            fcurve = action.fcurves.new(tempDatapath, index=axis)
            temporaryCurves[f'{tempComponent}{axis}'] = fcurve

            duplicateFrames = []

            for i, keyframe in enumerate(fcurveData['keyframes']):
                endTime = max(endTime, keyframe['time'])
                frame = keyframe['time'] * bpy.context.scene.render.fps
                oldKeyframeCount = len(fcurve.keyframe_points)
                kframe = fcurve.keyframe_points.insert(frame, keyframe['value'])
                newKeyframeCount = len(fcurve.keyframe_points)
                kframe.handle_right_type = kframe.handle_left_type = 'FREE'
                kframe.interpolation = keyframe['interpolation']
                if newKeyframeCount != oldKeyframeCount + 1:
                    print('duplicate keyframe time! ', i)
                    duplicateFrames.append(i)
            
            keyframes = fcurve.keyframe_points[:]

            i = 0

            for j, keyframe in enumerate(fcurveData['keyframes']):

                if j in duplicateFrames:
                    continue

                kx = keyframes[i].co[0]
                ky = keyframes[i].co[1]
                if i > 0:
                    dtL = keyframes[i].co[0] - keyframes[i - 1].co[0]
                    dxL = keyframe['derivativeL']
                    keyframes[i].handle_left[0] = kx - dtL / 3
                    keyframes[i].handle_left[1] = ky - dxL / 3
                    

                if i < len(keyframes) - 1:
                    dtR = keyframes[i + 1].co[0] - keyframes[i].co[0]
                    dxR = keyframe['derivativeR']
                    keyframes[i].handle_right[0] = kx + dtR / 3
                    keyframes[i].handle_right[1] = ky + dxR / 3


                i += 1

        sampleFrames = math.ceil(sampleFramerate * endTime)

        # add curves for non-animated channels to make next step simpler
        for ax in [0, 1, 2]:
            for c, base in temporaryComponents.values():
                if f'{c}{ax}' not in temporaryCurves:
                    tempDatapath = f'pose.bones["{boneName}"].{c}'
                    fcurve = action.fcurves.new(tempDatapath, index=ax)
                    temporaryCurves[f'{c}{ax}'] = fcurve
                    fcurve.keyframe_points.insert(0, base[ax])

        # add proper channels
        finalCurves = {}
        for ax in [0, 1, 2]:
            for component, (c, _) in temporaryComponents.items():
                datapath = f'pose.bones["{boneName}"].{component}'
                fcurve = action.fcurves.new(datapath, index=ax)
                finalCurves[f'{c}{ax}'] = fcurve

        times[1] = time.time()

        for s in ['s0', 's1', 's2', 'r0', 'r1', 'r2', 't0', 't1', 't2']:
            finalCurves[s].keyframe_points.add(sampleFrames)
            for i in range(sampleFrames):
                frame = i * bpy.context.scene.render.fps / sampleFramerate
                finalCurves[s].keyframe_points[i].co[0] = frame

        times[2] = time.time()

        # sample
        rate = bpy.context.scene.render.fps / sampleFramerate
        scale = np.array([Vector((temporaryCurves['s0'].evaluate(frame * rate),
                                  temporaryCurves['s1'].evaluate(frame * rate),
                                  temporaryCurves['s2'].evaluate(frame * rate), 1.0)) for frame in range(sampleFrames)])
        
        translation = np.array([Matrix.Translation(Vector((temporaryCurves['t0'].evaluate(frame * rate),
                                                           temporaryCurves['t1'].evaluate(frame * rate),
                                                           temporaryCurves['t2'].evaluate(frame * rate)))) for frame in range(sampleFrames)])

        rotation = np.array([Euler((temporaryCurves['r0'].evaluate(frame * rate),
                                    temporaryCurves['r1'].evaluate(frame * rate),
                                    temporaryCurves['r2'].evaluate(frame * rate))).to_matrix().to_4x4() for frame in range(sampleFrames)])

        times[3] = time.time()

        if bone.type == 2:

            local = bone.localTransform
            if b.parent:
                relativeBind = b.parent.bone.matrix_local.inverted() @ b.bone.matrix_local
            else:
                relativeBind = b.bone.matrix_local

            invRelativeBind = relativeBind.inverted()
            jointOrientation = bone.bindRotation

            # scale corrections for blender
            s = bone.inverseBindMatrix.inverted().to_scale()
            C_1 = Matrix.Diagonal((1 / s[0], 1 / s[1], 1 / s[2], 1.0))
            
            if b.parent:
                s = bone.invparentBind.inverted().to_scale()
                C_2 = Matrix.Diagonal((s[0], s[1], s[2], 1.0))

            if b.parent:
                correctedMatrix = np.einsum('...sh,hi,...in,nm,...mj,...j,jt->...st', invRelativeBind, C_2, translation, jointOrientation, rotation, scale, C_1, optimize='greedy')
            else:
                correctedMatrix = np.einsum('...si,...in,nm,...mj,...j,jt->...st', invRelativeBind, translation, jointOrientation, rotation, scale, C_1, optimize='greedy')
            

        elif (bone.type == 0 or bone.type == 3 or bone.type == 5 or bone.type == 6 or bone.type == 7):
            # GSnull, GSmodel, GSlight, GSvolume, GSparticle

            # time for maya memes
            precomputed = (bone.RotationPivotTranslate[0] == float('inf') 
                        or bone.RotationPivotTranslate[1] == float('inf')
                        or bone.RotationPivotTranslate[2] == float('inf'))
            if precomputed:
                T_1 = bone.ScalePivot
                T_2 = bone.ScalePivotTranslate
                T_3 = bone.RotatePivot
            else:
                T_1 = -bone.ScalePivot
                T_2 = bone.ScalePivot + bone.ScalePivotTranslate - bone.RotatePivot
                T_3 = bone.RotatePivot + bone.RotationPivotTranslate

            T_1 = Matrix.Translation(T_1)
            T_2 = Matrix.Translation(T_2)
            T_3 = Matrix.Translation(T_3)

            local = bone.localTransform
            if b.parent:
                relativeBind = b.parent.bone.matrix_local.inverted() @ b.bone.matrix_local
            else:
                relativeBind = b.bone.matrix_local

            invRelativeBind = relativeBind.inverted()

            correctedMatrix = np.einsum('...ij,...jk,kl,...lm,mt,...t,ts->...is', invRelativeBind, translation, T_3, rotation, T_2, scale, T_1, optimize='greedy')

        elif bone.type == 1:
            print("What the fuck is node type 1?")
        else:
            # TODO: camera
            print("Camera animations are currently not implemented")

        times[4] = time.time()

        times[5] = time.time()

        for i in range(sampleFrames):
            trans, rot, scale = Matrix(correctedMatrix[i]).decompose()
            rot = rot.to_euler()
            finalCurves['s0'].keyframe_points[i].co[1] = scale[0]
            finalCurves['s0'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['s1'].keyframe_points[i].co[1] = scale[1]
            finalCurves['s1'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['s2'].keyframe_points[i].co[1] = scale[2]
            finalCurves['s2'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['r0'].keyframe_points[i].co[1] = rot[0]
            finalCurves['r0'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['r1'].keyframe_points[i].co[1] = rot[1]
            finalCurves['r1'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['r2'].keyframe_points[i].co[1] = rot[2]
            finalCurves['r2'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['t0'].keyframe_points[i].co[1] = trans[0]
            finalCurves['t0'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['t1'].keyframe_points[i].co[1] = trans[1]
            finalCurves['t1'].keyframe_points[i].interpolation = 'CONSTANT'
            finalCurves['t2'].keyframe_points[i].co[1] = trans[2]
            finalCurves['t2'].keyframe_points[i].interpolation = 'CONSTANT'

        times[6] = time.time()
        ttimes.append(times)
        
        # remove temporary curves
        for fcurve in temporaryCurves.values():
            action.fcurves.remove(fcurve)

    times = [0] * 6
    total = 0
    for times_ in ttimes:
        durations = [times_[i + 1] - times_[i] for i in range(len(times_) - 1)]
        for i in range(len(times)):
            times[i] += durations[i]
            total += durations[i]
        
    times = [f"{t / total * 100:3.2f}%" for t in times]
    print(' '.join(times))


def makeObject(context, meshData, partData, material, bones, meshBone):
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
    else:
        # rigid skin
        name = meshBone.name
        for i in range(len(meshData.vertices)):
            if name not in o.vertex_groups:
                o.vertex_groups.new(name=name)
            o.vertex_groups[name].add([i], 1.0, 'REPLACE')
    return o

def makeArmature_r(edit_bones, bones, boneIndex):
    boneData = bones[boneIndex]
    bone = edit_bones.new(boneData.name)
    bone.tail = (0, 0, 0.5) # length = 0.5
    bone.matrix = boneData.inverseBindMatrix.inverted()
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
    for bone in skele.bones:
        b = arma.pose.bones[bone.name]

        # another maya meme: scale compensation
        if b.parent:
            isBone = bone.type == 2
            dontInheritScale = isBone and (bone.nodeFlags >> 3) & 1 and (bone.boneFlags & 8)
            if dontInheritScale:
                b.bone.inherit_scale = 'NONE_LEGACY'

        if b.name != bone.name:
            print("DUPLICATE BONE NAME: ", b.name, " ", bone.name)

        local = bone.localTransform
        if b.parent:
            relativeBind = b.parent.bone.matrix_local.inverted() @ b.bone.matrix_local
        else:
            relativeBind = b.bone.matrix_local

        # scale corrections for blender
        s = bone.inverseBindMatrix.to_scale()
        C = Matrix.Diagonal((s[0], s[1], s[2], 1.0))
        local = local @ C
        
        if b.parent:
            s = bone.invparentBind.to_scale()
            C = Matrix.Diagonal((1 / s[0], 1 / s[1], 1 / s[2], 1.0))
            local = C @ local

        b.matrix_basis = relativeBind.inverted() @ local
        b["type"] = bone.type
        b["flag"] = "{0:b}".format(bone.nodeFlags)
        b["idk1"] = hex(bone.idk1)
        b["idk2"] = hex(bone.idk2)
    
    return arma

def importSDR(context, path, useDefaultPose=False, joinMeshes=False):
    model_data = parseModel(path, useDefaultPose)

    # save images
    images = model_data['images']
    for i in range(len(images)):
        img = images[i]
        image = bpy.data.images.new(f'image{i}', img.width, img.height)
        # Blender expects values to be normalized
        image.pixels = [(x / 255) for x in img.pixels][:len(image.pixels)]
        #path = f'{os.path.dirname(path)}/texture{i}.png'
        #image.filepath_raw = path
        #image.file_format = 'PNG'
        #image.save()
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
        arma.animation_data_create()
        for bone in arma.pose.bones:
            bone.rotation_mode = 'XYZ'
        for action in anim_dict:
            makeAction(anim_dict[action], arma, skele)
        arma.select_set(False)
        # create meshes
        for bone in skele.bones:
            if bone.meshIndex != None:
                mesh = meshes[bone.meshIndex]
                parts = []
                bpy.ops.object.select_all(action='DESELECT')
                for part in mesh.parts:
                    mat = materials[part.materialIndex]
                    obj = makeObject(context, mesh, part, mat, skele.bones, bone)
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
