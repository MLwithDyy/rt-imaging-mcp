"""RT plan tool: summary of an RTPLAN.

Plan label and name, beam names and descriptions, machine and institution names,
reviewer names and dose reference descriptions are free text and are never returned.
Only numbers and DICOM enumerated code strings are returned (rule R11).
"""

from __future__ import annotations

from itertools import islice
from typing import Any

from rt_imaging_mcp.config import Config
from rt_imaging_mcp.security.errors import NotRtPlanError, RtImagingMcpError
from rt_imaging_mcp.tools.dicom import read_header
from rt_imaging_mcp.tools.rt_common import code, number, prepare_rt_file

MAX_BEAMS = 200
MAX_DOSE_REFERENCES = 100

PLAN_GEOMETRIES = frozenset({"PATIENT", "TREATMENT_DEVICE"})
APPROVAL_STATUSES = frozenset({"APPROVED", "UNAPPROVED", "REJECTED"})
PLAN_INTENTS = frozenset(
    {
        "CURATIVE",
        "PALLIATIVE",
        "PROPHYLACTIC",
        "VERIFICATION",
        "MACHINE_QA",
        "RESEARCH",
        "SERVICE",
    }
)
BEAM_TYPES = frozenset({"STATIC", "DYNAMIC"})
RADIATION_TYPES = frozenset({"PHOTON", "ELECTRON", "PROTON", "NEUTRON", "ION"})
DELIVERY_TYPES = frozenset({"TREATMENT", "OPEN_PORTFILM", "TRMT_PORTFILM", "CONTINUATION", "SETUP"})
ROTATION_DIRECTIONS = frozenset({"CW", "CCW", "NONE"})
DOSE_REFERENCE_TYPES = frozenset({"TARGET", "ORGAN_AT_RISK"})


def _integer(value: Any) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def _beam_entry(
    beam: Any, fraction_values: dict[int, tuple[float | None, float | None]]
) -> dict[str, Any]:
    number_ = _integer(beam.get("BeamNumber"))
    first_control_point = None
    control_points = beam.get("ControlPointSequence")
    if control_points:
        first_control_point = control_points[0]
    beam_dose, meterset = (
        fraction_values.get(number_, (None, None)) if number_ is not None else (None, None)
    )
    entry: dict[str, Any] = {
        "beam_number": number_,
        "beam_type": code(beam.get("BeamType"), BEAM_TYPES),
        "radiation_type": code(beam.get("RadiationType"), RADIATION_TYPES),
        "treatment_delivery_type": code(beam.get("TreatmentDeliveryType"), DELIVERY_TYPES),
        "control_point_count": _integer(beam.get("NumberOfControlPoints")),
        "nominal_energy": None,
        "gantry_angle_start": None,
        "gantry_rotation_direction": None,
        "collimator_angle": None,
        "couch_angle": None,
        "beam_dose_gy": beam_dose,
        "beam_meterset_mu": meterset,
    }
    if first_control_point is not None:
        entry["nominal_energy"] = number(first_control_point.get("NominalBeamEnergy"))
        entry["gantry_angle_start"] = number(first_control_point.get("GantryAngle"))
        entry["gantry_rotation_direction"] = code(
            first_control_point.get("GantryRotationDirection"), ROTATION_DIRECTIONS
        )
        entry["collimator_angle"] = number(first_control_point.get("BeamLimitingDeviceAngle"))
        entry["couch_angle"] = number(first_control_point.get("PatientSupportAngle"))
    return entry


def rt_plan_summary(config: Config, path: str) -> dict[str, Any]:
    """Summarise an RTPLAN: intent, approval status, fractions, beams and prescription doses.

    Beam dose and meterset come from the first fraction group (per fraction). ``nominal_energy``
    is in MV for photons and MeV for electrons, as stored in the first control point.
    """
    file = prepare_rt_file(config, path)
    header = read_header(file)
    try:
        if str(header.get("Modality", "")).strip().upper() != "RTPLAN":
            raise NotRtPlanError()

        fraction_groups = header.get("FractionGroupSequence") or []
        fractions_planned = None
        fraction_values: dict[int, tuple[float | None, float | None]] = {}
        if len(fraction_groups) > 0:
            first_group = fraction_groups[0]
            fractions_planned = _integer(first_group.get("NumberOfFractionsPlanned"))
            for reference in first_group.get("ReferencedBeamSequence") or []:
                beam_number = _integer(reference.get("ReferencedBeamNumber"))
                if beam_number is not None:
                    fraction_values[beam_number] = (
                        number(reference.get("BeamDose")),
                        number(reference.get("BeamMeterset")),
                    )

        beam_sequence = header.get("BeamSequence") or []
        beams = [_beam_entry(beam, fraction_values) for beam in islice(beam_sequence, MAX_BEAMS)]
        by_radiation: dict[str, int] = {}
        for beam in beams:
            key = beam["radiation_type"] or "UNKNOWN"
            by_radiation[key] = by_radiation.get(key, 0) + 1

        prescriptions: list[dict[str, Any]] = []
        for reference in islice(header.get("DoseReferenceSequence") or [], MAX_DOSE_REFERENCES):
            prescriptions.append(
                {
                    "reference_type": code(
                        reference.get("DoseReferenceType"), DOSE_REFERENCE_TYPES
                    ),
                    "target_prescription_dose_gy": number(reference.get("TargetPrescriptionDose")),
                    "target_minimum_dose_gy": number(reference.get("TargetMinimumDose")),
                    "target_maximum_dose_gy": number(reference.get("TargetMaximumDose")),
                    "organ_at_risk_maximum_dose_gy": number(
                        reference.get("OrganAtRiskMaximumDose")
                    ),
                }
            )
    except RtImagingMcpError:
        raise
    except Exception:
        raise NotRtPlanError() from None

    return {
        "plan_geometry": code(header.get("RTPlanGeometry"), PLAN_GEOMETRIES),
        "approval_status": code(header.get("ApprovalStatus"), APPROVAL_STATUSES),
        "plan_intent": code(header.get("PlanIntent"), PLAN_INTENTS),
        "fraction_group_count": len(fraction_groups),
        "fractions_planned": fractions_planned,
        "beam_count": len(beam_sequence),
        "counts_by_radiation_type": dict(sorted(by_radiation.items())),
        "beams": beams,
        "beams_truncated": len(beam_sequence) > MAX_BEAMS,
        "dose_references": prescriptions,
    }
