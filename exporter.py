import bpy, struct
from time import time

assert bpy.context.object.type == 'ARMATURE'

arma = bpy.context.object
bones = arma.data.bones

def isSkin(name):
    return name in (mesh.name for mesh in arma.children)

def getMatTexture(material):
    return [n for n in material.node_tree.nodes if n.type == 'TEX_IMAGE'][0]

def readString(file, address):
    file.seek(address)
    next_byte = file.read(1)
    s = ''
    while len(next_byte) > 0 and next_byte != 'x00':
        s += chr(next_byte[0])
        next_byte = file.read(1)
    return s

# still a little slow but acceptable; should pre-allocate
def imageToRGB5A3(image):
    w,h = image.size
    num_blocks_x = w // 4
    num_blocks_y = h // 4
    # converting to ints in advance significantly improves speed
    rgba = [int(f * 255) for f in image.pixels]
    data = bytes()
    for row in range(num_blocks_y):
        for col in range(num_blocks_x):
            for i in range(4):
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
    print(None in data)
    return bytes(data)

def writeTexture(file, address, texture):
    image = texture.image
    file.seek(address)
    file.write(struct.pack('>H', image.size[0])) # width
    file.write(struct.pack('>H', image.size[1])) # height
    file.seek(address + 0x5)
    file.write(b'\x01')
    file.seek(address + 0x8)
    file.write(b'\x00\x00\x00\x90') # encoding
    file.seek(address + 0x10)
    # extrapolation
    if texture.extension == 'EXTEND':
        file.write(b'\x00\x00\x00\x00') # x
        file.write(b'\x00\x00\x00\x00') # y
    elif texture.extension == 'REPEAT':
        file.write(b'\x00\x00\x00\x01') # x
        file.write(b'\x00\x00\x00\x01') # y
    else:
        raise Exception(f"Extrapolation type '{texture.extension}' unsupported")
    file.seek(address + 0x28)
    file.write(b'\x00\x00\x00\x80') # image offset
    t0 = time()
    #data = imageToRGBA32(image)
    data = imageToRGB5A3(image)
    print(time() - t0)
    file.seek(address + 0x4c)
    file.write(struct.pack('>I', len(data))) # compressed image size
    file.seek(address + 0x80)
    file.write(data) # compressed image data
    return file.tell() + 0x10 # next address (add some padding)

