"""Renderers: vector PDF (exact paper size), SVG preview, PNG preview (rasterised from the PDF), layered DXF."""
from __future__ import annotations

import base64
import io
from xml.sax.saxutils import escape

from .prim import DASH, EM, LAYERS, ViewResult
from .sheets import SheetResult

MM = 72.0 / 25.4
FILLS = {"wall": (0.10, 0.10, 0.10), "light": (0.90, 0.90, 0.90), "mid": (0.55, 0.55, 0.55), "glass": (0.88, 0.94, 1.0)}
_FONTS_READY = False


def _fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    base = "/usr/share/fonts/truetype/dejavu/"
    pdfmetrics.registerFont(TTFont("DV", base + "DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DV-B", base + "DejaVuSans-Bold.ttf"))
    _FONTS_READY = True


def _rgb(layer):
    return LAYERS.get(layer, (7, (0, 0, 0), 0.2, ""))[1]


def _lw(p):
    return p.w if getattr(p, "w", None) else LAYERS.get(p.layer, (7, (0, 0, 0), 0.2, ""))[2]


def render_pdf(sheets: list[SheetResult], title="Drawing set", subject="") -> bytes:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    _fonts()
    buf = io.BytesIO()
    first = sheets[0].size
    c = canvas.Canvas(buf, pagesize=(first[0] * MM, first[1] * MM), pageCompression=1)
    c.setTitle(title); c.setAuthor("AI Architect Studio (AI-assisted concept draft)"); c.setSubject(subject or "Architectural drawings")
    try:
        c.setViewerPreference("PrintScaling", "None")
    except Exception:
        pass
    for sh in sheets:
        W, H = sh.size
        c.setPageSize((W * MM, H * MM))
        for p in sh.prims:
            _pdf_prim(c, p)
        if sh.logo:
            try:
                lg = sh.logo
                c.drawImage(ImageReader(io.BytesIO(lg["data"])), lg["x"] * MM, lg["y"] * MM, lg["w"] * MM, lg["h"] * MM, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.showPage()
    c.save()
    return buf.getvalue()


def _pdf_prim(c, p):
    col = _rgb(p.layer)
    if p.kind == "text":
        size = p.h * EM * MM
        c.saveState()
        c.setFillColorRGB(*col)
        c.setFont("DV-B" if p.bold else "DV", size)
        cap = 0.73 * size
        dy = {"b": 0.0, "m": -cap / 2, "t": -cap}[p.valign]
        c.translate(p.x * MM, p.y * MM)
        if p.rot:
            c.rotate(p.rot)
        fn = {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[p.anchor]
        fn(0, dy, p.s)
        c.restoreState()
        return
    c.saveState()
    c.setStrokeColorRGB(*col)
    c.setLineWidth(_lw(p) * MM)
    c.setLineCap(0); c.setLineJoin(0)
    lt = getattr(p, "lt", "cont")
    if lt != "cont":
        c.setDash([d * MM for d in DASH[lt]])
    if p.kind == "line":
        c.line(p.x1 * MM, p.y1 * MM, p.x2 * MM, p.y2 * MM)
    elif p.kind == "poly":
        path = c.beginPath()
        pts = p.pts
        path.moveTo(pts[0][0] * MM, pts[0][1] * MM)
        for x, y in pts[1:]:
            path.lineTo(x * MM, y * MM)
        if p.closed:
            path.close()
        fill = p.fill
        if fill:
            c.setFillColorRGB(*FILLS.get(fill, (0.8, 0.8, 0.8)))
            if fill == "wall":
                c.setStrokeColorRGB(*FILLS["wall"])
        c.drawPath(path, stroke=1, fill=1 if fill else 0)
    elif p.kind == "arc":
        c.arc((p.cx - p.r) * MM, (p.cy - p.r) * MM, (p.cx + p.r) * MM, (p.cy + p.r) * MM, p.a0, p.a1 - p.a0)
    elif p.kind == "circle":
        if p.fill:
            c.setFillColorRGB(*FILLS.get(p.fill, (0.8, 0.8, 0.8)))
        c.circle(p.cx * MM, p.cy * MM, p.r * MM, stroke=1, fill=1 if p.fill else 0)
    c.restoreState()


def render_png(pdf_bytes: bytes, page=0, dpi=110) -> bytes:
    import pymupdf
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[page].get_pixmap(dpi=dpi, alpha=False)
    return pix.tobytes("png")


def render_svg(sh: SheetResult) -> str:
    W, H = sh.size
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Arial, sans-serif">',
           f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
    f = lambda v: f"{v:.3f}".rstrip("0").rstrip(".")
    Y = lambda y: H - y
    def color(layer, fill=None):
        r, g, b = _rgb(layer)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    def fillc(n):
        r, g, b = FILLS.get(n, (0.8, 0.8, 0.8)); return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    for p in sh.prims:
        if p.kind == "text":
            size = p.h * EM
            cap = 0.73 * size
            dy = {"b": 0.0, "m": cap / 2, "t": cap}[p.valign]
            anchor = {"l": "start", "c": "middle", "r": "end"}[p.anchor]
            tr = f' transform="rotate({f(-p.rot)} {f(p.x)} {f(Y(p.y))})"' if p.rot else ""
            out.append(f'<text x="{f(p.x)}" y="{f(Y(p.y) + dy)}" font-size="{f(size)}" text-anchor="{anchor}" fill="{color(p.layer)}"{" font-weight=\"bold\"" if p.bold else ""}{tr}>{escape(p.s)}</text>')
            continue
        stroke = color(p.layer)
        sw = _lw(p)
        dash = DASH.get(getattr(p, "lt", "cont"), [])
        da = f' stroke-dasharray="{" ".join(f(d) for d in dash)}"' if dash else ""
        base = f'stroke="{stroke}" stroke-width="{f(sw)}" stroke-linecap="butt" stroke-linejoin="miter"{da}'
        if p.kind == "line":
            out.append(f'<line x1="{f(p.x1)}" y1="{f(Y(p.y1))}" x2="{f(p.x2)}" y2="{f(Y(p.y2))}" {base}/>')
        elif p.kind == "poly":
            pts = " ".join(f"{f(x)},{f(Y(y))}" for x, y in p.pts)
            fl = fillc(p.fill) if p.fill else "none"
            st = fillc("wall") if p.fill == "wall" else stroke
            tag = "polygon" if p.closed else "polyline"
            out.append(f'<{tag} points="{pts}" fill="{fl}" {base.replace(stroke, st, 1)}/>')
        elif p.kind == "circle":
            fl = fillc(p.fill) if p.fill else "none"
            out.append(f'<circle cx="{f(p.cx)}" cy="{f(Y(p.cy))}" r="{f(p.r)}" fill="{fl}" {base}/>')
        elif p.kind == "arc":
            import math
            a0, a1 = math.radians(p.a0), math.radians(p.a1)
            x0, y0 = p.cx + p.r * math.cos(a0), p.cy + p.r * math.sin(a0)
            x1, y1 = p.cx + p.r * math.cos(a1), p.cy + p.r * math.sin(a1)
            large = 1 if (p.a1 - p.a0) % 360 > 180 else 0
            out.append(f'<path d="M {f(x0)} {f(Y(y0))} A {f(p.r)} {f(p.r)} 0 {large} 0 {f(x1)} {f(Y(y1))}" fill="none" {base}/>')
    if sh.logo:
        lg = sh.logo
        b64 = base64.b64encode(lg["data"]).decode()
        out.append(f'<image x="{f(lg["x"])}" y="{f(Y(lg["y"] + lg["h"]))}" width="{f(lg["w"])}" height="{f(lg["h"])}" preserveAspectRatio="xMidYMid meet" xlink:href="data:{lg["mime"]};base64,{b64}"/>')
    out.append("</svg>")
    return "".join(out)


_LW_VALID = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]


def render_dxf(views: list[ViewResult], title="Drawing", gap=6000.0) -> bytes:
    """One layered DXF in model space at 1:1 (units = mm). Views are laid out left-to-right; the first
    keeps the project's model coordinates. Text heights are paper height x scale so they print correctly."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment as A
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$MEASUREMENT"] = 1
    for name, (aci, rgb, lw, desc) in LAYERS.items():
        if name in ("A-SHEET",):
            continue
        lay = doc.layers.add(name, color=aci)
        lay.dxf.lineweight = min(_LW_VALID, key=lambda v: abs(v - lw * 100))
        lay.description = desc
    msp = doc.modelspace()
    lt = {"cont": "Continuous", "dash": "DASHED", "center": "CENTER", "hidden": "HIDDEN"}
    xcur = None
    for v in views:
        S = v.scale or 1
        bx0, by0, bx1, by1 = v.bbox
        dx = 0.0
        if xcur is None:
            xcur = bx1
        else:
            dx = xcur + gap - bx0
            xcur = bx1 + dx
        if v.scale == 0:
            S = 1
        ls = max(1.0, S * 0.25)
        def at(x, y): return (x + dx, y)
        for p in v.prims:
            attr = {"layer": p.layer if p.layer in LAYERS else "0"}
            if getattr(p, "lt", "cont") != "cont":
                attr["linetype"] = lt[p.lt]; attr["ltscale"] = ls
            if p.kind == "line":
                msp.add_line(at(p.x1, p.y1), at(p.x2, p.y2), dxfattribs=attr)
            elif p.kind == "poly":
                pts = [at(x, y) for x, y in p.pts]
                msp.add_lwpolyline(pts, close=p.closed, dxfattribs=attr)
                if p.fill in ("wall", "mid", "light") and p.closed:
                    h = msp.add_hatch(color={"wall": 250, "mid": 9, "light": 254}[p.fill], dxfattribs={"layer": attr["layer"]})
                    h.paths.add_polyline_path(pts, is_closed=True)
            elif p.kind == "arc":
                msp.add_arc((p.cx + dx, p.cy), p.r, p.a0, p.a1, dxfattribs=attr)
            elif p.kind == "circle":
                msp.add_circle((p.cx + dx, p.cy), p.r, dxfattribs=attr)
            elif p.kind == "text":
                if not p.s.strip():
                    continue
                t = msp.add_text(p.s, height=p.h * S, dxfattribs={"layer": attr["layer"], "rotation": p.rot})
                al = {("l", "b"): A.BOTTOM_LEFT, ("c", "b"): A.BOTTOM_CENTER, ("r", "b"): A.BOTTOM_RIGHT,
                      ("l", "m"): A.MIDDLE_LEFT, ("c", "m"): A.MIDDLE_CENTER, ("r", "m"): A.MIDDLE_RIGHT,
                      ("l", "t"): A.TOP_LEFT, ("c", "t"): A.TOP_CENTER, ("r", "t"): A.TOP_RIGHT}[(p.anchor, p.valign)]
                t.set_placement((p.x + dx, p.y), align=al)
        t = msp.add_text(v.title + (f"  (1:{v.scale})" if v.scale else "  (not to scale; units = paper mm)"), height=3.2 * S, dxfattribs={"layer": "A-ANNO-TEXT"})
        t.set_placement((bx0 + dx, by1 + 3.0 * S), align=A.BOTTOM_LEFT)
    msp.add_text("CONCEPT DRAFT - NOT REVIEWED. Units: millimetres, model space 1:1.", height=100, dxfattribs={"layer": "A-ANNO-TEXT"}).set_placement((0, -9000))
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
