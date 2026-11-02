#!/usr/bin/env python3
"""VS Code's status bar icons: Talpy's still poses (talpy_icons.mjs --status)
as an icon font, vscode/media/talpy-glyphs.woff (package.json
contributes.icons). A status bar shows only text and font icons; the poses
are drawn with masks and strokes, so each is rendered large, traced back to
plain outlines (potrace) and put in the font (FontForge's Python module).

    python3 tools/talpy_font.py [OUT.woff] [--preview PNG]

Needs node, rsvg-convert, ImageMagick (magick), potrace and python3-fontforge.
The font's metrics are the codicons' (VS Code's own icons: a 300 unit em, all
of it above the baseline), so Talpy sits where they do, about as big.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import fontforge
import psMat

ROOT = Path(__file__).resolve().parent.parent
POSES = ["working", "waiting", "idle", "none"]   # U+E000 on, in this order (package.json)
FIRST = 0xE000
EM = 300
# The pose's 24 unit box fills the em (12.5 a unit); scaled down to the
# codicons' size (their ink spans about 37 to 263) about the middle, the
# working pose's ink centred on it
SCALE = 1.0
CENTER_Y = 154.7


def traced(svg, work):
    png, pbm, out = work / (svg.stem + ".png"), work / (svg.stem + ".pbm"), work / (svg.stem + "-traced.svg")
    subprocess.run(["rsvg-convert", "-w", "1200", "-h", "1200", "-b", "white", str(svg), "-o", str(png)], check=True)
    subprocess.run(["magick", str(png), "-colorspace", "gray", "-threshold", "50%", str(pbm)], check=True)
    subprocess.run(["potrace", "-s", "-o", str(out), str(pbm)], check=True)
    return out


def build(out):
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        subprocess.run(["node", str(ROOT / "tools/talpy_icons.mjs"), "--status", str(work)], check=True)
        font = fontforge.font()
        font.fontname = font.familyname = font.fullname = "talpy-den-glyphs"
        font.em = EM
        font.ascent, font.descent = EM, 0
        font.hhea_ascent, font.hhea_descent = EM, 0
        font.os2_typoascent, font.os2_typodescent = EM, 0
        font.os2_winascent, font.os2_windescent = EM, 0
        font.hhea_ascent_add = font.os2_typoascent_add = font.os2_winascent_add = False
        font.hhea_descent_add = font.os2_typodescent_add = font.os2_windescent_add = False
        move = psMat.compose(psMat.translate(-EM / 2, -CENTER_Y),
                             psMat.compose(psMat.scale(SCALE), psMat.translate(EM / 2, EM / 2)))
        for i, pose in enumerate(POSES):
            glyph = font.createChar(FIRST + i, "talpy-" + pose)
            glyph.importOutlines(str(traced(work / (pose + ".svg"), work)))
            glyph.transform(move)
            glyph.removeOverlap()
            glyph.correctDirection()
            glyph.round()
            glyph.width = EM
        font.generate(str(out))
    return out


def preview(woff, png):
    """The poses at 16 px beside VS Code's own icons, as the status bar shows them, and at 64 px."""
    codicon = next(Path("/usr/share/code").rglob("codicon.ttf"), None)
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        for size in (16, 64):
            text = "  ".join(chr(FIRST + i) + " 2" for i in range(len(POSES)))
            part = Path(tmp) / f"{size}.png"
            subprocess.run(["magick", "-background", "#181818", "-fill", "#cccccc", "-font", str(woff), "-pointsize", str(size),
                            "label:" + text, str(part)], check=True)
            lines.append(str(part))
        if codicon:
            ref = Path(tmp) / "ref.png"
            subprocess.run(["magick", "-background", "#181818", "-fill", "#cccccc", "-font", str(codicon), "-pointsize", "16",
                            "label:" + "\ueb19 2   \ueb9a 1   \uec10", str(ref)], check=True)
            lines.append(str(ref))
        subprocess.run(["magick", *lines, "-background", "#181818", "-gravity", "west", "-append", str(png)], check=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    png = None
    if "--preview" in args:
        png = args[args.index("--preview") + 1]
        del args[args.index("--preview"):args.index("--preview") + 2]
    woff = Path(args[0]) if args else ROOT / "vscode/media/talpy-glyphs.woff"
    build(woff)
    print(json.dumps({"font": str(woff), "glyphs": {p: hex(FIRST + i) for i, p in enumerate(POSES)}}))
    if png:
        preview(woff, png)
