# Validation

This page says what has been checked, how, and what has **not** been checked. Read it before trusting any number
the dose-volume tool returns.

**Summary:** the dose-volume metrics are verified against hand-calculated answers and against dicompyler-core on
synthetic phantoms, and a first comparison with dicompyler-core on three patients of one public collection has been
done (Level 3, preliminary). They are **not validated against a treatment planning system.** Do not use them for
clinical decisions.

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
| Cube, dose slices between contour slices | 1.150 / 1.200 | 10.978 / 10.955 | 10.30 / 10.26 | 11.00 / 10.91 | 11.80 / 11.76 | 0.582 / 0.588 |

Each cell is *rt-imaging-mcp / dicompyler-core*.

How to read it:

- Where contour and dose slices line up, volumes and V(t) agree exactly and dose metrics agree within about
  0.04 Gy. That gap is expected: dicompyler-core builds a histogram with 0.01 Gy bins and interpolates, while
  rt-imaging-mcp uses the exact voxel doses.
- Where dose slices fall between contour slices, the two tools use different rules (rt-imaging-mcp weights every dose
  slice by the fraction of its thickness inside the contour slabs; dicompyler-core samples the nearest dose plane for
  each contour plane and multiplies by the contour thickness). Dose metrics differ by up to about 0.09 Gy and V11 by
  about 1 % on this phantom. The volumes differ by 4 % because the lowest 0.5 mm of the structure lies below the
  dose grid, which rt-imaging-mcp reports (`inside_grid` is false) and dicompyler-core does not.
- dicompyler-core's structure volume is a grid-sampled volume (dose-grid pixel centres inside each contour plane times
  the contour thickness), so it is compared with rt-imaging-mcp's grid-sampled volume, not with the polygon-area volume.
- On a dose that is constant within each slice and steps between slices, D(p) is not well defined and the two tools
  give quite different values (for example D95 and D2). The phantoms above use a smooth dose for that reason.

### Dose planes denser than contour planes (analytic check)

A real-data run (below) showed larger disagreements in cases where the dose planes were twice as dense as the contour
planes. A phantom reproduces that geometry and has an exact answer: 20 contour planes 3 mm apart (the structure spans
z = -1.5 to 58.5 mm if each contour stands for a slab half a spacing either side), dose planes every 1.5 mm, and a dose
that rises 0.4 Gy per mm. For a continuous structure the dose is uniform between 19.4 and 43.4 Gy.

| | min | max | mean | D95 | D50 | D2 | volume (cm³) |
|---|---|---|---|---|---|---|---|
| Exact (continuous, slab model) | 19.40 | 43.40 | 31.40 | 20.60 | 31.40 | 42.92 | 6.00 |
| rt-imaging-mcp before the end-plane weighting | 19.40 | 43.40 | 31.40 | 20.60 | 31.40 | 43.40 | 6.15 |
| rt-imaging-mcp now | 19.40 | 43.40 | 31.40 | 20.60 | 31.40 | 42.80 | 6.00 |
| dicompyler-core, default | 20.01 | 42.81 | 31.41 | 20.01 | 30.81 | 41.61 | 6.00 |
| dicompyler-core, one interpolated plane between contours | 20.01 | 42.81 | 31.41 | 20.61 | 30.81 | 42.21 | 5.85 |

- The earlier version of rt-imaging-mcp counted a dose plane lying exactly on the outer boundary in full at both ends,
  one plane too many (volume +2.5 %, D2 +0.48 Gy). Planes are now weighted by the fraction of their thickness inside
  the structure; the volume equals the sum of the slabs and D2 is within one plane step (0.6 Gy) of the exact value.
- dicompyler-core samples the dose only at the contour planes and does not extend the structure beyond its end
  contours, which is a different (also reasonable) model. With a steep gradient that alone gives differences of
  0.6 to 1.3 Gy in min, max, D95 and D2. This is a difference of model, not a measurement error of either tool, and
  the exact value above holds only for the slab model.
- The check is part of the test suite (`test_denser_dose_planes_reproduce_the_continuous_answer`), together with a
  mirrored gradient and a check that the volume equals the contour volume.

### Planes shared between two contour slices (growing cross-section)

A dose plane that lies exactly between two contour slices belongs half to each slab. The first version gave such a
plane wholly to the lower contour. With a cross-section that grows from slice to slice (ten contours 3 mm apart,
n x n voxel centres with n = 2..11, dose planes every 1.5 mm, dose rising 0.4 Gy per mm) the sum of the slabs is
6.060 cm³ and the voxel-weighted mean dose at the contour planes is 27.9485 Gy:

