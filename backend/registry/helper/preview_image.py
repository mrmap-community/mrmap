"""Render validated WGS84 GeoJSON into a small, transient service thumbnail."""
import math
from io import BytesIO

from PIL import Image, ImageDraw


BACKGROUND = "#edf2f5"
FILL = "#a8cce5"
STROKE = "#246b9c"
MERCATOR_LATITUDE = 85.0511287798066


def _project(position):
    longitude, latitude = position[:2]
    latitude = max(-MERCATOR_LATITUDE, min(MERCATOR_LATITUDE, latitude))
    return math.radians(longitude), math.asinh(math.tan(math.radians(latitude)))


def _parts(geometry):
    """Flatten multi geometries into points, lines and polygon ring lists."""
    if geometry is None:
        return
    kind = geometry["type"]
    if kind == "GeometryCollection":
        for child in geometry["geometries"]:
            yield from _parts(child)
        return
    coordinates = geometry["coordinates"]
    if kind.startswith("Multi"):
        for child in coordinates:
            yield from _parts({"type": kind[5:], "coordinates": child})
    elif kind == "Point":
        yield kind, [[_project(coordinates)]]
    elif kind == "LineString":
        yield kind, [[_project(position) for position in coordinates]]
    elif kind == "Polygon":
        yield kind, [[_project(position) for position in ring] for ring in coordinates]


def render_feature_collection(collection, width=512, height=256):
    """Return PNG bytes with generic styles, fitting the returned feature sample.

    Input must already have passed the preview GeoJSON/permission validation.
    Project to Web Mercator with clamped polar latitudes and preserve its aspect
    ratio, including when the feature sample has a zero-width or zero-height
    extent. No upstream requests or persistence are performed here.
    """
    if any(type(value) is not int or not 1 <= value <= 2048 for value in (width, height)):
        raise ValueError("Thumbnail dimensions must be integers between 1 and 2048")
    parts = [part for feature in collection["features"] for part in _parts(feature.get("geometry"))]
    positions = [position for _, paths in parts for path in paths for position in path]
    if not positions:
        raise ValueError("No renderable geometry")
    xmin = min(x for x, _ in positions)
    xmax = max(x for x, _ in positions)
    ymin = min(y for _, y in positions)
    ymax = max(y for _, y in positions)
    padding = min(12, (width - 1) / 10, (height - 1) / 10)
    scales = []
    if xmax > xmin:
        scales.append((width - 1 - 2 * padding) / (xmax - xmin))
    if ymax > ymin:
        scales.append((height - 1 - 2 * padding) / (ymax - ymin))
    scale = min(scales) if scales else 1
    center_x, center_y = (xmin + xmax) / 2, (ymin + ymax) / 2

    def pixel(position):
        x, y = position
        return ((width - 1) / 2 + (x - center_x) * scale,
                (height - 1) / 2 - (y - center_y) * scale)

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for kind, paths in parts:
        paths = [[pixel(position) for position in path] for path in paths]
        if kind == "Point":
            x, y = paths[0][0]
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=STROKE, outline="white", width=1)
        elif kind == "LineString":
            draw.line(paths[0], fill=STROKE, width=2)
        else:
            # A mask preserves previously drawn features beneath polygon holes.
            mask = Image.new("L", image.size)
            mask_draw = ImageDraw.Draw(mask)
            for index, ring in enumerate(paths):
                mask_draw.polygon(ring, fill=255 if index == 0 else 0)
            image.paste(FILL, mask=mask)
            for ring in paths:
                draw.line(ring, fill=STROKE, width=2)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()
