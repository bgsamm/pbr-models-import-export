import os, math, struct
from mathutils import Euler, Matrix
from .gtx import imagify
from .classes import *
from .const import *

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

def readString(file, offset):
    s = ''
    file.seek(offset)
    nextChar = int.from_bytes(file.read(1), 'big')
    while nextChar != 0:
        s += chr(nextChar)
        nextChar = int.from_bytes(file.read(1), 'big')
    return s

def toRotationMatrix(x, y, z):
    return Euler((x, y, z), 'XYZ').to_matrix().to_4x4()

def toScaleMatrix(x, y, z):
    sX = Matrix.Scale(x, 4, (1, 0, 0))
    sY = Matrix.Scale(y, 4, (0, 1, 0))
    sZ = Matrix.Scale(z, 4, (0, 0, 1))
    return sZ @ sY @ sX

def flattenIndexedDict(d):
    return [data['object'] for addr,data in
            sorted(d.items(), key=lambda item: item[1]['index'])]

def parseTextures(file, offset, numTextures):
    for i in range(numTextures):
        file.seek(offset + 0x4 * i)
        textureHeaderAddr = int.from_bytes(file.read(4), 'big')
        file.seek(textureHeaderAddr + 0x10)
        ext = int.from_bytes(file.read(4), 'big')
        file.seek(textureHeaderAddr + 0x28)
        imageOffset = int.from_bytes(file.read(4), 'big')
        imageAddr = textureHeaderAddr + imageOffset
        if imageAddr not in img_dict:
            img = extractImage(file, textureHeaderAddr, imageAddr)
            img_dict[imageAddr] = {
                'object': img,
                'index': len(img_dict)
            }
        tex = Texture(img_dict[imageAddr]['index'], ext)
        tex_dict[textureHeaderAddr] = {
            'object': tex,
            'index': len(tex_dict)
        }
        
def extractImage(file, offset, imageAddr):
    file.seek(offset)
    textureWidth = int.from_bytes(file.read(2), 'big')
    textureHeight = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x8)
    textureEncoding = int.from_bytes(file.read(4), 'big')
    file.seek(offset + 0x10)
    isRepeating = int.from_bytes(file.read(4), 'big') == 1
    file.seek(offset + 0x4c)
    textureSize = int.from_bytes(file.read(4), 'big')
    file.seek(imageAddr)
    image = imagify(file.read(textureSize),
                  textureWidth,
                  textureHeight,
                  encodings[textureEncoding])
    return image

def parseMaterials(file, offset, numMaterials):
    for i in range(numMaterials):
        file.seek(offset + 0x4 * i)
        materialHeaderAddr = int.from_bytes(file.read(4), 'big')
        mat_dict[materialHeaderAddr] = {
            'object': parseMaterial(file, materialHeaderAddr),
            'index': len(mat_dict)
        }

def parseMaterial(file, offset):
    file.seek(offset)
    materialNameAddr = int.from_bytes(file.read(4), 'big')
    name = readString(file, materialNameAddr)
    file.seek(offset + 0x18)
    textureAddr = int.from_bytes(file.read(4), 'big')
    if textureAddr == 0:
        return Material(name, None)
    return Material(name, tex_dict[textureAddr]['index'])

def parseVertices(file, offset, numEntries, entrySize):
    vertices = []
    for i in range(numEntries):
        file.seek(offset + i * entrySize)
        x = struct.unpack('>f', file.read(4))[0]
        y = struct.unpack('>f', file.read(4))[0]
        z = struct.unpack('>f', file.read(4))[0]
        vertices.append((x, y, z))
    return vertices

def parseNormals(file, offset, numEntries, entrySize):
    normals = []
    for i in range(numEntries):
        file.seek(offset + i * entrySize + 0xc)
        nx = struct.unpack('>f', file.read(4))[0]
        ny = struct.unpack('>f', file.read(4))[0]
        nz = struct.unpack('>f', file.read(4))[0]
        normals.append((nx, ny, nz))
    return normals

def parseTextureCoords(file, offset, numEntries, entrySize):
    texcoords = []
    for i in range(numEntries):
        file.seek(offset + i * entrySize)
        x = struct.unpack('>f', file.read(4))[0]
        y = 1.0 - struct.unpack('>f', file.read(4))[0]
        texcoords.append((x, y))
    return texcoords

