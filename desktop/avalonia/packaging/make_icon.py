#!/usr/bin/env python3
"""Generates the Neurogenesis application icon (PNG and ICO) for Windows and Linux packaging."""
import math
from PIL import Image, ImageDraw

def create_icon(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded rect
    margin = int(size * 0.05)
    radius = int(size * 0.2)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(18, 26, 46, 255),
        outline=(50, 75, 120, 255),
        width=int(size * 0.015)
    )

    # Deterministic pseudo-random points (seeded)
    state = 7
    def next_rand():
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        return (state & 0xFFFFFFFF) / 0xFFFFFFFF

    pts = []
    for k in range(36):
        layer = k % 3
        x = size * (0.2 + 0.6 * next_rand())
        y = size * (0.25 + 0.22 * layer + 0.1 * next_rand())
        pts.append((x, y, layer))

    # Synapses
    line_color = (255, 215, 150, 70)
    for a in pts:
        for b in pts:
            if b[2] == a[2] + 1:
                dist = math.hypot(a[0] - b[0], a[1] - b[1])
                if dist < size * 0.28:
                    draw.line([a[0], a[1], b[0], b[1]], fill=line_color, width=max(1, int(size * 0.008)))

    # Neurons
    layer_colors = [
        (85, 160, 250, 255),   # Blue
        (250, 140, 60, 255),   # Orange
        (90, 210, 120, 255),   # Green
    ]

    for k, (x, y, l) in enumerate(pts):
        r = size * (0.035 if k % 6 == 0 else 0.022)
        if k % 6 == 0:
            # Glow
            draw.ellipse([x - r * 1.8, y - r * 1.8, x + r * 1.8, y + r * 1.8], fill=(255, 245, 180, 60))
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 245, 190, 255))
        else:
            col = layer_colors[l]
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

    return img

if __name__ == "__main__":
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(out_dir, "neurogenesis.png")
    ico_path = os.path.join(out_dir, "neurogenesis.ico")

    img_large = create_icon(512)
    img_large.save(png_path, "PNG")
    print(f"Wrote {png_path}")

    # Generate ICO with standard multi-resolution icons
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_images = [img_large.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    ico_images[0].save(ico_path, format="ICO", sizes=sizes, append_images=ico_images[1:])
    print(f"Wrote {ico_path}")
