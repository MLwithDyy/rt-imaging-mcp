"""Synthetic test data. Everything here is fake and generated at run time (rule R9)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence as DicomSequence
from pydicom.uid import (
    CTImageStorage,
    ExplicitVRLittleEndian,
    RTStructureSetStorage,
    generate_uid,
)

FAKE_NAME = "SYNTHNAME^FAKE^ZZ"
FAKE_ID = "SYNTHID-0001"
FAKE_BIRTH = "19000101"
FAKE_INSTITUTION = "SYNTH INSTITUTION"
FAKE_PHYSICIAN = "SYNTHDOC^FAKE"
FAKE_ACCESSION = "SYNTHACC-77"
FAKE_DESCRIPTION = "SYNTH DESCRIPTION WITH NAME"
FAKE_PRIVATE = "SYNTH PRIVATE VALUE"

IDENTIFYING_VALUES = (
    FAKE_NAME,
    FAKE_ID,
    FAKE_BIRTH,
    FAKE_INSTITUTION,
    FAKE_PHYSICIAN,
    FAKE_ACCESSION,
    FAKE_PRIVATE,
)


def build_ct_dataset(**overrides: Any) -> Dataset:
    """Build a tiny CT-like dataset that deliberately contains fake identifiers."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()

    ds.PatientName = FAKE_NAME
    ds.PatientID = FAKE_ID
    ds.PatientBirthDate = FAKE_BIRTH
    ds.PatientSex = "O"
    ds.InstitutionName = FAKE_INSTITUTION
    ds.ReferringPhysicianName = FAKE_PHYSICIAN
    ds.AccessionNumber = FAKE_ACCESSION
    ds.StudyDescription = FAKE_DESCRIPTION
    ds.StudyDate = "20000101"

    ds.add_new(0x00110010, "LO", "SYNTH PRIVATE CREATOR")
    ds.add_new(0x00111001, "LO", FAKE_PRIVATE)

    ds.Modality = "CT"
    ds.Rows = 4
    ds.Columns = 4
    ds.SamplesPerPixel = 1
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelSpacing = [0.5, 0.5]
    ds.SliceThickness = 2.5
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, 0]
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    ds.PixelData = np.arange(16, dtype=np.uint16).tobytes()

    for key, value in overrides.items():
        setattr(ds, key, value)
    return ds


def write_dicom(path: Path, **overrides: Any) -> Path:
    """Write a synthetic DICOM file (with preamble and file meta) and return its path."""
    ds = build_ct_dataset(**overrides)
    ds.save_as(path, enforce_file_format=True)
    return path


FAKE_NIFTI_DESCRIP = "SYNTHNAME descrip field"


def write_nifti(path: Path, shape: tuple[int, ...] = (4, 5, 6), gz: bool = False) -> Path:
    """Write a tiny synthetic NIfTI-1 file whose free-text header field holds a fake name."""
    image = nib.Nifti1Image(np.zeros(shape, dtype=np.int16), affine=np.diag([1.5, 1.5, 2.0, 1.0]))
    image.header["descrip"] = FAKE_NIFTI_DESCRIP.encode()
    image.header.set_xyzt_units("mm", "sec")
    target = path.with_suffix(".nii.gz") if gz else path.with_suffix(".nii")
    nib.save(image, str(target))
    return target


FAKE_STRUCT_LABEL = "SYNTHSTRUCTLABEL"
FAKE_ROI_NAME = "SYNTHROI_Budi"
FAKE_OBS_LABEL = "SYNTHOBSLABEL"
RT_IDENTIFYING_VALUES = (*IDENTIFYING_VALUES, FAKE_STRUCT_LABEL, FAKE_ROI_NAME, FAKE_OBS_LABEL)

Point2D = tuple[float, float]


@dataclass
class RoiSpec:
    """One synthetic structure: contours are (z, [x, y points]) tuples."""

    number: int
    name: str
    interpreted_type: str = "ORGAN"
    algorithm: str = "MANUAL"
    contours: list[tuple[float, list[Point2D]]] = field(default_factory=list)


def square(x0: float, y0: float, size: float) -> list[Point2D]:
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]


def extrude(polygon: list[Point2D], z_values: Sequence[float]) -> list[tuple[float, list[Point2D]]]:
    """The same polygon on every listed slice."""
    return [(z, polygon) for z in z_values]


def build_rtstruct_dataset(rois: Sequence[RoiSpec]) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = RTStructureSetStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    ds.SOPClassUID = RTStructureSetStorage
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = "RTSTRUCT"
    ds.PatientName = FAKE_NAME
    ds.PatientID = FAKE_ID
    ds.StructureSetLabel = FAKE_STRUCT_LABEL

    definitions = DicomSequence()
    contour_items = DicomSequence()
    observations = DicomSequence()
    for roi in rois:
        definition = Dataset()
        definition.ROINumber = roi.number
        definition.ROIName = roi.name
        definition.ROIGenerationAlgorithm = roi.algorithm
        definitions.append(definition)

        roi_contour = Dataset()
        roi_contour.ReferencedROINumber = roi.number
        contour_sequence = DicomSequence()
        for z, polygon in roi.contours:
            contour = Dataset()
            contour.ContourGeometricType = "CLOSED_PLANAR"
            contour.NumberOfContourPoints = len(polygon)
            contour.ContourData = [value for x, y in polygon for value in (x, y, z)]
            contour_sequence.append(contour)
        if roi.contours:
            roi_contour.ContourSequence = contour_sequence
        contour_items.append(roi_contour)

        observation = Dataset()
        observation.ObservationNumber = roi.number
        observation.ReferencedROINumber = roi.number
        observation.RTROIInterpretedType = roi.interpreted_type
        observation.ROIObservationLabel = FAKE_OBS_LABEL
        observations.append(observation)

    ds.StructureSetROISequence = definitions
    ds.ROIContourSequence = contour_items
    ds.RTROIObservationsSequence = observations
    return ds


def write_rtstruct(path: Path, rois: Sequence[RoiSpec]) -> Path:
    build_rtstruct_dataset(rois).save_as(path, enforce_file_format=True)
    return path
