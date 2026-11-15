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
    RTDoseStorage,
    RTPlanStorage,
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


FAKE_PLAN_LABEL = "SYNTHPLANLABEL"
FAKE_PLAN_NAME = "SYNTHPLANNAME"
FAKE_MACHINE = "SYNTHMACHINE"
FAKE_BEAM_NAME = "SYNTHBEAM_Budi"
FAKE_DOSE_REF_DESCRIPTION = "SYNTHDOSEREF"
FAKE_REVIEWER = "SYNTHREVIEWER^FAKE"
FAKE_REFERENCED_UID = "1.2.826.0.1.3680043.9.7777.1234567"
ALL_RT_IDENTIFYING_VALUES = (
    *RT_IDENTIFYING_VALUES,
    FAKE_PLAN_LABEL,
    FAKE_PLAN_NAME,
    FAKE_MACHINE,
    FAKE_BEAM_NAME,
    FAKE_DOSE_REF_DESCRIPTION,
    FAKE_REVIEWER,
    FAKE_REFERENCED_UID,
)


def build_rtdose_dataset(
    raw: np.ndarray[Any, Any],
    *,
    scaling: float = 0.001,
    pixel_spacing: tuple[float, float] = (2.5, 2.0),
    slice_offsets: Sequence[float] | None = None,
    **overrides: Any,
) -> Dataset:
    """Synthetic RTDOSE. ``raw`` has shape (frames, rows, columns) and is stored as uint32."""
    frames, rows, columns = raw.shape
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = RTDoseStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    ds.SOPClassUID = RTDoseStorage
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = "RTDOSE"
    ds.PatientName = FAKE_NAME
    ds.PatientID = FAKE_ID
    referenced_plan = Dataset()
    referenced_plan.ReferencedSOPClassUID = RTPlanStorage
    referenced_plan.ReferencedSOPInstanceUID = FAKE_REFERENCED_UID
    ds.ReferencedRTPlanSequence = DicomSequence([referenced_plan])

    ds.DoseUnits = "GY"
    ds.DoseType = "PHYSICAL"
    ds.DoseSummationType = "PLAN"
    ds.DoseGridScaling = scaling
    ds.Rows = rows
    ds.Columns = columns
    if frames > 1:
        ds.NumberOfFrames = frames
        offsets = (
            list(slice_offsets) if slice_offsets is not None else [3.0 * i for i in range(frames)]
        )
        ds.GridFrameOffsetVector = offsets
    ds.PixelSpacing = list(pixel_spacing)
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [-100.0, -100.0, 0.0]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 32
    ds.BitsStored = 32
    ds.HighBit = 31
    ds.PixelRepresentation = 0
    ds.PixelData = raw.astype(np.uint32).tobytes()

    for key, value in overrides.items():
        setattr(ds, key, value)
    return ds


def write_rtdose(path: Path, raw: np.ndarray[Any, Any], **kwargs: Any) -> Path:
    build_rtdose_dataset(raw, **kwargs).save_as(path, enforce_file_format=True)
    return path


@dataclass
class BeamSpec:
    number: int
    name: str = "B"
    radiation: str = "PHOTON"
    beam_type: str = "STATIC"
    delivery: str = "TREATMENT"
    energy: float = 6.0
    gantry: float = 0.0
    direction: str = "NONE"
    collimator: float = 0.0
    couch: float = 0.0
    control_points: int = 2
    dose: float = 2.0
    meterset: float = 200.0


def build_rtplan_dataset(
    beams: Sequence[BeamSpec],
    *,
    fractions: int | None = 25,
    prescription_gy: float = 50.0,
    organ_at_risk_max_gy: float = 45.0,
    **overrides: Any,
) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = RTPlanStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()

    ds.SOPClassUID = RTPlanStorage
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = "RTPLAN"
    ds.PatientName = FAKE_NAME
    ds.PatientID = FAKE_ID
    ds.InstitutionName = FAKE_INSTITUTION
    ds.RTPlanLabel = FAKE_PLAN_LABEL
    ds.RTPlanName = FAKE_PLAN_NAME
    ds.ReviewerName = FAKE_REVIEWER
    ds.RTPlanGeometry = "PATIENT"
    ds.ApprovalStatus = "APPROVED"
    ds.PlanIntent = "CURATIVE"

    beam_items = DicomSequence()
    referenced = DicomSequence()
    for spec in beams:
        beam = Dataset()
        beam.BeamNumber = spec.number
        beam.BeamName = FAKE_BEAM_NAME if spec.name == "B" else spec.name
        beam.BeamType = spec.beam_type
        beam.RadiationType = spec.radiation
        beam.TreatmentDeliveryType = spec.delivery
        beam.TreatmentMachineName = FAKE_MACHINE
        beam.NumberOfControlPoints = spec.control_points
        control_point = Dataset()
        control_point.ControlPointIndex = 0
        control_point.NominalBeamEnergy = spec.energy
        control_point.GantryAngle = spec.gantry
        control_point.GantryRotationDirection = spec.direction
        control_point.BeamLimitingDeviceAngle = spec.collimator
        control_point.PatientSupportAngle = spec.couch
        beam.ControlPointSequence = DicomSequence([control_point])
        beam_items.append(beam)

        reference = Dataset()
        reference.ReferencedBeamNumber = spec.number
        reference.BeamDose = spec.dose
        reference.BeamMeterset = spec.meterset
        referenced.append(reference)
    ds.BeamSequence = beam_items

    if fractions is not None:
        group = Dataset()
        group.FractionGroupNumber = 1
        group.NumberOfFractionsPlanned = fractions
        group.NumberOfBeams = len(beams)
        group.NumberOfBrachyApplicationSetups = 0
        group.ReferencedBeamSequence = referenced
        ds.FractionGroupSequence = DicomSequence([group])

    target = Dataset()
    target.DoseReferenceNumber = 1
    target.DoseReferenceType = "TARGET"
    target.DoseReferenceDescription = FAKE_DOSE_REF_DESCRIPTION
    target.TargetPrescriptionDose = prescription_gy
    organ = Dataset()
    organ.DoseReferenceNumber = 2
    organ.DoseReferenceType = "ORGAN_AT_RISK"
    organ.OrganAtRiskMaximumDose = organ_at_risk_max_gy
    ds.DoseReferenceSequence = DicomSequence([target, organ])

    for key, value in overrides.items():
        setattr(ds, key, value)
    return ds


def write_rtplan(path: Path, beams: Sequence[BeamSpec], **kwargs: Any) -> Path:
    build_rtplan_dataset(beams, **kwargs).save_as(path, enforce_file_format=True)
    return path