def writeMaterial(file, address, material):
    nameAddr = address + 0x8c
    file.seek(address)
    file.write(struct.pack('>I', nameAddr))
    
    # name
    file.seek(nameAddr)
    file.write(bytes(material.name, 'ascii'))
    sz = len(material.name)
    sz = (sz // 4) * 4 + 4
    nextAddr = nameAddr + sz
    
    texture = getMatTexture(material)
    texAddr = textures[texture.image.name]['address']
    file.seek(address + 0x18)
    file.write(struct.pack('>I', texAddr))
    file.seek(address + 0x2c)
    file.write(struct.pack('>I', nextAddr))
    file.seek(address + 0x5a)
    file.write(b'\x01\x01\x01\xff')
    file.seek(address + 0x60)
    file.write(b'\x80\x80\x80\xff')
    file.write(b'\xff\xff\xff\xff')
    file.seek(address + 0x70)
    file.write(b'\x00\x00\x00\xff')
    file.write(b'\xff')
    file.seek(address + 0x78)
    file.write(b'\x33\x33\x33\xff')
    file.seek(address + 0x80)
    file.write(b'\xff\xff\xff\xff')
    
    file.seek(nextAddr)
    file.write(b'\x01\x04\x00\x00')
    file.write(struct.pack('>f', 0.0))
    file.write(struct.pack('>f', 0.0))
    file.write(struct.pack('>f', 0.0))
    file.write(struct.pack('>f', 1.0))
    file.write(struct.pack('>f', 1.0))
    
    nextAddr = file.tell()
    file.seek(address + 0x40)
    file.write(struct.pack('>I', nextAddr))
    file.seek(nextAddr)
    file.write(b'\x00\x00\xff\xff\x00\x00\x00\x00')
    
    return file.tell()

def writeBone(file, address, bone):
    # if bone name is the same as a child mesh, mark it as a skin node
    if isSkin(bone.name):
        file.seek(address)
        file.write(b'\x00\x00\x00\x03')
        nameAddr = address + 0x3c
    else:
        nameAddr = address + 0x30
    
    file.seek(address + 0x4)
    file.write(struct.pack('>I', nameAddr))
    file.write(struct.pack('>H', bones.find(bone.name)))
    file.write(b'\x00\x18')
    
    file.seek(nameAddr)
    file.write(bytes(bone.name, 'ascii'))
    sz = len(bone.name)
    sz = (sz // 4) * 4 + 4
    nextAddr = nameAddr + sz
    
    if len(bone.children) > 0:
        file.seek(address + 0x24)
        file.write(struct.pack('>I', nextAddr))
        nextAddr = writeBone(file, nextAddr, bone.children[0])
    
    if bone.parent is not None:
        siblings = bone.parent.children
        idx = siblings.find(bone.name)
        # if has next sibling...
        if len(siblings) > idx + 1:
            file.seek(address + 0x28)
            file.write(struct.pack('>I', nextAddr))
            nextAddr = writeBone(file, nextAddr, siblings[idx + 1])
        
    return nextAddr

def writeMeshes(file, boneAddr, nextAddr):
    file.seek(boneAddr)
    # check if the bone is a skin node
    if int.from_bytes(file.read(4), 'big') == 0x3:
        # if so, get the bone name
        nameAddr = int.from_bytes(file.read(4), 'big')
        name = readString(file, nameAddr)
        # write the mesh address
        file.seek(boneAddr + 0x30)
        file.write(struct.pack('>I', nextAddr))
        # write the mesh data
        mesh = bpy.data.objects[name]
        nextAddr = writeMesh(file, nextAddr, mesh)
        
    file.seek(boneAddr + 0x24)
    childAddr = int.from_bytes(file.read(4), 'big')
    if childAddr != 0:
        nextAddr = writeMeshes(file, childAddr, nextAddr)
        
    file.seek(boneAddr + 0x28)
    sibAddr = int.from_bytes(file.read(4), 'big')
    if sibAddr != 0:
        nextAddr = writeMeshes(file, sibAddr, nextAddr)
        
    return nextAddr
    
def writeMesh(file, address, object):
    mesh = object.data
    file.seek(address)
    file.write(b'\x0a\x00')
    file.write(struct.pack('>H', len(mesh.vertices))) # num. verts
    file.seek(address + 0x6)
    file.write(b'\x00\x01') # num. uv layers
    vertsAddr = address + 0x30
    file.write(struct.pack('>I', vertsAddr))
    uvCoordsAddr = vertsAddr + len(mesh.vertices) * 0x18
    file.seek(address + 0x14)
    file.write(struct.pack('>I', uvCoordsAddr))
    facesAddr = uvCoordsAddr + len(mesh.loops) * 0x8 + 0x8
    file.seek(address + 0x18)
    file.write(struct.pack('>I', facesAddr))
    
    # write vertices & normals
    file.seek(vertsAddr)
    for v in mesh.vertices:
        # vertex
        for f in v.co:
            file.write(struct.pack('>f', f))
        # normal
        for f in v.normal:
            file.write(struct.pack('>f', f))
    
    # write uv coordinates
    file.seek(uvCoordsAddr)
    file.write(struct.pack('>I', uvCoordsAddr + 0x8)) # start of uv coords
    file.write(struct.pack('>H', len(mesh.loops)))
    file.seek(uvCoordsAddr + 0x8)
    uvMap = mesh.uv_layers.active.data
    for loop in mesh.loops:
        coords = uvMap[loop.index].uv
        file.write(struct.pack('>f', coords[0])) # x
        file.write(struct.pack('>f', coords[1])) # y
    
    # write face groups
    for i in range(len(object.material_slots)):
        file.seek(facesAddr)
        file.write(b'\x00\x00\x00\x01')
        
        faces = [face for face in mesh.polygons if face.material_index == i]
        
        # material address
        mat = object.material_slots[i].material
        file.seek(matListAddr + 4 * materials.index(mat))
        matAddr = file.read(4)
        file.seek(facesAddr + 0x8)
        file.write(matAddr)
        
        file.write(b'\x00\x01') # num. ops
        faceOpsAddr = facesAddr + 0x40
        faceOpsAddr = (faceOpsAddr // 0x20) * 0x20
        file.seek(facesAddr + 0x14)
        file.write(struct.pack('>I', faceOpsAddr))
        faceOpsSize = 0x3 + len(faces) * 3 * 6
        faceOpsSize = (faceOpsSize // 0x10) * 0x10 + 0x10
        file.seek(facesAddr + 0x18)
        file.write(struct.pack('>I', faceOpsSize))
        vertInfoAddr = faceOpsAddr + faceOpsSize
        file.seek(facesAddr + 0x10)
        file.write(struct.pack('>I', vertInfoAddr))
        
        # faces
        file.seek(faceOpsAddr)
        file.write(b'\x90') # GX_DRAW_TRIANGLES
        file.write(struct.pack('>H', len(faces) * 3)) # num. entries
        for face in faces:
            file.write(struct.pack('>H', face.vertices[1])) # vertex index
            file.write(struct.pack('>H', face.vertices[1])) # normal index
            file.write(struct.pack('>H', face.loop_indices[1])) # uv index
            file.write(struct.pack('>H', face.vertices[0]))
            file.write(struct.pack('>H', face.vertices[0]))
            file.write(struct.pack('>H', face.loop_indices[0]))
            file.write(struct.pack('>H', face.vertices[2]))
            file.write(struct.pack('>H', face.vertices[2]))
            file.write(struct.pack('>H', face.loop_indices[2]))

        # vertex info
        file.seek(vertInfoAddr)
        file.write(b'\x09\x01\x04\x00\x03\x18\x00\x00') # vertices
        file.write(b'\x0a\x00\x04\x00\x03\x18\x00\x00') # normals
        file.write(b'\x0d\x01\x04\x00\x03\x08\x00\x00') # uv coords
        file.write(b'\xff\x00\x00\x00\x00\x00\x00\x00')
        file.seek(vertInfoAddr + 0xb8)
        file.write(b'\x00\x00\x00\x00')
        
        nextAddr = file.tell() + 0x4
        if i < len(object.material_slots) - 1:
            file.seek(facesAddr + 0x1c)
            file.write(struct.pack('>I', nextAddr))
            facesAddr = nextAddr
    
    # ???
    unknownAddr = nextAddr
    file.seek(address + 0x1c)
    file.write(struct.pack('>I', unknownAddr))
    
    file.seek(unknownAddr + 0x18)
    file.write(b'\x00\x01')
    file.seek(unknownAddr + 0x1c)
    file.write(struct.pack('>I', unknownAddr + 0x24))
    file.seek(unknownAddr + 0x24)
    file.write(b'\x00\x01\x1e\x00')
    file.write(struct.pack('>I', unknownAddr + 0x30))
    file.seek(unknownAddr + 0x3c)
    file.write(struct.pack('>f', 1.0))
    file.write(struct.pack('>f', 32.0))
    file.write(struct.pack('>f', 1.0))
    
    return file.tell()

meshes = [child for child in arma.children if child.type == 'MESH']
materials = []
for mesh in meshes:
    materials += [slot.material for slot in mesh.material_slots]
textures = {}
for mat in materials:
    tex = getMatTexture(mat)
    if tex.image.name not in textures:
        textures[tex.image.name] = tex

fout = open('C:\\Users\\seanm\\Projects\\PBR\\Blender\\pikipek.sdr', 'wb+')
fout.write(b'\x01\x00\x00\x04\x00\x00\x00\x00')

# textures
texListAddr = 0x30

fout.seek(0xc)
fout.write(struct.pack('>I', texListAddr))
fout.seek(0x1a)
fout.write(struct.pack('>H', len(textures))) # texture count

nextAddr = texListAddr + 4 * len(textures)
nextAddr = (nextAddr // 0x10) * 0x10 + 0x10
i = 0
for tex in textures.values():
    textures[tex.image.name]['address'] = nextAddr
    fout.seek(texListAddr + 4 * i)
    fout.write(struct.pack('>I', nextAddr))
    fout.seek(nextAddr)
    nextAddr = writeTexture(fout, nextAddr, tex)
    i += 1

# materials
matListAddr = nextAddr

fout.seek(0x14)
fout.write(struct.pack('>I', matListAddr))
fout.seek(0x1e)
fout.write(struct.pack('>H', len(materials))) # material count

nextAddr = matListAddr + 4 * len(materials)
nextAddr = (nextAddr // 0x10) * 0x10 + 0x10
for i in range(len(materials)):
    fout.seek(matListAddr + 4 * i)
    fout.write(struct.pack('>I', nextAddr))
    fout.seek(nextAddr)
    nextAddr = writeMaterial(fout, nextAddr, materials[i])

# skeleton
skeleListAddr = nextAddr
skeleAddr = skeleListAddr + 0x10
skeleNameAddr = skeleAddr + 0x1c

fout.seek(0x8)
fout.write(struct.pack('>I', skeleListAddr)) # skeleton list pointer
fout.seek(0x18)
fout.write(b'\x00\x01') # skeleton count

fout.seek(skeleListAddr)
fout.write(struct.pack('>I', skeleAddr)) # skeleton pointer

fout.seek(skeleAddr)
fout.write(struct.pack('>I', skeleNameAddr)) # name pointer

fout.seek(skeleAddr + 0x6)
fout.write(struct.pack('>H', len(bones))) # bone count

fout.seek(skeleNameAddr)
fout.write(bytes(bones[0].name, 'ascii')) # skeleton name (just uses root bone name)

sz = len(bones[0].name)
sz = (sz // 4) * 4 + 4
rootAddr = skeleNameAddr + sz
fout.seek(skeleAddr + 0x10)
fout.write(struct.pack('>I', rootAddr)) # root bone pointer

nextAddr = writeBone(fout, rootAddr, bones[0]) # write bone tree

# meshes
writeMeshes(fout, rootAddr, nextAddr)

fout.close()
