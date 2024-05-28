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
    def __init__(self, i, name, type, pivots, trans, mat, brot, rot, sca, pos, nodeFlags, boneFlags):
        self.index = i
        self.name = name
        self.type = type

        self.ScalePivot = pivots[0]
        self.ScalePivotTranslate = pivots[1]
        self.RotatePivot = pivots[2]
        self.RotationPivotTranslate = pivots[3]

        self.inverseBindMatrix = mat
        
        self.initialRot = rot
        self.initialScale = sca
        self.initialTrans = pos
        self.bindRotation = brot
        self.nodeFlags = nodeFlags
        self.boneFlags = boneFlags

        self.parentRelativeBind = None
        
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

    def calcGlobalTransforms(self, idx, parentTransform, invparentBind = Matrix.Identity(4)):
        bone = self.bones[idx]
        s = invparentBind.to_scale()
        #invparentBindWithoutScale = Matrix.Diagonal((1 / s[0], 1 / s[1], 1 / s[2], 1.0)) @ invparentBind
        bone.invparentBind = invparentBind
        bone.parentRelativeBind = invparentBind @ bone.inverseBindMatrix.inverted()
        bone.globalTransform = parentTransform @ bone.localTransform

        for childIndex in bone.childIndices:
            self.calcGlobalTransforms(childIndex, bone.globalTransform, bone.inverseBindMatrix)
