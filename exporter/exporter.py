import time
import bpy, math, struct
from ..shared.file_io import BinaryWriter

def approxEqual(f1, f2):
    return math.isclose(f1, f2, rel_tol=1e-05, abs_tol=0.001)

def isBoneAnimated(bone):
    return any(bone.name in actions[action_id]['bones']
               for action_id in actions)

def isMaterialAnimated(mat):
    return any(mat.name in actions[action_id]['materials']
               for action_id in actions)

def getVertexGroupBoneIndex(object, groupID):
    return [bone.name for bone in bones] \
           .index(object.vertex_groups[groupID].name)

def getMatTexture(material):
    textures = [n for n in material.node_tree.nodes if n.type == 'TEX_IMAGE']
    if len(textures) > 0:
        return textures[0]
    return None

def getMatMapNode(material):
    maps = [n for n in material.node_tree.nodes if n.type == 'MAPPING']
    if len(maps) > 0:
        return maps[0]
    return None

def imageToRGB5A3(image):
    w,h = image.size
    blocks_x = w // 4
    blocks_y = h // 4
    # converting to ints in advance significantly improves speed
    rgba = [int(f * 255) for f in image.pixels]
    data = [None] * (w * h * 2) # pre-allocate for speed
    idx = 0
    # add rows bottom-to-top to cooperate with Blender
    for row in range(blocks_y - 1, -1, -1):
        for col in range(blocks_x):
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
                    data[idx:idx+2] = val.to_bytes(2, 'big')
                    idx += 2
    return bytes(data)

def imageToRGBA32(image):
    w,h = image.size
    blocks_x = w // 4
    blocks_y = h // 4
    rgba = [int(f * 255) for f in image.pixels]
    data = [None] * (w * h * 4) # pre-allocate for speed
    for row in range(blocks_y):
        for col in range(blocks_x):
            offset = (row * w * 4 + col * 4) * 4
            # each block is 4x4 pixels
            for i in range(4):
                for j in range(4):
                    pos = (row * w * 4 + col * 4 + i * w + j) * 4
                    idx = (row * blocks_x + col) * 64 + (i * 4 + j) * 2
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
    # image data address needs to be a multiple of 0x20
    offset = 0x80 + address % 0x20
    file.write('uint', offset, address, offset=0x28)
    #data = imageToRGBA32(image) # currently doesn't load correctly in-game
    data = imageToRGB5A3(image)
    file.write('uint', len(data), address, offset=0x4c)
    file.write_chunk(data, address + offset)
    return file.tell() + 0x10 # next address (add some padding)

def writeMaterial(file, address, material):
    # name
    nameAddr = address + 0x8c
    file.write('uint', nameAddr, address)
    file.write('string', material.name, nameAddr)
    sz = len(material.name) + 1 # null terminate
    sz = (sz + 3) // 4 * 4
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

    # animation data
    nextAddr = file.tell() + 1
    if isMaterialAnimated(material):
        file.write('uint', nextAddr, address, offset=0x84)
        nextAddr = writeFCurves(file, nextAddr, material)

    return nextAddr

def writeAction(file, address, action_id):
    time = actions[action_id]['length'] / FRAME_RATE
    # determines portion of animation played during attacks
    if action_id == 'move_spec':
        # 1.5 is fairly arbitrary, length of Psychic's animation
        file.write('float', time - 1.5, address, offset=0x4)
    # determines position of mon when animation is played
    if action_id == 'move_phys':
        # 1.0 is entirely arbitrary
        file.write('float', 1.0, address, offset=0x8)
    file.write('float', time, address, offset=0xc)
    file.write('uchar', 1, address, offset=0x28) # loops?
    if not action_id.startswith('tx_'):
        file.write('uchar', 1, address, offset=0x29)
    file.write('uchar', 1, address, offset=0x2a)
    return address + 0x30