| | volume (cm³) | mean dose (Gy) |
|---|---|---|
| Plane given wholly to the lower contour | 5.709 (-5.8 %) | 28.0295 (+0.081) |
| Plane shared by overlap (current) | 6.060 | 27.9485 |

The check is part of the test suite (`test_a_growing_cross_section_does_not_bias_volume_or_mean_dose`), together with a
property test that every contour slab receives exactly its own thickness however the dose planes fall.

Reproduce:

```bash
uv run python scripts/make_dvh_phantoms.py phantoms
uv run python scripts/compare_dvh.py phantoms/aligned_hexagon/struct.dcm phantoms/aligned_hexagon/dose.dcm 1 --percent 95 50 2 --gy 11
```

`compare_dvh.py` and `validate_collection.py` need `uv` on PATH. They install dicompyler-core in a temporary
isolated environment (it needs pydicom < 3 and numpy < 2, which this project cannot share).

## Level 3: real data (preliminary)

**One collection, three patients, one comparison tool.** This is a first look, not a validation study.

- Collection: Pancreatic-CT-CBCT-SEG from The Cancer Imaging Archive (TCIA), https://doi.org/10.7937/TCIA.ESHQ-4D90.
  Licence: Creative Commons Attribution 4.0 International (CC BY 4.0), as stated on the collection page. The data
  is not part of this repository and is not redistributed; only aggregate numbers derived from it are published here.
  See "Hong, J., Reyngold, M., Crane, C., Cuaron, J., Hajj, C., Mann, J., Zinovoy, M., Yorke, E., LoCastro, E., Apte, A. P., & Mageras, G. (2021). Breath-hold CT and cone-beam CT images with expert manual organ-at-risk segmentations from radiation treatments of locally advanced pancreatic cancer [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.ESHQ-4D90" below.
- Data: 3 patients (planning CT structure sets and CBCT structure sets with the RTDOSE calculated on the planning CT).
- Run by the maintainer with `scripts/validate_collection.py`, November 2026, with the current version of the tool,
  against dicompyler-core 0.5.6: 9 structure/dose pairs were run, 1 further pair was skipped because the frames of
  reference differ, and 39 structures were compared (tolerances: 0.1 Gy for dose metrics, 2 % for volumes).

| Metric | Structures | Median \|difference\| | Max \|difference\| | Beyond tolerance |
|---|---|---|---|---|
| Volume (cm³) | 39 | 0.0002 | 0.0005 | 0 |
| Mean dose (Gy) | 39 | 0.0003 | 0.028 | 0 |
| D50 (Gy) | 39 | 0.0036 | 0.034 | 0 |
| D2 (Gy) | 39 | 0.0038 | 0.095 | 0 |
| D95 (Gy) | 39 | 0.0025 | 1.112 | 1 |
| V20 Gy (cm³) | 39 | 0.0001 | 1.768 | 3 |
| V30 Gy (cm³) | 39 | 0.0000 | 0.945 | 4 |
| V40 Gy (cm³) | 39 | 0.0000 | 1.955 | 3 |
| Minimum dose (Gy) | 39 | 0.0100 | 2.407 | 6 |
| Maximum dose (Gy) | 39 | 0.4615 | 1.519 | 31 |

Differences are rt-imaging-mcp minus dicompyler-core.

The same three patients were run after each change to the tool (structures beyond tolerance, with the largest
absolute difference in brackets):

| Version of rt-imaging-mcp | Mean dose | D95 | D50 | D2 |
|---|---|---|---|---|
| First run | 9 (0.245 Gy) | 5 (1.697 Gy) | 5 (0.711 Gy) | 4 (0.877 Gy) |
| After weighting the end planes | 6 (0.152 Gy) | 3 (1.385 Gy) | 4 (0.537 Gy) | 4 (1.128 Gy) |
| After sharing planes between contour slabs (current) | 0 (0.028 Gy) | 1 (1.112 Gy) | 0 (0.034 Gy) | 0 (0.095 Gy) |

What the runs show:

