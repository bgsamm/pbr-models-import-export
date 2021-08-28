import bpy, struct
from time import time
from ..shared.file_io import BinaryWriter

arma = None
bones = None

materials = []
textures = {}

matListAddr = 0

def isSkin(name):
    return name in (mesh.name for mesh in arma.children)

def getMatTexture(material):
    return [n for n in material.node_tree.nodes if n.type == 'TEX_IMAGE'][0]

# still a little slow but acceptable; should pre-allocate
def imageToRGB5A3(image):
    w,h = image.size
    num_blocks_x = w // 4
    num_blocks_y = h // 4
    # converting to ints in advance significantly improves speed
    rgba = [int(f * 255) for f in image.pixels]
    data = bytes()
    # add rows bottom-to-top to cooperate with Blender
    for row in range(num_blocks_y - 1, -1, -1):
        for col in range(num_blocks_x):
            for i in range(3, -1, -1):
                for j in range(4):
                    pos = (row * w * 4 + col * 4 + i * w + j) * 4
                    r,g,b,a = rgba[pos:pos+4]
                    if a < 255:
                        val = ((a >> 5) << 12) + \
                              ((r // 0x11) << 8) + \
                              ((g // 0x11) << 4) + \
                              (b // 0x11)
                    else:
                        val = 0x8000 + \
                              ((r >> 3) << 10) + \
                              ((g >> 3) << 5) + \
                              (b >> 3)
                    data += val.to_bytes(2, 'big')
    return data

def imageToRGBA32(image):
    w,h = image.size
    num_blocks_x = w // 4
    num_blocks_y = h // 4
    rgba = [int(f * 255) for f in image.pixels]
    data = [None] * (w * h * 4) # pre-allocate to increase speed
    for row in range(num_blocks_y):
        for col in range(num_blocks_x):
            offset = (row * w * 4 + col * 4) * 4
            # each block is 4x4 pixels
            for i in range(4):
                for j in range(4):
                    pos = (row * w * 4 + col * 4 + i * w + j) * 4
                    idx = (row * num_blocks_x + col) * 64 + (i * 4 + j) * 2
                    data[idx] = rgba[pos+3] # a
                    data[idx+1] = rgba[pos] # r
                    data[idx+32] = rgba[pos+1] # g
                    data[idx+33] = rgba[pos+2] # b
    return bytes(data)

def writeTexture(file, address, texture):
    image = texture.image
    w,h = image.size
    file.write('ushort', w, address, offset=0)
    file.write('ushort', h, address, offset=0x2)
    file.write('uchar', 1, address, offset=0x5)
    file.write('uint', 0x90, address, offset=0x8) # encoding
    # extrapolation
    if texture.extension == 'EXTEND':
        file.write('uint', 0, address, offset=0x10) # x
        file.write('uint', 0, address, offset=0x14) # y
    elif texture.extension == 'REPEAT':
        file.write('uint', 1, address, offset=0x10) # x
        file.write('uint', 1, address, offset=0x14) # y
    else:
        raise Exception(f"Extrapolation type '{texture.extension}' unsupported")
    file.write('uint', 0x80, address, offset=0x28) # image offset
    #data = imageToRGBA32(image) # currently doesn't load correctly in-game
    data = imageToRGB5A3(image)
    file.write('uint', len(data), address, offset=0x4c)
    file.write_chunk(data, address + 0x80)
    return file.tell() + 0x10 # next address (add some padding)

def writeMaterial(file, address, material):
    nameAddr = address + 0x8c
    file.write('uint', nameAddr, address)

    # name
    file.write('string', material.name, nameAddr)
    sz = len(material.name)
    sz = (sz // 4) * 4 + 4
    nextAddr = nameAddr + sz

    texture = getMatTexture(material)
    texAddr = textures[texture.image.name]['address']
    file.write('uint', texAddr, address, offset=0x18)
    file.write('uint', nextAddr, address, offset=0x2c)
    file.write('uchar', 0x1, address, offset=0x5a)
    file.write('uchar', 0x1, 0, whence='current')
    file.write('uchar', 0x1, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0x80, address, offset=0x60)
    file.write('uchar', 0x80, 0, whence='current')
    file.write('uchar', 0x80, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, address, offset=0x64)
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0x0, address, offset=0x70)
    file.write('uchar', 0x0, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, address, offset=0x74)
    file.write('uchar', 0x33, address, offset=0x78)
    file.write('uchar', 0x33, 0, whence='current')
    file.write('uchar', 0x33, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, address, offset=0x80)
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')

    file.write('uchar', 0x1, nextAddr)
    file.write('uchar', 0x4, 0, whence='current')
    file.write('float', 0.0, 2, whence='current')
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 1.0, 0, whence='current')
    file.write('float', 1.0, 0, whence='current')

    nextAddr = file.tell()
    file.write('uint', nextAddr, address, offset=0x40)
    file.write('uchar', 0x0, nextAddr)
    file.write('uchar', 0x0, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0xff, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current')

    return file.tell() + 1

def writeBone(file, address, bone):
    # if bone name is the same as a child mesh, mark it as a skin node
    if isSkin(bone.name):
        file.write('uint', 0x3, address)
        nextAddr = address + 0x3c
    else:
        nextAddr = address + 0x30

    # skin bones cannot have any transformation
    if not isSkin(bone.name):
        if bone.parent is not None:
            transform = bone.parent.matrix_local.inverted() @ bone.matrix_local
            t,r,s = transform.decompose()
        else:
            t,r,s = bone.matrix_local.decompose()
        r = r.to_euler()
        if any(f != 0.0 for f in r):
            file.write('uint', 0x2, address)
            file.write('float', r[0], address, offset=0x34)
            file.write('float', r[1], 0, whence='current')
            file.write('float', r[2], 0, whence='current')
            nextAddr += 72 # leave room for inverse bind matrix
        if any(f != 0.0 for f in t):
            file.write('uint', nextAddr, address, offset=0xc)
            file.write('float', t[0], nextAddr)
            file.write('float', t[1], 0, whence='current')
            file.write('float', t[2], 0, whence='current')
            nextAddr += 12
        if any(f != 1.0 for f in s):
            file.write('uint', nextAddr, address, offset=0x14)
            file.write('float', s[0], nextAddr)
            file.write('float', s[1], 0, whence='current')
            file.write('float', s[2], 0, whence='current')
            nextAddr += 12
    
    nameAddr = nextAddr
    file.write('uint', nameAddr, address, offset=0x4)
    idx = bones.find(bone.name)
    file.write('ushort', idx, address, offset=0x8)
    file.write('ushort', 0x18, address, offset=0xa)

    file.write('string', bone.name, nameAddr)
    sz = len(bone.name)
    sz = (sz // 4) * 4 + 4
    nextAddr = nameAddr + sz

    if len(bone.children) > 0:
        file.write('uint', nextAddr, address, offset=0x24)
        nextAddr = writeBone(file, nextAddr, bone.children[0])

    if bone.parent is not None:
        siblings = bone.parent.children
        idx = siblings.find(bone.name)
        # if has next sibling...
        if len(siblings) > idx + 1:
            file.write('uint', nextAddr, address, offset=0x28)
            nextAddr = writeBone(file, nextAddr, siblings[idx + 1])

    return nextAddr

def writeMeshes(file, boneAddr, nextAddr):
    file.seek(boneAddr)
    # check if the bone is a skin node
    if file.read('uint', boneAddr) == 0x3:
        # if so, get the bone name
        nameAddr = file.read('uint', boneAddr, offset=0x4)
        name = file.read('string', nameAddr)
        # write the mesh address
        file.write('uint', nextAddr, boneAddr, offset=0x30)
        # write the mesh data
        mesh = bpy.data.objects[name]
        nextAddr = writeMesh(file, nextAddr, mesh)

    childAddr = file.read('uint', boneAddr, offset=0x24)
    if childAddr != 0:
        nextAddr = writeMeshes(file, childAddr, nextAddr)

    sibAddr = file.read('uint', boneAddr, offset=0x28)
    if sibAddr != 0:
        nextAddr = writeMeshes(file, sibAddr, nextAddr)

    return nextAddr

def writeMesh(file, address, object):
    mesh = object.data
    file.write('ushort', 0xa00, address)
    numVerts = len(mesh.vertices)
    file.write('ushort', numVerts, address, offset=0x2)
    file.write('ushort', 0x1, address, offset=0x6) # num. uv layers
    vertsAddr = address + 0x30
    file.write('uint', vertsAddr, address, offset=0x8)
    uvCoordsAddr = vertsAddr + len(mesh.vertices) * 0x18
    file.write('uint', uvCoordsAddr, address, offset=0x14)
    facesAddr = uvCoordsAddr + len(mesh.loops) * 0x8 + 0x8
    file.write('uint', facesAddr, address, offset=0x18)

    # write vertices & normals
    file.seek(vertsAddr)
    for v in mesh.vertices:
        # vertex
        for f in v.co:
            file.write('float', f, 0, whence='current')
        # normal
        for f in v.normal:
            file.write('float', f, 0, whence='current')

    # write uv coordinates
    file.write('uint', uvCoordsAddr + 0x8, uvCoordsAddr) # start of uv coords
    file.write('ushort', len(mesh.loops), uvCoordsAddr, offset=0x4)
    uvMap = mesh.uv_layers.active.data
    file.seek(uvCoordsAddr + 0x8)
    for loop in mesh.loops:
        coords = uvMap[loop.index].uv
        file.write('float', coords[0], 0, whence='current') # x
        file.write('float', 1.0 - coords[1], 0, whence='current') # y

    # write face groups
    for i in range(len(object.material_slots)):
        file.write('uint', 0x1, facesAddr)
        faces = [face for face in mesh.polygons if face.material_index == i]
        mat = object.material_slots[i].material
        matAddr = file.read('uint', matListAddr,
                            offset=(4 * materials.index(mat)))
        file.write('uint', matAddr, facesAddr, offset=0x8)

        file.write('ushort', 0x1, facesAddr, offset=0xc) # num. ops
        faceOpsAddr = facesAddr + 0x40
        faceOpsAddr = (faceOpsAddr // 0x20) * 0x20
        file.write('uint', faceOpsAddr, facesAddr, offset=0x14)
        faceOpsSize = 0x3 + len(faces) * 3 * 6
        faceOpsSize = (faceOpsSize // 0x10) * 0x10 + 0x10
        file.write('uint', faceOpsSize, facesAddr, offset=0x18)
        vertInfoAddr = faceOpsAddr + faceOpsSize
        file.write('uint', vertInfoAddr, facesAddr, offset=0x10)

        # faces
        file.write('uchar', 0x90, faceOpsAddr) # GX_DRAW_TRIANGLES
        file.write('ushort', len(faces) * 3, 0, whence='current')
        for face in faces:
            file.write('ushort', face.vertices[1], 0, whence='current') # vertex
            file.write('ushort', face.vertices[1], 0, whence='current') # normal
            file.write('ushort', face.loop_indices[1], 0, whence='current') # uv coord

            file.write('ushort', face.vertices[0], 0, whence='current')
            file.write('ushort', face.vertices[0], 0, whence='current')
            file.write('ushort', face.loop_indices[0], 0, whence='current')

            file.write('ushort', face.vertices[2], 0, whence='current')
            file.write('ushort', face.vertices[2], 0, whence='current')
            file.write('ushort', face.loop_indices[2], 0, whence='current')

        # vertex info
        file.write('uchar', 0x9, vertInfoAddr) # vertices
        file.write('uchar', 0x1, 0, whence='current')
        file.write('uchar', 0x4, 0, whence='current')
        file.write('uchar', 0x0, 0, whence='current')
        file.write('uchar', 0x3, 0, whence='current')
        file.write('uchar', 0x18, 0, whence='current') # stride

        file.write('uchar', 0xa, 2, whence='current') # normals
        file.write('uchar', 0x0, 0, whence='current')
        file.write('uchar', 0x4, 0, whence='current')
        file.write('uchar', 0x0, 0, whence='current')
        file.write('uchar', 0x3, 0, whence='current')
        file.write('uchar', 0x18, 0, whence='current') # stride

        file.write('uchar', 0xd, 2, whence='current') # uv coords
        file.write('uchar', 0x1, 0, whence='current')
        file.write('uchar', 0x4, 0, whence='current')
        file.write('uchar', 0x0, 0, whence='current')
        file.write('uchar', 0x3, 0, whence='current')
        file.write('uchar', 0x8, 0, whence='current') # stride

        file.write('uchar', 0xff, 2, whence='current')

        nextAddr = vertInfoAddr + 0xc0
        if i < len(object.material_slots) - 1:
            file.write('uint', nextAddr, facesAddr, offset=0x1c)
            facesAddr = nextAddr

    # ??? (model scaling information)
    unknownAddr = nextAddr
    file.write('uint', unknownAddr, address, offset=0x1c)
    file.write('ushort', 0x1, unknownAddr, offset=0x18) # count
    file.write('uint', unknownAddr + 0x24, unknownAddr, offset=0x1c)
    
    file.write('ushort', 0x1, unknownAddr, offset=0x24) # count
    file.write('uchar', 0x1e, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current') # could be 0x8
    file.write('uint', unknownAddr + 0x30, 0, whence='current')
    
    file.write('float', 0.0, unknownAddr, offset=0x30)
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 1.0, 0, whence='current')
    file.write('float', 4.0, 0, whence='current') # this is the down-scale factor
    file.write('float', 1.0, 0, whence='current')

    return file.tell()

def writeSDR(path, context):
    assert context.object.type == 'ARMATURE'

    global arma
    global bones
    global materials
    global textures
    global matListAddr

    arma = context.object
    bones = arma.data.bones

    meshes = [child for child in arma.children if child.type == 'MESH']
    materials = []
    for mesh in meshes:
        materials += [slot.material for slot in mesh.material_slots]
    textures = {}
    for mat in materials:
        tex = getMatTexture(mat)
        if tex.image.name not in textures:
            textures[tex.image.name] = tex

    fout = BinaryWriter(path)
    fout.write('uchar', 0x1, 0)
    fout.write('ushort', 0x4, 0x2)

    # textures
    texListAddr = 0x30
    fout.write('uint', texListAddr, 0xc)
    fout.write('ushort', len(textures), 0x1a)

    nextAddr = texListAddr + 4 * len(textures)
    nextAddr = (nextAddr // 0x10) * 0x10 + 0x10
    i = 0
    for tex in textures.values():
        textures[tex.image.name]['address'] = nextAddr
        fout.write('uint', nextAddr, texListAddr, offset=(4 * i))
        nextAddr = writeTexture(fout, nextAddr, tex)
        i += 1

    # materials
    matListAddr = nextAddr
    fout.write('uint', matListAddr, 0x14)
    fout.write('ushort', len(materials), 0x1e)

    nextAddr = matListAddr + 4 * len(materials)
    nextAddr = (nextAddr // 0x10) * 0x10 + 0x10
    for i in range(len(materials)):
        fout.write('uint', nextAddr, matListAddr, offset=(4 * i))
        nextAddr = writeMaterial(fout, nextAddr, materials[i])

    # skeleton
    skeleListAddr = nextAddr
    skeleAddr = skeleListAddr + 0x10
    skeleNameAddr = skeleAddr + 0x1c
    fout.write('uint', skeleListAddr, 0x8)
    fout.write('ushort', 0x1, 0x18) # skeleton count
    fout.write('uint', skeleAddr, skeleListAddr)
    
    fout.write('uint', skeleNameAddr, skeleAddr, offset=0)
    fout.write('ushort', len(bones), skeleAddr, offset=0x6)
    fout.write('string', bones[0].name, skeleNameAddr) # skeleton name (just uses root bone name)

    sz = len(bones[0].name)
    sz = (sz // 4) * 4 + 4
    rootAddr = skeleNameAddr + sz
    fout.write('uint', rootAddr, skeleAddr, offset=0x10) # root bone pointer
    nextAddr = writeBone(fout, rootAddr, bones[0]) # write bone tree

    # meshes
    writeMeshes(fout, rootAddr, nextAddr)

    fout.close()