def writeBone(file, address, bone):
    print(bone.name)
    nextAddr = address + 0x30
    
    # root bone cannot be part of a vertex group
    if bone.parent is not None:
        transform = bone.parent.matrix_local.inverted() @ bone.matrix_local
        t,r,s = transform.decompose()
        # regular bones don't actually contain scale info in
        # Blender from what I can tell, so just going to use
        # the origin's posed scale for now
        if bone.name.lower() == 'origin':
            s = arma.pose.bones[bone.name].scale
        r = r.to_euler()
        # gonna mark every bone as a vertex group instead
        # of trying to track which ones actually are
        file.write('uint', 0x2, address)
        # inverse bind matrix
        file.seek(address + 0x44)
        for row in bone.matrix_local.inverted()[:3]:
            for f in row:
                file.write('float', f, 0, whence='current')
        nextAddr += 72
        if any(f != 0.0 for f in t):
            file.write('uint', nextAddr, address, offset=0xc)
            file.write('float', t[0], nextAddr)
            file.write('float', t[1], 0, whence='current')
            file.write('float', t[2], 0, whence='current')
            nextAddr += 12
        if any(f != 0.0 for f in r):
            file.write('uint', nextAddr, address, offset=0x10)
            file.write('float', r[0], nextAddr)
            file.write('float', r[1], 0, whence='current')
            file.write('float', r[2], 0, whence='current')
            nextAddr += 12
        if any(f != 1.0 for f in s):
            file.write('uint', nextAddr, address, offset=0x14)
            file.write('float', s[0], nextAddr)
            file.write('float', s[1], 0, whence='current')
            file.write('float', s[2], 0, whence='current')
            nextAddr += 12
        if bone.name == 'ct_all':
            # this affects camera positioning during run animation;
            # should not be hard-coded
            file.write('float', 8, address, offset=0x1c)

    nameAddr = nextAddr
    file.write('uint', nameAddr, address, offset=0x4)
    idx = bones.find(bone.name)
    file.write('ushort', idx, address, offset=0x8)
    file.write('ushort', 0x18, address, offset=0xa)
    file.write('string', bone.name, nameAddr)
    sz = len(bone.name) + 1 # null terminate
    sz = (sz + 3) // 4 * 4
    nextAddr = nameAddr + sz

    if isBoneAnimated(bone):
        file.write('uint', nextAddr, address, offset=0x20)
        nextAddr = writeFCurves(file, nextAddr, bone)

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

def writeFCurves(file, address, object):
    i = 0
    for action_id in actions:
        file.write('ushort', i, address, offset=0)
        # anim. length can't be 0 or it will freeze the game
        animLength = actions[action_id]['length'] / FRAME_RATE
        file.write('float', animLength, address, offset=0x8)

        numFCurves = 0
        if type(object) == bpy.types.Bone:
            if object.name in actions[action_id]['bones']:
                keyframes = actions[action_id]['bones'][object.name]
            else:
                keyframes = {
                    0: { 0: [(0, 0)], 1: [(0, 0)], 2: [(0, 0)] }, # t (x, y, z)
                    1: { 0: [(0, 0)], 1: [(0, 0)], 2: [(0, 0)] }, # r (x, y, z)
                    2: { 0: [(0, 1)], 1: [(0, 1)], 2: [(0, 1)] }, # s (x, y, z)
                }
        elif type(object) == bpy.types.Material:
            if object.name in actions[action_id]['materials']:
                keyframes = actions[action_id]['materials'][object.name]
            else:
                keyframes = {
                    0x14: { 0: [(0, 0)], 1: [(0, 0)] }, # t (x, y)
                    0x16: { 0: [(0, 1)], 1: [(0, 1)] }, # s (x, y)
                }
        for comp in keyframes:
            numFCurves += len(keyframes[comp])
        file.write('ushort', numFCurves, address, offset=0x2)
        fcurveListAddr = address + 0x10
        file.write('uint', fcurveListAddr, address, offset=0x4)

        nextAddr = fcurveListAddr + numFCurves * 0x10
        c = 0
        for m in keyframes: # component
            for n in keyframes[m]: # axis
                entryAddr = fcurveListAddr + c * 0x10
                file.write('uchar', m, entryAddr, offset=0x1)
                file.write('uchar', n+1, entryAddr, offset=0x2)
                file.write('uchar', 0x8, entryAddr, offset=0x6) # format code?
                # calc largest exponent that satisfies
                #   |x| * (2 ^ exp) < (2 ^ 15)
                # for all keyframe points (2 ^ 15 = max signed short)
                umax = max(abs(kf[1]) for kf in keyframes[m][n])
                if umax == 0.0:
                    exp = 0
                else:
                    exp = min(14, math.ceil(15 - math.log(umax, 2)) - 1)
                file.write('uchar', exp, entryAddr, offset=0x7)
                file.write('uint', nextAddr, entryAddr, offset=0x8)
                nextAddr = writeKeyframes(file, nextAddr,
                                          keyframes[m][n], 2 ** exp)
                c += 1
        # actions are stored in a linked list
        if i < len(actions) - 1:
            file.write('uint', nextAddr, address, offset=0xc)
        address = nextAddr
        i += 1
    return nextAddr

