from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image, ImageChops, ImageColor
from registry.helper.preview_image import BACKGROUND, FILL, STROKE, render_feature_collection


class PreviewImageTests(SimpleTestCase):
    @staticmethod
    def collection(*geometries):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": geometry}
            for geometry in geometries
        ]}

    def render(self, *geometries, **kwargs):
        content = render_feature_collection(self.collection(*geometries), **kwargs)
        image = Image.open(BytesIO(content))
        self.assertEqual(image.format, "PNG")
        image.load()
        return image

    def test_point_is_visible_and_centered_in_default_thumbnail(self):
        image = self.render({"type": "Point", "coordinates": [7, 50]})
        self.assertEqual(image.size, (512, 256))
        self.assertEqual(image.getpixel((256, 128)), ImageColor.getrgb(STROKE))
        self.assertEqual(image.getpixel((0, 0)), ImageColor.getrgb(BACKGROUND))

    def test_lines_fit_with_padding_and_preserve_projected_aspect(self):
        image = self.render({"type": "LineString", "coordinates": [[0, 0], [10, 0]]}, width=100, height=100)
        background = ImageColor.getrgb(BACKGROUND)
        points = [(x, y) for y in range(100) for x in range(100) if image.getpixel((x, y)) != background]
        self.assertTrue(points)
        self.assertGreater(min(x for x, _ in points), 0)
        self.assertLess(max(x for x, _ in points), 99)
        self.assertLess(max(y for _, y in points) - min(y for _, y in points), 3)
        # Near the equator, equal longitude/latitude spans remain near-square.
        square = self.render({"type": "Polygon", "coordinates": [
            [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
        ]}, width=200, height=100)
        bounds = ImageChops.difference(square, Image.new("RGB", square.size, BACKGROUND)).getbbox()
        self.assertLess(abs((bounds[2] - bounds[0]) - (bounds[3] - bounds[1])), 3)
        self.assertEqual(square.getpixel((50, 50)), background)
        self.assertEqual(square.getpixel((100, 50)), ImageColor.getrgb(FILL))
        self.assertEqual(square.getpixel((150, 50)), background)

    def test_polygon_hole_preserves_background_and_previously_drawn_features(self):
        polygon = {"type": "Polygon", "coordinates": [
            [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]],
            [[-1, -1], [-1, 1], [1, 1], [1, -1], [-1, -1]],
        ]}
        image = self.render(polygon, width=200, height=200)
        self.assertEqual(image.getpixel((100, 100)), ImageColor.getrgb(BACKGROUND))
        self.assertEqual(image.getpixel((35, 100)), ImageColor.getrgb(FILL))
        image = self.render({"type": "Point", "coordinates": [0, 0]}, polygon, width=200, height=200)
        self.assertEqual(image.getpixel((100, 100)), ImageColor.getrgb(STROKE))

    def test_multi_geometries_and_geometry_collections_are_rendered(self):
        geometries = [
            {"type": "MultiPoint", "coordinates": [[-3, 0], [3, 0]]},
            {"type": "MultiLineString", "coordinates": [[[-2, -1], [-2, 1]]]},
            {"type": "MultiPolygon", "coordinates": [[[[0, -1], [1, -1], [1, 1], [0, 1], [0, -1]]]]},
        ]
        image = self.render({"type": "GeometryCollection", "geometries": geometries}, width=200, height=100)
        colors = image.getcolors()
        self.assertIn(ImageColor.getrgb(FILL), [color for _, color in colors])
        self.assertIn(ImageColor.getrgb(STROKE), [color for _, color in colors])

    def test_polar_latitudes_render_without_projection_errors(self):
        image = self.render({"type": "LineString", "coordinates": [[-180, -90], [180, 90]]}, width=80, height=40)
        self.assertEqual(image.size, (80, 40))

    def test_empty_and_null_geometry_samples_are_unavailable(self):
        for collection in (self.collection(), self.collection(None), self.collection({"type": "GeometryCollection", "geometries": []})):
            with self.subTest(collection=collection), self.assertRaisesMessage(ValueError, "No renderable geometry"):
                render_feature_collection(collection)

    def test_dimensions_are_bounded(self):
        collection = self.collection({"type": "Point", "coordinates": [0, 0]})
        for dimensions in ({"width": 0}, {"height": -1}, {"width": 2049}, {"height": 2049}, {"width": 1.5}, {"height": True}):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                render_feature_collection(collection, **dimensions)
        self.assertEqual(self.render({"type": "Point", "coordinates": [0, 0]}, width=1, height=1).size, (1, 1))