- **Most of the early disagreement was a bias in rt-imaging-mcp, not a difference of model.** Two biases were found
  with phantoms that have an exact answer (see Level 2) and fixed: a dose plane lying exactly on the outer boundary of a
  structure counted in full, and a plane lying exactly between two contour slices went wholly to the lower one. After
  both fixes the volume, mean dose, D50 and D2 agree with dicompyler-core for all 39 structures within 0.0005 cm³,
  0.03 Gy, 0.04 Gy and 0.1 Gy.
- **The disagreements followed the slice spacing.** Patient 1 has 1.5 mm dose slices and 3 mm contour slices, patient 2
  has 1 mm and 2 mm, patient 3 has 3 mm and 3 mm. Patient 3 agreed within 0.02 Gy from the first run; patients 1 and 2
  agreed only after the two fixes, which concern dose planes that fall between or at the end of contour slices.
- **D95 differs by more than 0.1 Gy in one structure of 39** (1.1 Gy, rt-imaging-mcp lower), unexplained. A candidate is
  the half-weighted dose planes rt-imaging-mcp includes beyond the end contours, which dicompyler-core does not sample.
- **V20, V30 and V40 differ by more than 2 % in 3 to 4 structures** (up to 1.95 cm³), unexplained. The largest V40
  difference did not change across versions, which points at a threshold-edge effect rather than at the sampling.
- **Minimum and maximum dose differ systematically** (the maximum by 0.46 Gy at the median). These are single-voxel
  extremes, and rt-imaging-mcp samples more dose planes than dicompyler-core and includes the end planes, so a different
  extreme is expected. They are not used for conclusions.
- **Agreement with another tool is not proof.** Both programs could share a mistake, for example in the voxel-inclusion
  rule. Together with the phantoms that have exact answers it is useful evidence, no more.
- Three patients from one collection and one treatment site are not enough to estimate how large the differences
  usually are, and the tool has not been compared with a treatment planning system.

Open questions: the one D95 outlier, the V(t) differences, and how both tools compare with a much finer sampling of the
same structure. A planning system DVH export or a finer-sampling reference would be needed to answer them.

### Data attribution

The data used in Level 3 is credited as the collection page and the TCIA data usage policy require:

- Dataset: Pancreatic-CT-CBCT-SEG, The Cancer Imaging Archive, https://doi.org/10.7937/TCIA.ESHQ-4D90, licensed under
  CC BY 4.0. **Copy the exact citation text from the "Citations & Data Usage Policy" section of the collection page
  here**, including the authors and the data descriptor if the page lists one.
- Platform citation that TCIA asks users to include: Clark K, Vendt B, Smith K, et al. The Cancer Imaging Archive (TCIA):
  maintaining and operating a public information repository. Journal of Digital Imaging 26(6), 1045-1057 (2013),
  https://doi.org/10.1007/s10278-013-9622-7 (verify against the collection page).
- No attempt was made to identify or contact any participant, and nothing derived from the data that could reveal
  identity is published.

How to repeat or extend this:

1. Choose a collection with RTSTRUCT and RTDOSE and read its licence and data usage policy first. Follow its citation
   rules and accept any restricted-data agreement before downloading. This repository must never contain the data.
2. Download a handful of cases to a folder **outside** this repository.
3. Run the validation script. It pairs each RTSTRUCT with an RTDOSE of the same frame of reference, runs
   `rt_dvh_metrics` on the structures, runs dicompyler-core on the same files and prints aggregate numbers only
   (cases are numbered, no paths, no identifiers, no non-standard names unless you enable them):
   ```bash
   uv run python scripts/validate_collection.py PATH_TO_CASES --max-cases 5 --include-redacted --json-out results.json
   ```
   Use `--case-depth 2` when the folder holds one sub-folder per collection with the patients inside it, `--gy` to
   choose V(t) thresholds that make sense for the prescription and `--debug-reference` to see why the reference run
   fails (its output can contain file paths: never paste it unedited). Do not commit `results.json`.
4. Record what was compared, what differed, what was refused and why. Report disagreements as they are.

Rules for this step: obey each collection's licence and terms of use, keep the data outside the repository, and
record only aggregate numbers here, never file names, identifiers or images.

## Known differences from a planning system

- Voxel-centre inclusion with no partial-volume weighting, so results depend on the dose grid resolution.
- Each contour slice stands for a slab as thick as the median contour spacing.
- Overlapping, non-nested contours on one slice cancel each other (even-odd rule).
- Only axis-aligned dose grids in Gy with uniform slice spacing are supported.
- Planar-contour volumes are estimates, not the volumes a planning system reports.
