"""Build small red thermometer PNG/ICO assets with the Python standard library.

The geometry follows web/favicon.svg; no runtime imaging dependency is required.
"""
from pathlib import Path
import math
import struct
import zlib

WEB = Path(__file__).resolve().parents[1] / 'web'


def curve(points):
    out = []
    for i in range(33):
        t = i / 32
        out.append(tuple((1-t)**3*points[0][axis] + 3*(1-t)**2*t*points[1][axis]
                         + 3*(1-t)*t*t*points[2][axis] + t**3*points[3][axis]
                         for axis in (0, 1)))
    return out


def arc(cx, cy, radius, start, end):
    return [(cx+radius*math.cos(start+(end-start)*i/80),
             cy+radius*math.sin(start+(end-start)*i/80)) for i in range(81)]


paths = [arc(8, 11, 2.5, 0, math.tau),
         curve([(25, 14), (23, 10), (15, 10), (15, 18)])
         + curve([(15, 18), (15, 26), (23, 26), (25, 22)]),
         [(36, 39), (36, 12)] + arc(42, 12, 6, math.pi, math.tau)
         + [(48, 39)] + arc(42, 47, 10, -math.atan2(8, 6), math.pi+math.atan2(8, 6)),
         [(42, 21), (42, 48)], [(48, 14), (55, 14)],
         [(48, 23), (53, 23)], [(48, 32), (55, 32)]]
segments = [(a, b) for path in paths for a, b in zip(path, path[1:])]


def ink(x, y):
    if (x-42)**2+(y-48)**2 <= 4.5**2:
        return True
    for (ax, ay), (bx, by) in segments:
        dx, dy = bx-ax, by-ay
        length = dx*dx+dy*dy
        t = max(0, min(1, ((x-ax)*dx+(y-ay)*dy)/length)) if length else 0
        if (x-ax-t*dx)**2+(y-ay-t*dy)**2 <= 1.75**2:
            return True
    return False


def png(size):
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            count = sum(ink((x+(sx+.5)/4)*64/size, (y+(sy+.5)/4)*64/size)
                        for sy in range(4) for sx in range(4))
            raw.extend((229, 57, 53, round(count*255/16)))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    sizes = (16, 32, 48)
    images = [png(size) for size in sizes]
    offset = 6+16*len(sizes)
    entries = bytearray()
    for size, data in zip(sizes, images):
        entries.extend(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (WEB / 'favicon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + entries + b''.join(images))
    (WEB / 'favicon.png').write_bytes(images[1])


if __name__ == '__main__':
    main()