def parseWeights(file, offset):
    weights = []
    
    file.seek(offset)
    n = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x4)
    addr1 = int.from_bytes(file.read(4), 'big')
    file.seek(addr1)
    for i in range(n):
        numVerts = int.from_bytes(file.read(2), 'big')
        bone1 = int.from_bytes(file.read(2), 'big')
        for j in range(numVerts):
            weights.append({bone1: 1.0})

    file.seek(offset + 0x8)
    n = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0xc)
    addr1 = int.from_bytes(file.read(4), 'big')
    addr2 = int.from_bytes(file.read(4), 'big')
    count = 0
    for i in range(n):
        file.seek(addr1 + i * 0x6)
        numVerts = int.from_bytes(file.read(2), 'big')
        bone1 = int.from_bytes(file.read(2), 'big')
        bone2 = int.from_bytes(file.read(2), 'big')
        file.seek(addr2 + count * 0x2)
        for j in range(numVerts):
            w = int.from_bytes(file.read(2), 'big') / 0xffff
            weights.append({bone1: w, bone2: 1 - w})
        count += numVerts

    file.seek(offset + 0x14)
    n = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x18)
    addr1 = int.from_bytes(file.read(4), 'big')
    file.seek(addr1)
    for i in range(n):
        vertNum = int.from_bytes(file.read(2), 'big')
        bone1 = int.from_bytes(file.read(2), 'big')
        bone2 = int.from_bytes(file.read(2), 'big')
        w1 = int.from_bytes(file.read(2), 'big') / 0xffff
        w2 = int.from_bytes(file.read(2), 'big') / 0xffff
        for bone in weights[vertNum]:
            weights[vertNum][bone] *= 1 - w1 - w2
        weights[vertNum][bone1] = w1
        if bone2 != 0xffff:
            weights[vertNum][bone2] = w2

    return weights

def parseFaces(file, offset, numGroups, vertAttrs):
    file.seek(offset)
    faces = []
    for i in range(numGroups):
        op = int.from_bytes(file.read(1), 'big')
        count = int.from_bytes(file.read(2), 'big')
        vertices = []
        for j in range(count):
            v = n = t = None
            for i in range(len(vertAttrs)):
                if vertAttrs[i] == GX_VA_POS:
                    v = int.from_bytes(file.read(2), 'big')
                elif vertAttrs[i] in [GX_VA_NRM, GX_VA_NBT]:
                    n = int.from_bytes(file.read(2), 'big')
                elif vertAttrs[i] == GX_VA_TEX0:
                    t = int.from_bytes(file.read(2), 'big')
                else:
                    file.read(2)
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

def parseMesh(file, offset):
    file.seek(offset + 0x18)
    meshHeaderAddr = int.from_bytes(file.read(4), 'big')
    file.seek(meshHeaderAddr + 0x10)
    vertexInfoAddr = int.from_bytes(file.read(4), 'big')
    
    # vertices
    file.seek(offset + 0x2)
    numVertices = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x8)
    verticesAddr = int.from_bytes(file.read(4), 'big')
    file.seek(vertexInfoAddr + 0x5)
    vertexSize = int.from_bytes(file.read(1), 'big')
    v = parseVertices(file, verticesAddr, numVertices, vertexSize)
    
    # vertex normals
    n = parseNormals(file, verticesAddr, numVertices, vertexSize)

    # texture coordinates
    file.seek(offset + 0x14)
    texCoordsHeaderAddr = int.from_bytes(file.read(4), 'big')
    t = None
    if texCoordsHeaderAddr != 0:
        file.seek(texCoordsHeaderAddr)
        texCoordsAddr = int.from_bytes(file.read(4), 'big')
        numTexCoords = int.from_bytes(file.read(2), 'big')
        file.seek(vertexInfoAddr + 0x15)
        texCoordSize = int.from_bytes(file.read(1), 'big')
        t = parseTextureCoords(file, texCoordsAddr, numTexCoords, texCoordSize)

    # bone weights
    file.seek(offset + 0xc)
    boneWeightsAddr = int.from_bytes(file.read(4), 'big')
    if boneWeightsAddr != 0:
        w = parseWeights(file, boneWeightsAddr)
    else:
        w = None

    meshGroup = Mesh(v, n, t, w)
    for mesh in parseMeshPart(file, meshHeaderAddr):
        meshGroup.parts.append(mesh)
    return meshGroup

def parseMeshPart(file, offset):
    file.seek(offset + 0x10)
    vertexInfoAddr = int.from_bytes(file.read(4), 'big')
    file.seek(vertexInfoAddr)
    va = int.from_bytes(file.read(1), 'big')
    vas = []
    while va != 0xff:
        vas.append(va)
        file.seek(0x7, 1)
        va = int.from_bytes(file.read(1), 'big')
    
    file.seek(offset + 0x8)
    materialAddr = int.from_bytes(file.read(4), 'big')
    file.seek(offset + 0xc)
    numGroups = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x14)
    facesAddr = int.from_bytes(file.read(4), 'big')
    f = parseFaces(file, facesAddr, numGroups, vas)
    mesh = MeshPart(f, GX_VA_TEX0 in vas, mat_dict[materialAddr]['index'])
    yield mesh
    
    # check if has child
    file.seek(offset + 0x1c)
    nextMeshAddr = int.from_bytes(file.read(4), 'big')
    if nextMeshAddr != 0:
        for mesh in parseMeshPart(file, nextMeshAddr):
            yield mesh

