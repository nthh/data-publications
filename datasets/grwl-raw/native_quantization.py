"""Tippecanoe 2.79.0 EPSG:4326 vertex quantization helpers.

The pinned builder uses Tippecanoe's ordinary EPSG:4326 path, not
``--grid-low-zooms``. ``projection.cpp`` first rounds longitude/latitude to
integer zoom-32 world coordinates. Before line simplification, ``tile.cpp``
calls ``remove_noop`` with ``shift = 32 - z - line_detail``; ``clip.cpp``
rounds each coordinate divided by that power of two, with C++ ``std::round``
(half ties away from zero). At z12/detail12 this second step is a 1/4096-tile
grid. This intentionally models vertices, not line length or geometry loss.

Sources pinned by ``datasets/grwl/tippecanoe.lock.json``:
https://github.com/felt/tippecanoe/tree/68ab8dcc229f95b8b25877697d5e8d66783af503
Relevant files: ``projection.cpp`` (lonlat2tile), ``tile.cpp`` (remove_noop
call before simplification), and ``clip.cpp`` (remove_noop and tile scaling).

The optional tile coordinates model a second, explicitly tile-local
quantization: subtract the tile's zoom-32 origin before rounding, then add its
coarse-grid origin back. Upstream's pre-simplification ``remove_noop`` is
world-coordinate based; callers classifying source-part collapse should omit
tile coordinates. Tile-local mode is exposed for diagnostics around buffered
coordinates, where negative half ties are not translation invariant.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np


_WORLD32 = 1 << 32


def _round_away_from_zero(values: np.ndarray) -> np.ndarray:
    """Vectorized equivalent of C++ std::round for finite float values."""
    values = np.asarray(values, dtype=np.float64)
    return np.where(values >= 0.0, np.floor(values + 0.5), np.ceil(values - 0.5)).astype(np.int64)


def _coordinates(coords: Iterable[Iterable[float]]) -> np.ndarray:
    try:
        points = np.asarray(coords, dtype=np.float64)
    except (TypeError, ValueError):
        points = np.asarray(list(coords), dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("coords must be a finite Nx2 array of longitude/latitude pairs")
    if not np.isfinite(points).all():
        raise ValueError("coords must contain only finite longitude/latitude values")
    return points


def project_epsg4326_zoom32(coords: Iterable[Iterable[float]]) -> np.ndarray:
    """Return Tippecanoe's integer EPSG:4326 world coordinates at zoom 32.

    The formula follows ``projection.cpp::lonlat2tile``. Tippecanoe clamps
    finite longitude to [-360, 360] and latitude to [-89.9, 89.9] before the
    projection; normal GRWL coordinates are already in the conventional ranges.
    """
    points = _coordinates(coords)
    lon = np.clip(points[:, 0], -360.0, 360.0)
    lat = np.clip(points[:, 1], -89.9, 89.9)
    projected = []
    for longitude, latitude in zip(lon, lat, strict=True):
        # Keep operation order aligned with projection.cpp::lonlat2tile.
        lat_rad = float(latitude) * math.pi / 180.0
        x = _WORLD32 * ((float(longitude) + 180.0) / 360.0)
        y = _WORLD32 * (1.0 - (math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)) / 2.0
        projected.append((_round_away_from_zero(np.array([x]))[0],
                          _round_away_from_zero(np.array([y]))[0]))
    return np.asarray(projected, dtype=np.int64).reshape((-1, 2))


def quantized_world_grid(
    coords: Iterable[Iterable[float]],
    z: int = 12,
    detail: int = 12,
    tile_x: int | None = None,
    tile_y: int | None = None,
) -> np.ndarray:
    """Quantize lon/lat vertices as Tippecanoe and return global grid indices.

    The result is an int64 ``Nx2`` array in global coarse-grid (x,y) indices,
    where a tile spans ``2**detail`` grid units. With no tile arguments, this
    matches the world-coordinate ``remove_noop`` stage used by the pinned
    builder. Supply both tile coordinates to inspect local rounding instead;
    the result is re-offset into global grid indices after local rounding.

    ``detail`` and ``z`` must satisfy ``z + detail <= 32``, matching the
    nonnegative ``shift`` consumed by Tippecanoe. Passing only one tile axis is
    an error.
    """
    if isinstance(z, bool) or not isinstance(z, (int, np.integer)) or not 0 <= z <= 32:
        raise ValueError("z must be an integer from 0 through 32")
    if isinstance(detail, bool) or not isinstance(detail, (int, np.integer)) or not 0 <= detail <= 32:
        raise ValueError("detail must be an integer from 0 through 32")
    shift = 32 - int(z) - int(detail)
    if shift < 0:
        raise ValueError("z + detail must not exceed 32")
    if shift > 62:
        raise ValueError("32 - z - detail must be at most 62")
    if (tile_x is None) != (tile_y is None):
        raise ValueError("tile_x and tile_y must be supplied together")

    points32 = project_epsg4326_zoom32(coords)
    divisor = 1 << shift
    if tile_x is None:
        return _round_away_from_zero(points32.astype(np.float64) / divisor)

    for axis, tile in (("tile_x", tile_x), ("tile_y", tile_y)):
        if isinstance(tile, bool) or not isinstance(tile, (int, np.integer)):
            raise ValueError(f"{axis} must be an integer")
        if not 0 <= int(tile) < (1 << int(z)):
            raise ValueError(f"{axis} is outside the z={z} tile range")

    tile_origin32 = np.array([int(tile_x), int(tile_y)], dtype=np.int64) * (1 << (32 - int(z)))
    coarse_tile_origin = np.array([int(tile_x), int(tile_y)], dtype=np.int64) * (1 << int(detail))
    local = points32 - tile_origin32
    return _round_away_from_zero(local.astype(np.float64) / divisor) + coarse_tile_origin


def quantization_diagnostics(
    coords: Iterable[Iterable[float]],
    z: int = 12,
    detail: int = 12,
) -> dict[str, list[list[int]] | list[list[float]]]:
    """Return continuous grid, zoom-32 projected coordinates, and native grid."""
    points = _coordinates(coords)
    quantized = quantized_world_grid(points, z=z, detail=detail)
    scale = 1 << (int(z) + int(detail))
    continuous = np.column_stack((
        ((points[:, 0] + 180.0) / 360.0) * scale,
        (1.0 - np.log(np.tan(np.deg2rad(np.clip(points[:, 1], -89.9, 89.9)))
                      + 1.0 / np.cos(np.deg2rad(np.clip(points[:, 1], -89.9, 89.9)))) / math.pi) * scale / 2.0,
    ))
    return {
        "continuous_world_grid": continuous.tolist(),
        "zoom32_world": project_epsg4326_zoom32(points).tolist(),
        "quantized_world_grid": quantized.tolist(),
    }
