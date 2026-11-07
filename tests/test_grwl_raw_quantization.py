import importlib.util
import gzip
import json
from pathlib import Path
import unittest

import numpy as np
import mapbox_vector_tile
from pmtiles.reader import MmapSource, Reader


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "datasets/grwl-raw/native_quantization.py"
SPEC = importlib.util.spec_from_file_location("grwl_raw_native_quantization", MODULE_PATH)
quantizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quantizer)


class NativeQuantizationTests(unittest.TestCase):
    def test_target_matches_native_zoom32_projection_and_tie_away(self):
        target = [
            [12.0, 57.85976955918039],
            [11.999999244516006, 57.859769577051296],
        ]
        diagnostic = quantizer.quantization_diagnostics(target)
        self.assertEqual(diagnostic["zoom32_world"], [
            [2290649225, 1296751776],
            [2290649216, 1296751776],
        ])
        self.assertEqual(diagnostic["quantized_world_grid"], [
            [8947849, 5065437],
            [8947849, 5065437],
        ])
        self.assertEqual(quantizer.quantized_world_grid(target).shape, (2, 2))
        self.assertEqual(quantizer.quantized_world_grid(target).dtype, np.dtype("int64"))

    def test_native_surviving_near_threshold_and_phase_controls(self):
        # Native fixture 91007: a 0.036-grid-unit crossing survives as the
        # one-cell MVT line [[2185,2781],[2184,2781]].
        span_036 = [
            [12.000000008496073, 57.859769568115844],
            [11.999999236019931, 57.859769568115844],
        ]
        self.assertNotEqual(*quantizer.quantized_world_grid(span_036).tolist())
        span_004 = [
            [11.999999713897694, 57.859769559180386],
            [11.999998855590832, 57.859769559180386],
        ]
        self.assertNotEqual(*quantizer.quantized_world_grid(span_004).tolist())

        # Native fixture 92002: same target-scale span, shifted -0.03 grid
        # units, also survives. Its +0.00 and +0.03 phase controls collapse.
        phase_negative = [
            [11.999999356643144, 57.859769568115844],
            [11.999998600412539, 57.859769568115844],
        ]
        phase_center = [
            [12.00000000037329, 57.859769568115844],
            [11.999999244142714, 57.859769568115844],
        ]
        phase_positive = [
            [12.000000644103437, 57.859769568115844],
            [11.99999988787286, 57.859769568115844],
        ]
        self.assertNotEqual(*quantizer.quantized_world_grid(phase_negative).tolist())
        self.assertEqual(*quantizer.quantized_world_grid(phase_center).tolist())
        self.assertEqual(*quantizer.quantized_world_grid(phase_positive).tolist())

    def test_native_omitted_near_threshold_and_shift_controls_collapse(self):
        # Native fixture 91006 is 0.03524 grid units and omitted. After
        # projection to 2^32 its second x is the exact 8947848.5 tie.
        span_03524 = [
            [12.000000000342169, 57.859769568115844],
            [11.999999244173836, 57.859769568115844],
        ]
        shifted_plus = [
            [12.000002145767212, 57.859769559180386],
            [12.000001390283217, 57.859769577051296],
        ]
        shifted_minus = [
            [11.999997854232788, 57.859769559180386],
            [11.999997098748793, 57.859769577051296],
        ]
        for coords in (span_03524, shifted_plus, shifted_minus):
            quantized = quantizer.quantized_world_grid(coords)
            self.assertEqual(quantized[0].tolist(), quantized[1].tolist())

    def test_all_stored_native_fixture_ids_and_geometry_match_predictions(self):
        directory = ROOT / "research/grwl-raw-release-20261102/global-display-diagnostics-r1"
        for stem in ("native-quantization-controls", "native-threshold-controls"):
            with self.subTest(fixture=stem):
                features = json.loads((directory / (stem + ".geojson")).read_text())["features"]
                predicted = {}
                for feature in features:
                    for part in feature["geometry"]["coordinates"]:
                        grid = quantizer.quantized_world_grid(part)
                        if np.any(grid[1:] != grid[:-1]):
                            predicted[feature["id"]] = (grid - [2184*4096, 1236*4096]).tolist()
                with (directory / (stem + ".pmtiles")).open("rb") as stream:
                    reader = Reader(MmapSource(stream))
                    raw = reader.get(12, 2184, 1236)
                    if raw[:2] == b"\x1f\x8b":
                        raw = gzip.decompress(raw)
                    decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})["grwl_raw"]["features"]
                self.assertEqual(set(predicted), {feature["id"] for feature in decoded})
                for feature in decoded:
                    self.assertEqual(predicted[feature["id"]], feature["geometry"]["coordinates"])

    def test_cpp_round_half_away_signs(self):
        values = np.array([-1.5, -0.5, 0.5, 1.5], dtype=np.float64)
        self.assertEqual(quantizer._round_away_from_zero(values).tolist(), [-2, -1, 1, 2])

    def test_negative_local_half_tie_differs_from_canonical_world_grid(self):
        # This longitude projects to 0.5 pixel west of tile 2184's origin.
        # Canonical world rounding sees a positive half tie and rounds up;
        # local rounding sees -0.5 and rounds away from zero to -1. That
        # difference applies to buffered tile-local coordinates, not the
        # pinned pre-simplification world-coordinate no-op check.
        z, detail, tile_x, tile_y = 12, 12, 2184, 2048
        x32 = tile_x * (1 << (32 - z)) - 128
        lon = x32 / (1 << 32) * 360.0 - 180.0
        coords = [[lon, 0.0]]
        world = quantizer.quantized_world_grid(coords, z, detail)
        local = quantizer.quantized_world_grid(coords, z, detail, tile_x, tile_y)
        self.assertEqual(world[0, 0], tile_x * (1 << detail))
        self.assertEqual(local[0, 0], tile_x * (1 << detail) - 1)
        self.assertEqual(world[0, 1], local[0, 1])

        # The same sign-sensitive behavior applies to y at the north edge of
        # tile 2048. This verifies latitude projection and local tie handling.
        y32 = tile_y * (1 << (32 - z)) - 128
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * y32 / (1 << 32)))))
        y_coords = [[0.0, lat]]
        world_y = quantizer.quantized_world_grid(y_coords, z, detail)
        local_y = quantizer.quantized_world_grid(y_coords, z, detail, tile_x, tile_y)
        self.assertEqual(world_y[0, 1], tile_y * (1 << detail))
        self.assertEqual(local_y[0, 1], tile_y * (1 << detail) - 1)

    def test_input_and_tile_arguments_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            quantizer.quantized_world_grid([[float("nan"), 1.0]])
        with self.assertRaisesRegex(ValueError, "Nx2"):
            quantizer.quantized_world_grid([1.0, 2.0])
        with self.assertRaisesRegex(ValueError, "supplied together"):
            quantizer.quantized_world_grid([[0.0, 0.0]], tile_x=1)
        with self.assertRaisesRegex(ValueError, "tile_x"):
            quantizer.quantized_world_grid([[0.0, 0.0]], tile_x=-1, tile_y=0)


if __name__ == "__main__":
    unittest.main()
