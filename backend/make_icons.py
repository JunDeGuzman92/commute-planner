"""Generate PWA icons: 192, 512, and maskable 512. Simple bus glyph."""
import zlib, struct, sys

def png(width, height, pixels):
    """Minimal PNG encoder (RGB, no filter)."""
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
    raw = b""
    for y in range(height):
        row = pixels[y * width:(y + 1) * width]
        raw += b"\x00" + bytes(v for px in row for v in px)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))

BLUE = (37, 99, 235)      # #2563eb
WHITE = (255, 255, 255)
DARK = (30, 41, 59)

def draw(size, maskable=False):
    """Bus front: rounded body, windshield, headlights, wheels."""
    px = [BLUE] * (size * size)
    if maskable:
        # maskable needs the icon inside the central 80% safe zone
        margin = int(size * 0.14)
    else:
        margin = int(size * 0.08)

    def rect(x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                px[y * size + x] = color

    def circle(cx, cy, r, color):
        for y in range(size):
            for x in range(size):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    px[y * size + x] = color

    # Bus body (rounded rect approximated)
    bx0, by0 = margin + int(size*0.08), margin + int(size*0.10)
    bx1, by1 = size - margin - int(size*0.08), size - margin - int(size*0.18)
    rect(bx0, by0, bx1, by1, WHITE)

    # Windshield
    wx0, wy0 = bx0 + int(size*0.04), by0 + int(size*0.06)
    wx1, wy1 = bx1 - int(size*0.04), by0 + int(size*0.30)
    rect(wx0, wy0, wx1, wy1, DARK)

    # Headlights
    hr = int(size * 0.035)
    circle(bx0 + int(size*0.10), by1 - int(size*0.10), hr, DARK)
    circle(bx1 - int(size*0.10), by1 - int(size*0.10), hr, DARK)

    # Wheels
    wr = int(size * 0.055)
    circle(bx0 + int(size*0.16), by1, wr, DARK)
    circle(bx1 - int(size*0.16), by1, wr, DARK)

    # Destination sign bar
    rect(wx0 + int(size*0.06), by0 - int(size*0.02), wx1 - int(size*0.06), by0 + int(size*0.02), DARK)

    return png(size, size, px)

out = r"C:\Users\junbu\Documents\commute-planner\frontend\public"
for name, size, mask in [("icon-192.png", 192, False),
                          ("icon-512.png", 512, False),
                          ("icon-maskable-512.png", 512, True)]:
    data = draw(size, mask)
    with open(f"{out}\\{name}", "wb") as f:
        f.write(data)
    print(f"{name}: {len(data)} bytes")