def writeKeyframes(file, address, keyframes, scale):
    maxTime = keyframes[-1][0] / FRAME_RATE
    numFrames = len(keyframes)
    pointsAddr = address + 0x20
    # each point uses 2 bytes so need to do some alignment
    framesAddr = pointsAddr + (numFrames * 2 + 3) // 4 * 4
    file.write('uint', pointsAddr, address, offset=0)
    file.write('ushort', numFrames, address, offset=0x8)
    file.write('float', maxTime, address, offset=0xc)
    file.write('uint', framesAddr, address, offset=0x10)
    file.write('ushort', numFrames, address, offset=0x14)
    file.write('float', -1234567.0, address, offset=0x18) # "-inf"
    file.seek(pointsAddr)
    for kf in keyframes:
        scaled = round(kf[1] * scale)
        file.write('short', scaled, 0, whence='current')

    # not currently supporting Bezier interpolation
##    file.seek(tangentsAddr)
##    for kf in fcurve.keyframe_points:
##        if kf.interpolation == 'BEZIER':
##            # convert Bezier to Hermite
##            h0 = 3 * kf.co.y - 3 * kf.handle_left.y
##            h1 = 3 * kf.handle_right.y - 3 * kf.co.y
##            file.write('float', h0, 0, whence='current')
##            file.write('float', h1, 0, whence='current')

    file.seek(framesAddr)
    for i in range(numFrames):
        kf = keyframes[i]
        # interpolation - using constant (0) for everything atm
        file.write('ushort', 0, 0, whence='current')
        file.write('ushort', i, 0, whence='current')
        timestamp = kf[0] / FRAME_RATE
        file.write('float', timestamp, 4, whence='current')
    return framesAddr + numFrames * 0xc

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

    # vertices & normals
    vertsAddr = address + 0x30
    file.write('uint', vertsAddr, address, offset=0x8)
    file.seek(vertsAddr)
    for v in mesh.vertices:
        # vertex
        for f in v.co:
            file.write('float', f, 0, whence='current')
        # normal
        for f in v.normal:
            file.write('float', f, 0, whence='current')
    nextAddr = file.tell()

    # weights
    vertGroups = []
    for v in mesh.vertices:
        groups = sorted(v.groups, key=lambda x : x.weight, reverse=True)
        if len(groups) > 4:
            operator.report({'WARNING'}, 'A vertex is part of more than 4 vertex groups;\n' + \
                            'lowest weighted group(s) will be culled')
        vertGroups.append(groups[:4])
    if any(len(groups) > 0 for groups in vertGroups):
        skinAddr = nextAddr
        file.write('uint', skinAddr, address, offset=0xc)
        file.write('ushort', len(mesh.vertices), skinAddr, offset=0x8)
        file.write('ushort', len(mesh.vertices), skinAddr, offset=0xa)
        groupsListAddr = skinAddr + 0x1c
        file.write('uint', groupsListAddr, skinAddr, offset=0xc)
        weightsListAddr = groupsListAddr + 6 * len(mesh.vertices)
        file.write('uint', weightsListAddr, skinAddr, offset=0x10)
        for i in range(len(vertGroups)):
            groups = vertGroups[i]
            file.write('ushort', 1, groupsListAddr, offset=(6 * i))
            b1 = getVertexGroupBoneIndex(object, groups[0].group)
            file.write('ushort', b1, 0, whence='current')
            if len(groups) > 1:
                b2 = getVertexGroupBoneIndex(object, groups[1].group)
                file.write('ushort', b2, 0, whence='current')
                w1 = groups[0].weight
                w2 = groups[1].weight
                # weights are out of 0xffff
                if w1 == w2:
                    # handles the case where both w1 and w2 are 0
                    weight = 0x8000
                else:
                    # normalize in case there are > 2 groups
                    weight = round(0xffff * (w1 / (w1 + w2)))
            else:
                file.write('ushort', 0, 0, whence='current')
                # only one group, give entire weight to it
                weight = 0xffff
            file.write('ushort', weight, weightsListAddr, offset=(2 * i))
        groupsListAddr = file.tell()
        file.write('uint', groupsListAddr, skinAddr, offset=0x18)
        n = 0
        file.seek(groupsListAddr)
        for i in range(len(vertGroups)):
            groups = vertGroups[i]
            if len(groups) > 2:
                file.write('ushort', i, 0, whence='current')
                b1 = getVertexGroupBoneIndex(object, groups[2].group)
                w1 = round(groups[2].weight * 0xffff)
                if len(groups) == 4:
                    b2 = getVertexGroupBoneIndex(object, groups[3].group)
                    w2 = round(groups[3].weight * 0xffff)
                else:
                    b2 = 0xffff
                    w2 = 0
                file.write('ushort', b1, 0, whence='current')
                file.write('ushort', b2, 0, whence='current')
                file.write('ushort', w1, 0, whence='current')
                file.write('ushort', w2, 0, whence='current')
                n += 1
        nextAddr = file.tell()
        file.write('ushort', n, skinAddr, offset=0x14)

    # uv coordinates
    uvCoordsAddr = nextAddr
    file.write('uint', uvCoordsAddr, address, offset=0x14)
    file.write('uint', uvCoordsAddr + 0x8, uvCoordsAddr) # start of uv coords
    file.write('ushort', len(mesh.loops), uvCoordsAddr, offset=0x4)
    uvMap = mesh.uv_layers.active.data
    file.seek(uvCoordsAddr + 0x8)
    for loop in mesh.loops:
        coords = uvMap[loop.index].uv
        file.write('float', coords[0], 0, whence='current') # x
        file.write('float', 1.0 - coords[1], 0, whence='current') # y

    # face groups
    facesAddr = file.tell()
    file.write('uint', facesAddr, address, offset=0x18)
    for i in range(len(object.material_slots)):
        file.write('uint', 0x1, facesAddr)
        faces = [face for face in mesh.polygons if face.material_index == i]
        mat = object.material_slots[i].material
        matListAddr = file.read('uint', 0, offset=0x14)
        matAddr = file.read('uint', matListAddr,
                            offset=(4 * materials.index(mat)))
        file.write('uint', matAddr, facesAddr, offset=0x8)

        file.write('ushort', 0x1, facesAddr, offset=0xc) # num. ops
        faceOpsAddr = facesAddr + 0x40
        # the start address needs to be a multiple of 0x20
        faceOpsAddr = (faceOpsAddr + 0x1f) // 0x20 * 0x20
        file.write('uint', faceOpsAddr, facesAddr, offset=0x14)
        faceOpsSize = 0x3 + len(faces) * 3 * 6
        # the region size also needs to be a multiple of 0x20
        faceOpsSize = (faceOpsSize + 0x1f) // 0x20 * 0x20
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

    # bounding boxes
    unknownAddr = nextAddr
    file.write('uint', unknownAddr, address, offset=0x1c)
    file.write('ushort', 0x1, unknownAddr, offset=0x18) # count
    file.write('uint', unknownAddr + 0x24, unknownAddr, offset=0x1c)

    file.write('ushort', 0x1, unknownAddr, offset=0x24) # count
    file.write('uchar', 0x1e, 0, whence='current')
    file.write('uchar', 0x0, 0, whence='current') # could be 0x8
    file.write('uint', unknownAddr + 0x30, 0, whence='current')

    # currently just writing a single bounding box for
    # proper scaling in the Pokemon summary menu
    file.write('float', 0.0, unknownAddr, offset=0x30)
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 0.0, 0, whence='current')
    file.write('float', 1.0, 0, whence='current')
    # this should probably not be hard-coded but I'm not sure
    # how to determine the correct value dynamically yet
    file.write('float', 8.0, 0, whence='current')
    file.write('float', 1.0, 0, whence='current')

    return file.tell()