def parseSkeleton(file, offset):
    file.seek(offset)
    objNameAddr = int.from_bytes(file.read(4), 'big')
    name = readString(file, objNameAddr)
    file.seek(offset + 0x6)
    numBones = int.from_bytes(file.read(2), 'big')
    file.seek(offset + 0x10)
    rootAddr = int.from_bytes(file.read(4), 'big')
    bones = [None] * numBones
    rootBone = next(parseBones(file, rootAddr, bones))
    return Skeleton(name, numBones, bones)

def parseBones(file, offset, bones):
    file.seek(offset)
    k = int.from_bytes(file.read(4), 'big')
    
    file.seek(offset + 0x4)
    nameAddr = int.from_bytes(file.read(4), 'big')
    name = readString(file, nameAddr)
    
    file.seek(offset + 0x8)
    idx = int.from_bytes(file.read(2), 'big')
    
    file.seek(offset + 0xc)
    posAddr = int.from_bytes(file.read(4), 'big')
    if posAddr != 0:
        file.seek(posAddr)
        x = struct.unpack('>f', file.read(4))[0]
        y = struct.unpack('>f', file.read(4))[0]
        z = struct.unpack('>f', file.read(4))[0]
        pos = Matrix.Translation((x, y, z))
    else:
        pos = Matrix.Identity(4)
        
    file.seek(offset + 0x10)
    rotAddr = int.from_bytes(file.read(4), 'big')
    if rotAddr != 0:
        file.seek(rotAddr)
        x = struct.unpack('>f', file.read(4))[0]
        y = struct.unpack('>f', file.read(4))[0]
        z = struct.unpack('>f', file.read(4))[0]
        rot = toRotationMatrix(x, y, z)
    else:
        rot = Matrix.Identity(4)
        
    file.seek(offset + 0x14)
    scaAddr = int.from_bytes(file.read(4), 'big')
    if scaAddr != 0:
        file.seek(scaAddr)
        x = struct.unpack('>f', file.read(4))[0]
        y = struct.unpack('>f', file.read(4))[0]
        z = struct.unpack('>f', file.read(4))[0]
        sca = toScaleMatrix(x, y, z)
    else:
        sca = Matrix.Identity(4)
        
    if k == 0x2:
        # secondary rotation
        file.seek(offset + 0x34)
        x = struct.unpack('>f', file.read(4))[0]
        y = struct.unpack('>f', file.read(4))[0]
        z = struct.unpack('>f', file.read(4))[0]
        rot2 = toRotationMatrix(x, y, z)
        rot = rot2 @ rot
        # inverse bind matrix
        mat = []
        file.seek(offset + 0x44)
        for r in range(3):
            row = []
            for c in range(4):
                row.append(struct.unpack('>f', file.read(4))[0])
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
    
    file.seek(offset + 0x24)
    childAddr = int.from_bytes(file.read(4), 'big')
    if childAddr != 0:
        for child in parseBones(file, childAddr, bones):
            bone.childIndices.append(child.index)
            child.parentIndex = idx
            
    if k == 0x3:
        file.seek(offset + 0x30)
        meshHeaderAddr = int.from_bytes(file.read(4), 'big')
        if meshHeaderAddr not in mesh_dict:
            mesh_dict[meshHeaderAddr] = {
                'object': parseMesh(file, meshHeaderAddr),
                'index': len(mesh_dict)
            }
        bone.meshIndex = mesh_dict[meshHeaderAddr]['index']
    yield bone
    
    file.seek(offset + 0x28)
    nextAddr = int.from_bytes(file.read(4), 'big')
    if nextAddr != 0:
        for sibling in parseBones(file, nextAddr, bones):
            yield sibling

def parseSDR(path):
    global mesh_dict, mat_dict, tex_dict, img_dict
    mesh_dict = {}
    mat_dict = {}
    tex_dict = {}
    img_dict = {}

    file = open(path, 'rb')

    # textures
    file.seek(0xc)
    texturesListAddr = int.from_bytes(file.read(4), 'big')
    file.seek(0x1a)
    numTextures = int.from_bytes(file.read(2), 'big')
    parseTextures(file, texturesListAddr, numTextures)
    
    # materials
    file.seek(0x14)
    materialsListAddr = int.from_bytes(file.read(4), 'big')
    file.seek(0x1e)
    numMaterials = int.from_bytes(file.read(2), 'big')
    parseMaterials(file, materialsListAddr, numMaterials)
    
    # skeleton
    file.seek(0x8)
    skeletonsListAddrPtr = int.from_bytes(file.read(4), 'big')
    file.seek(0x18)
    numSkeletons = int.from_bytes(file.read(2), 'big')
    skeletons = []
    for i in range(numSkeletons):
        file.seek(skeletonsListAddrPtr + 4 * i)
        skeletonHeaderAddr = int.from_bytes(file.read(4), 'big')
        skeletons.append(parseSkeleton(file, skeletonHeaderAddr))
    
    file.close()
    
    sdr = {
        'skeletons': skeletons,
        'meshes': flattenIndexedDict(mesh_dict),
        'materials': flattenIndexedDict(mat_dict),
        'textures': flattenIndexedDict(tex_dict),
        'images': flattenIndexedDict(img_dict)
    }
    return sdr
