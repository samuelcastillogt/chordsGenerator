from fastapi import FastAPI, Query, Body, Response
from typing import List, Optional
import hashlib

app = FastAPI(title="Chord Renderer", version="1.0")
CHORD_SHAPES_GUITAR = {
    "Cmaj": {"pos": [-1, 3, 2, 0, 1, 0], "fretStart": 1},
    "Gmaj": {"pos": [3, 2, 0, 0, 0, 3], "fretStart": 1},
    "Dmaj": {"pos": [-1, -1, 0, 2, 3, 2], "fretStart": 1},
    "Amin": {"pos": [-1, 0, 2, 2, 1, 0], "fretStart": 1},
    "Emin": {"pos": [0, 2, 2, 0, 0, 0], "fretStart": 1}
}
def _parse_pos_csv(pos: str) -> List[int]:
    return [int(x.strip()) for x in pos.split(",")]

def render_guitar_svg(
    name: str,
    positions: List[int],
    fret_start: int = 1,
    frets_visible: int = 5,
    barres: Optional[List[dict]] = None,
) -> str:
    """
    positions: 6 ints, low->high (E A D G B e)
      -1 mute, 0 open, >=1 fret
    """
    if len(positions) != 6:
        raise ValueError("positions must have 6 values for guitar")

    barres = barres or []

    # Layout
    W, H = 260, 360
    margin_top = 60
    margin_left = 40
    grid_w = 180
    grid_h = 220
    strings = 6
    frets = frets_visible

    string_gap = grid_w / (strings - 1)
    fret_gap = grid_h / frets

    # Helpers
    def x_for_string(i_0_based: int) -> float:
        return margin_left + i_0_based * string_gap

    def y_for_fret_line(fret_index_0_based: int) -> float:
        return margin_top + fret_index_0_based * fret_gap

    def y_for_fret_center(fret_number: int) -> float:
        # fret_number is absolute, map to visible grid
        rel = fret_number - fret_start
        return margin_top + (rel + 0.5) * fret_gap

    # Start SVG
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    svg.append('<rect width="100%" height="100%" fill="white"/>')

    # Title
    svg.append(f'<text x="{W/2}" y="32" font-size="20" text-anchor="middle" font-family="Arial">{name}</text>')

    # Fret label if not starting at 1
    if fret_start != 1:
        svg.append(f'<text x="{margin_left + grid_w + 18}" y="{margin_top + 14}" font-size="14" font-family="Arial">fret {fret_start}</text>')

    # Nut (thicker top line if fret_start == 1)
    nut_y = margin_top
    nut_thickness = 6 if fret_start == 1 else 2
    svg.append(f'<line x1="{margin_left}" y1="{nut_y}" x2="{margin_left+grid_w}" y2="{nut_y}" stroke="black" stroke-width="{nut_thickness}"/>')

    # Frets (remaining)
    for f in range(1, frets + 1):
        y = y_for_fret_line(f)
        svg.append(f'<line x1="{margin_left}" y1="{y}" x2="{margin_left+grid_w}" y2="{y}" stroke="black" stroke-width="2"/>')

    # Strings
    for s in range(strings):
        x = x_for_string(s)
        svg.append(f'<line x1="{x}" y1="{margin_top}" x2="{x}" y2="{margin_top+grid_h}" stroke="black" stroke-width="2"/>')

    # Open/mute markers above nut
    marker_y = margin_top - 18
    for i, p in enumerate(positions):
        x = x_for_string(i)
        if p == -1:
            svg.append(f'<text x="{x}" y="{marker_y}" font-size="16" text-anchor="middle" font-family="Arial">x</text>')
        elif p == 0:
            svg.append(f'<text x="{x}" y="{marker_y}" font-size="16" text-anchor="middle" font-family="Arial">o</text>')

    # Barres
    for b in barres:
        # expect fromString/toString are 1..6 (6=lowest string, 1=highest)
        # We'll map to 0-based left-to-right (low->high) => low string index 0, high string index 5
        fret = int(b["fret"])
        from_s = int(b["fromString"])
        to_s = int(b["toString"])
        # Convert (6..1) to (0..5)
        a = 6 - from_s
        c = 6 - to_s
        x1 = x_for_string(min(a, c))
        x2 = x_for_string(max(a, c))
        y = y_for_fret_center(fret)
        svg.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="black" stroke-width="10" stroke-linecap="round"/>')

    # Finger dots
    for i, p in enumerate(positions):
        if p <= 0:
            continue
        # only draw if within visible window
        if not (fret_start <= p < fret_start + frets_visible):
            continue
        x = x_for_string(i)
        y = y_for_fret_center(p)
        svg.append(f'<circle cx="{x}" cy="{y}" r="10" fill="black"/>')

    svg.append("</svg>")
    return "\n".join(svg)

def etag_for(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

@app.get("/v1/render/chord.svg")
def render_chord_svg_get(
    instrument: str = Query("guitar"),
    name: str = Query("Chord"),
    pos: str = Query(..., description="CSV positions, e.g. -1,3,2,0,1,0"),
    fretStart: int = Query(1),
):
    positions = _parse_pos_csv(pos)

    if instrument != "guitar":
        return Response(content="Unsupported instrument", status_code=400, media_type="text/plain")

    svg = render_guitar_svg(name=name, positions=positions, fret_start=fretStart)
    et = etag_for(svg)

    headers = {
        "Content-Type": "image/svg+xml; charset=utf-8",
        "Cache-Control": "public, max-age=86400",
        "ETag": et,
    }
    return Response(content=svg, media_type="image/svg+xml", headers=headers)

@app.post("/v1/render/chord.svg")
def render_chord_svg_post(payload: dict = Body(...)):
    instrument = payload.get("instrument", "guitar")
    meta = payload.get("meta", {})
    diagram = payload.get("diagram", {})

    if instrument != "guitar":
        return Response(content="Unsupported instrument", status_code=400, media_type="text/plain")

    name = meta.get("name", "Chord")
    positions = diagram.get("positions", [])
    fret_start = int(diagram.get("fretStart", 1))
    frets_visible = int(diagram.get("fretsVisible", 5))
    barres = diagram.get("barres", [])

    svg = render_guitar_svg(
        name=name,
        positions=positions,
        fret_start=fret_start,
        frets_visible=frets_visible,
        barres=barres,
    )
    et = etag_for(svg)

    headers = {
        "Cache-Control": "public, max-age=86400",
        "ETag": et,
    }
    return Response(content=svg, media_type="image/svg+xml", headers=headers)

@app.get("/v1/chords/guitar/{chord}.svg")
def chord_svg_guitar(chord: str):
    shape = CHORD_SHAPES_GUITAR.get(chord)
    if not shape:
        return Response(content=f"Chord not found: {chord}", status_code=404, media_type="text/plain")

    svg = render_guitar_svg(
        name=chord,
        positions=shape["pos"],
        fret_start=shape.get("fretStart", 1),
    )
    return Response(content=svg, media_type="image/svg+xml")