def writeSDR(op, cx):
    t0 = time.time()
    print('Start')
    assert cx.object.type == 'ARMATURE'

    global operator
    global context
    global FRAME_RATE

    global arma
    global bones
    global actions
    global materials
    global textures
    global keyframes

    operator = op
    path = op.filepath
    
    context = cx
    FRAME_RATE = cx.scene.render.fps

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

    # build keyframe dictionary
    actions = {}
    # material animations MUST start with "tx_"
    action_ids = ['idle', 'run', 'damage', 'faint', 'move_phys', 'move_spec',
                  'tx_wink', 'tx_sleep', 'tx_wakeup']
    for action_id in action_ids:
        actions[action_id] = { 'length': 0, 'bones': {}, 'materials': {} }
        action = getattr(arma.data, f'prop_{action_id}')
        if action:
            arma.animation_data.action = action
            actions[action_id]['length'] = action.frame_range.y
            for frame in range(int(action.frame_range[1] + 1)):
                context.scene.frame_set(frame)
                # root bone cannot be animated
                for bone in arma.pose.bones[1:]:
                    if bone.name not in actions[action_id]['bones']:
                        actions[action_id]['bones'][bone.name] = {
                            0: { 0: [], 1: [], 2: [] }, # t (x, y, z)
                            1: { 0: [], 1: [], 2: [] }, # r (x, y, z)
                            2: { 0: [], 1: [], 2: [] }, # s (x, y, z)
                        }
                    keyframes = actions[action_id]['bones'][bone.name]
                    transform = bone.parent.matrix.inverted() \
                                @ bone.matrix
                    comps = list(transform.decompose())
                    comps[1] = comps[1].to_euler()
                    for m in range(3):
                        for n in range(3):
                            if len(keyframes[m][n]) == 0 or \
                               not approxEqual(keyframes[m][n][-1][1],
                                               comps[m][n]):
                                keyframes[m][n].append((frame, comps[m][n]))
        # loop over materials
        for mat in materials:
            action = getattr(mat, f'prop_{action_id}')
            if action:
                actions[action_id]['length'] = max(action.frame_range.y,
                                                   actions[action_id]['length'])
                if not mat.node_tree.animation_data:
                    mat.node_tree.animation_data_create()
                mat.node_tree.animation_data.action = action
                if mat.name not in actions[action_id]['materials']:
                    actions[action_id]['materials'][mat.name] = {
                        0x14: { 0: [], 1: [] }, # t (x, y)
                        0x16: { 0: [], 1: [] }, # s (x, y)
                    }
                keyframes = actions[action_id]['materials'][mat.name]
                mapNode = getMatMapNode(mat)
                for frame in range(int(action.frame_range[1] + 1)):
                    context.scene.frame_set(frame)
                    for n in range(2): # x, y
                        t = mapNode.inputs[1].default_value[n]
                        # Blender goes bottom-to-top, game goes top-to-bottom
                        if n == 1:
                            t = 1.0 - t
                        if len(keyframes[0x14][n]) == 0 or \
                           not approxEqual(keyframes[0x14][n][-1][1], t):
                            keyframes[0x14][n].append((frame, t))
                        s = mapNode.inputs[3].default_value[n]
                        if len(keyframes[0x16][n]) == 0 or \
                           not approxEqual(keyframes[0x16][n][-1][1], s):
                            keyframes[0x16][n].append((frame, s))
        # filtering breaks the animation, not sure why yet
