from __future__ import annotations

from PIL import Image

from app.sprite_engine.quality.structural import evaluate_sprite_quality


def _image_with_pixels(size: int, pixels: set[tuple[int, int]]) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for x, y in pixels:
        image.putpixel((x, y), (255, 255, 255, 255))
    return image


def test_quality_accepts_one_compact_connected_silhouette():
    image = _image_with_pixels(10, {(x, y) for x in range(2, 8) for y in range(2, 8)})

    report = evaluate_sprite_quality(image, min_occupancy=0.08, max_occupancy=0.70)

    assert report.passed is True
    assert report.connected_components == 1
    assert report.isolated_pixel_count == 0
    assert report.issues == ()


def test_quality_reports_separated_components_and_isolated_pixels():
    image = _image_with_pixels(10, {(2, 2), (7, 7)})

    report = evaluate_sprite_quality(image, min_occupancy=0.0, max_occupancy=1.0)

    assert report.passed is False
    assert report.connected_components == 2
    assert report.isolated_pixel_count == 2
    assert {issue.code for issue in report.issues} == {"component_count", "isolated_pixels"}


def test_quality_treats_diagonal_pixels_as_one_component():
    image = _image_with_pixels(10, {(3, 3), (4, 4)})

    report = evaluate_sprite_quality(image, min_occupancy=0.0, max_occupancy=1.0)

    assert report.connected_components == 1
    assert report.isolated_pixel_count == 0
