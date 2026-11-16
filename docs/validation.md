# Validation

This page says what has been checked, how, and what has **not** been checked. Read it before trusting any number
the dose-volume tool returns.

**Summary:** the dose-volume metrics are verified against hand-calculated answers and against dicompyler-core on
synthetic phantoms. They are **not yet validated against a treatment planning system or real patient data.**
Do not use them for clinical decisions.

## Level 1: automated tests

The test suite runs on Linux and Windows for Python 3.11-3.13 in CI. For the dose-volume code it includes:

- phantoms with answers calculated by hand (uniform dose in a cube, a dose gradient, a structure with a hole,
  dose slices between contour slices, descending slice order, shifted grid origin, non-square voxels);
- an independent voxel-by-voxel reference for random dose fields;
- refusals for mismatched frames of reference and unsupported grids;
- mutation checks done by hand while developing: bugs were planted on purpose (swapped row/column spacing,
  ignoring the slab limit, skipping the frame-of-reference check, wrong rounding in D(p), ignoring holes, ...) and
  the tests had to fail. One planted bug survived the first version of the tests and led to a stronger test.

## Level 2: comparison with dicompyler-core on synthetic phantoms

[dicompyler-core](https://github.com/dicompyler/dicompyler-core) is an established open-source library for
dose-volume histograms. It is a useful cross-check, not ground truth: it decides which voxels belong to a structure
by different rules.

Setup of the run below (November 2026, Linux): rt-imaging-mcp with pydicom 3.0.2; dicompyler-core 0.5.6 in an
isolated environment with pydicom 2.4.5 and numpy 1.26.4. Dose grid 10 x 10 x N voxels of 2 mm, dose rising
smoothly with row, column and slice from 10 Gy. Structure number 1, `V11Gy` is the volume receiving at least 11 Gy.

| Phantom | volume (cm³) | mean (Gy) | D95 (Gy) | D50 (Gy) | D2 (Gy) | V11 Gy (cm³) |
|---|---|---|---|---|---|---|
| Cube, slices aligned | 1.000 / 1.000 | 10.900 / 10.905 | 10.30 / 10.26 | 10.90 / 10.86 | 11.65 / 11.61 | 0.432 / 0.432 |
| Hexagon, slices aligned | 1.120 / 1.120 | 11.525 / 11.530 | 10.90 / 10.86 | 11.55 / 11.51 | 12.30 / 12.26 | 1.024 / 1.024 |
| Structure with hole, aligned | 1.280 / 1.280 | 11.025 / 11.030 | 10.30 / 10.31 | 11.05 / 11.01 | 11.85 / 11.86 | 0.696 / 0.696 |
| Cube, dose slices between contour slices | 1.200 / 1.200 | 11.000 / 10.955 | 10.30 / 10.26 | 11.00 / 10.91 | 11.85 / 11.76 | 0.632 / 0.588 |

Each cell is *rt-imaging-mcp / dicompyler-core*.

How to read it:

- Where contour and dose slices line up, volumes and V(t) agree exactly and dose metrics agree within about
  0.04 Gy. That gap is expected: dicompyler-core builds a histogram with 0.01 Gy bins and interpolates, while
  rt-imaging-mcp uses the exact voxel doses.
- Where dose slices fall between contour slices, the two tools use different rules (rt-imaging-mcp assigns each dose
  slice to the nearest contour slice within one slab; dicompyler-core takes the nearest dose plane for each contour
  plane). Volumes still agree but dose metrics differ by up to about 0.09 Gy and V11 by about 7 % on this phantom.
  Expect differences of this kind on real data when the dose and CT grids differ.
- On a dose that is constant within each slice and steps between slices, D(p) is not well defined and the two tools
  give quite different values (for example D95 and D2). The phantoms above use a smooth dose for that reason.

Reproduce:

```bash
uv run python scripts/make_dvh_phantoms.py phantoms
uv run python scripts/compare_dvh.py phantoms/aligned_hexagon/struct.dcm phantoms/aligned_hexagon/dose.dcm 1 --percent 95 50 2 --gy 11
```

`compare_dvh.py` needs `uv` on PATH. It installs dicompyler-core in a temporary isolated environment.

## Level 3: real data

**Not done yet.** To be filled in after testing on publicly available, de-identified RT data. For each collection
record: name and version, licence and where it was obtained, number of cases, which tools were run, what worked,
what failed, and the comparison with dicompyler-core or a planning system export.

| Collection | Licence | Cases | Tools run | Result | Notes |
|---|---|---|---|---|---|
| _none yet_ | | | | | |

Rules for this step: obey each collection's licence and terms of use, keep the data outside the repository, and
record only aggregate numbers here, never file names, identifiers or images.

## Known differences from a planning system

- Voxel-centre inclusion with no partial-volume weighting, so results depend on the dose grid resolution.
- Each contour slice stands for a slab as thick as the median contour spacing.
- Overlapping, non-nested contours on one slice cancel each other (even-odd rule).
- Only axis-aligned dose grids in Gy with uniform slice spacing are supported.
- Planar-contour volumes are estimates, not the volumes a planning system reports.