##            # filter out constant f-curves
##            for bone in arma.data.bones[1:]:
##                keyframes = actions[i]['bones'][bone.name]
##                for m in range(3):
##                    keyframes[m] = { k:v for k,v in keyframes[m].items()
##                                     if len(v) > 1 }
##                keyframes = { k:v for k,v in keyframes.items()
##                              if len(v) > 0 }
##                actions[i]['bones'][bone.name] = keyframes

    print('Initialization:', time.time() - t0)
    t0 = time.time()

    fout = BinaryWriter(path)
    fout.write('uchar', 0x1, 0)
    fout.write('ushort', 0x4, 0x2)

    # textures
    texListAddr = 0x30
    fout.write('uint', texListAddr, 0xc)
    fout.write('ushort', len(textures), 0x1a)
    nextAddr = texListAddr + 4 * len(textures)
    nextAddr = (nextAddr + 0xf) // 0x10 * 0x10
    i = 0
    for tex in textures.values():
        textures[tex.image.name]['address'] = nextAddr
        fout.write('uint', nextAddr, texListAddr, offset=(4 * i))
        nextAddr = writeTexture(fout, nextAddr, tex)
        i += 1
    print('Textures:', time.time() - t0)
    t0 = time.time()

    # materials
    matListAddr = nextAddr
    fout.write('uint', matListAddr, 0x14)
    fout.write('ushort', len(materials), 0x1e)
    nextAddr = matListAddr + 4 * len(materials)
    nextAddr = (nextAddr + 0xf) // 0x10 * 0x10
    for i in range(len(materials)):
        fout.write('uint', nextAddr, matListAddr, offset=(4 * i))
        nextAddr = writeMaterial(fout, nextAddr, materials[i])
    print('Materials:', time.time() - t0)
    t0 = time.time()

    # actions
    actionListAddr = nextAddr
    for action_id in actions:
        nextAddr = writeAction(fout, nextAddr, action_id)
    i = 0
    for action_id in actions:
        actionAddr = actionListAddr + i * 0x30
        fout.write('uint', nextAddr, actionAddr)
        fout.write('string', action_id, nextAddr)
        sz = len(action_id) + 1 # null terminate
        sz = (sz + 3) // 4 * 4
        nextAddr += sz
        i += 1
    print('Actions:', time.time() - t0)
    t0 = time.time()

    # skeleton
    skeleListAddr = nextAddr
    skeleAddr = skeleListAddr + 0x10
    skeleNameAddr = skeleAddr + 0x1c
    fout.write('uint', skeleListAddr, 0x8)
    fout.write('ushort', 0x1, 0x18) # skeleton count
    fout.write('uint', skeleAddr, skeleListAddr)
    fout.write('uint', skeleNameAddr, skeleAddr, offset=0)
    # an extra bone will get added for each mesh
    fout.write('ushort', len(bones) + len(meshes), skeleAddr, offset=0x6)
    fout.write('ushort', len(actions), skeleAddr, offset=0x8)
    fout.write('uint', actionListAddr, skeleAddr, offset=0xc)
    fout.write('string', arma.name, skeleNameAddr)
    sz = len(arma.name) + 1
    sz = (sz + 3) // 4 * 4
    rootAddr = skeleNameAddr + sz
    fout.write('uint', rootAddr, skeleAddr, offset=0x10) # root bone pointer
    nextAddr = writeBone(fout, rootAddr, bones[0]) # write bone tree
    print('Skeleton:', time.time() - t0)
    t0 = time.time()

    # meshes
    address = fout.read('uint', rootAddr, offset=0x24)
    while True:
        nextSibling = fout.read('uint', address, offset=0x28)
        if nextSibling == 0:
            break
        address = nextSibling
    fout.write('uint', nextAddr, address, offset=0x28)
    address = nextAddr
    # add skin nodes
    for i in range(len(meshes)):
        fout.write('uint', 0x3, address, offset=0)
        nameAddr = address + 0x3c
        fout.write('uint', nameAddr, address, offset=0x4)
        idx = len(bones) + i
        fout.write('ushort', idx, address, offset=0x8)
        fout.write('ushort', 0x18, address, offset=0xa)
        fout.write('string', meshes[i].name, nameAddr)
        sz = len(meshes[i].name) + 1 # null terminate
        sz = (sz + 3) // 4 * 4
        nextAddr = nameAddr + sz
        if i < len(meshes) - 1:
            fout.write('uint', nextAddr, address, offset=0x28)
        address = nextAddr
    writeMeshes(fout, rootAddr, nextAddr)
    print('Meshes:', time.time() - t0)

    fout.close()
    print(f'\n"{arma.name}" exported successfully.')
