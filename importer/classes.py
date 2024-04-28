import io, struct
from mathutils import Matrix

class Image:
    def __init__(self, pixels, w, h):
        self.width = w
        self.height = h
        self.pixels = pixels

class Texture:
    def __init__(self, imgID, extType):
        self.imageIndex = imgID
        self.extensionType = extType

class Material:
    def __init__(self, name, texID):
        self.name = name
        self.textureIndex = texID

class Face:
    def __init__(self, v, n, t):
        self.vertexIndices = v
        self.vertNormalIndices = n
        self.texCoordIndices = t

    def getMatchingTexCoord(self, v):
        return self.texCoordIndices[self.vertexIndices.index(v)]

class Mesh:
    def __init__(self, v, n, t, w):
        self.vertices = v
        self.vertNormals = n
        self.texCoords = t
        self.weights = w
        
        self.parts = []
        
class MeshPart:
    def __init__(self, f, matID):
        self.vertStride = 0
        self.texStride = 0
        
        # filter out degenerate faces w/ repeated vertices
        self.faces = [face for face in f if len(set(face.vertexIndices)) == 3]
        self.materialIndex = matID

class Bone:
    def __init__(self, i, name, trans, mat, brot, rot, sca, pos, flags):
        self.index = i
        self.name = name

        self.inverseBindMatrix = mat
        
        self.initialRot = rot #TODO:
        self.initialScale = sca
        self.initialTrans = pos
        self.bindRotation = brot
        self.flags = flags
        
        self.localTransform = trans
        # self.globalTransform calculated by Skeleton

        self.childIndices = []
        self.parentIndex = None
        
        self.meshIndex = None

class Skeleton:
    def __init__(self, name, numBones, bones):
        self.name = name
        self.numBones = numBones
        self.bones = bones

        self.calcGlobalTransforms(0, Matrix.Identity(4))

    #def calcGlobalTransforms(self, idx, parentTransform):
    #    bone = self.bones[idx]
    #    bone.globalTransform = parentTransform @ bone.localTransform
    #    for childIndex in bone.childIndices:
    #        self.calcGlobalTransforms(childIndex, bone.globalTransform)

    def calcGlobalTransforms(self, idx, parentTransform):
        bone = self.bones[idx]
        bone.globalTransform = bone.localTransform
        if (bone.flags >> 3) & 1:
            bone.globalTransform = parentTransform @ bone.globalTransform

        for childIndex in bone.childIndices:
            self.calcGlobalTransforms(childIndex, bone.globalTransform)
