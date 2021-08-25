import math

def extractBits(byte, pos, sz):
    return (byte >> (8 - pos - sz)) & (2 ** sz - 1)
    
def bytesToRGB565(b1, b2):
    r = (b1 & 0xf8)
    g = ((b1 & 0x7) << 5) + ((b2 & 0xe0) >> 3)
    b = (b2 & 0x1f) << 3
    a = 0xff
    return [r, g, b, a]

def bytesToRGB5A3(b1, b2):
    if b1 & 0x80 == 0:
        r = (b1 & 0xf) * 0x11
        g = ((b2 & 0xf0) >> 4) * 0x11
        b = (b2 & 0xf) * 0x11
        a = (b1 & 0x70) << 1
    else:
        r = (b1 & 0x7c) << 1
        g = ((b1 & 0x3) << 6) + ((b2 & 0xe0) >> 2)
        b = (b2 & 0x1f) << 3
        a = 0xff
    return [r, g, b, a]

def interpolate(v1, v2, weight):
    return [int(a * (1 - weight) + b * weight) for a, b in zip(v1, v2)]
    
def parseImageData(byte_arr, img_width, img_height, encoding):
    if encoding == 'RGBA32':
        return parseRGBA32Data(byte_arr, img_width, img_height)
    elif encoding == 'CMPR':
        return parseCMPRData(byte_arr, img_width, img_height)
    
    if encoding == 'I4':
        img_width /= 2
        block_width = 4
        block_height = 8
        px_sz = 1
    elif encoding in ['IA4', 'I8']:
        block_width = 8
        block_height = 4
        px_sz = 1
    elif encoding in ['IA8', 'RGB565', 'RGB5A3']:
        block_width = block_height = 4
        px_sz = 2
    rgba = []
    num_blocks_x = math.ceil(img_width / block_width)
    num_blocks_y = math.ceil(img_height / block_height)
    # add rows bottom-to-top b/c Blender uses bottom-left
    # instead of top-left as origin
    for row in range(num_blocks_y - 1, -1, -1):
        for n in range(block_height - 1, -1, -1):
            for col in range(num_blocks_x):
                loc = (row * block_width * block_height * num_blocks_x \
                       + col * block_width * block_height \
                       + n * block_width) * px_sz
                for px in range(block_width):
                    offset = loc + px_sz * px
                    b = byte_arr[offset:offset + px_sz]
                    if encoding == 'I4':
                        b1 = (b[0] & 0xf0) >> 4
                        b2 = (b[0] & 0xf)
                        rgba += [b1 * 0x11] * 3 + [0xff]
                        rgba += [b2 * 0x11] * 3 + [0xff]
                    elif encoding == 'IA4':
                        b1 = (b[0] & 0xf0) >> 4
                        b2 = (b[0] & 0xf)
                        rgba += [b2 * 0x11] * 3 + [b1]
                    elif encoding == 'I8':
                        rgba += [b[0]]*3 + [0xff]
                    elif encoding == 'IA8':
                        rgba += [b[1]]*3 + [b[0]]
                    elif encoding == 'RGB565':
                        rgba += bytesToRGB565(*b)
                    elif encoding == 'RGB5A3':
                        rgba += bytesToRGB5A3(*b)
    return rgba

def parseRGBA32Data(byte_arr, img_width, img_height):
    block_width = block_height = 4
    px_sz = 4
    rgba = []
    num_blocks_x = math.ceil(img_width / block_width)
    num_blocks_y = math.ceil(img_height / block_height)
    for row in range(num_blocks_y - 1, -1, -1):
        for n in range(block_height - 1, -1, -1):
            for col in range(num_blocks_x):
                loc = (row * block_width * block_height * num_blocks_x \
                       + col * block_width * block_height \
                       + n * 2) * px_sz
                for px in range(block_width):
                    offset = loc + 2 * px
                    a = byte_arr[offset]
                    r = byte_arr[offset + 1]
                    g = byte_arr[offset + block_width * block_height * 2]
                    b = byte_arr[offset + block_width * block_height * 2 + 1]
                    rgba += [r, g, b, a]
    return rgba

def getCMPRColors(subblock):
    b1 = subblock[0]
    b2 = subblock[1]
    color1 = bytesToRGB565(b1, b2)
    b3 = subblock[2]
    b4 = subblock[3]
    color2 = bytesToRGB565(b3, b4)
    if (b1 << 8) + b2 > (b3 << 8) + b4:
        color3 = interpolate(color1, color2, 1/3)
        color4 = interpolate(color1, color2, 2/3)
    else:
        color3 = interpolate(color1, color2, 1/2)
        color4 = [0, 0, 0, 0]
    return [color1, color2, color3, color4]

def parseCMPRData(byte_arr, img_width, img_height):
    block_width = block_height = 2 # num. sub-blocks
    rgba = []
    # each sub-block is 4 pixels wide
    num_blocks_x = math.ceil(img_width / (block_width * 4))
    num_blocks_y = math.ceil(img_height / (block_height * 4))
    for r in range(num_blocks_y - 1, -1, -1):
        # each block is 8 pixels tall
        for i in range(7, -1, -1):
            for c in range(num_blocks_x):
                for j in range(block_width):
                    # every sub-block consists of 8 bytes
                    loc = (r * block_width * block_height * num_blocks_x \
                           + c * block_width * block_height \
                           + 2 * (i // 4) + j) * 8
                    colors = getCMPRColors(byte_arr[loc:loc + 4])
                    indices = byte_arr[loc + 4:loc + 8]
                    # each sub-block is 4 pixels wide
                    for px in range(4):
                        # handle partial blocks
                        if 8 * c + 4 * j + px < img_width:
                            index = extractBits(indices[i % 4], px * 2, 2)
                            rgba += colors[index]
    return rgba                  
    
def decompress(byte_arr, img_width, img_height, encoding):
    rgba = parseImageData(byte_arr, img_width, img_height, encoding)
    assert len(rgba) / 4 == img_width * img_height
    return rgba
