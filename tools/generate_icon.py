"""Reproduce the bundled application monogram using only the standard library."""
from pathlib import Path
import struct
import zlib


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))


def png(size):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            px, py = x / size, y / size
            letter = (0.25 <= px < 0.38 and 0.20 <= py < 0.80 or
                      0.25 <= px < 0.77 and 0.20 <= py < 0.33 or
                      0.25 <= px < 0.67 and 0.44 <= py < 0.57)
            pixels.extend((255, 255, 255, 255) if letter else (25, 71, 115, 255))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [png(size) for size in sizes]
    offset = 6 + 16 * len(images)
    entries = bytearray()
    for size, image in zip(sizes, images):
        entries.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(image), offset))
        offset += len(image)
    target = Path(__file__).resolve().parents[1] / "assets" / "FMEDA.ico"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + b"".join(images))
