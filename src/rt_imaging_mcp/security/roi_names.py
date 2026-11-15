"""Structure (ROI) name standardisation (rule R10).

ROI names in RT structure sets are free text and can contain identifiers
(for example ``PTV_Budi``). A name is returned only when it matches a standard
name or a target-volume pattern built from fixed tokens, or when the operator
explicitly enabled it. Everything else is reported as redacted.

The standard list is a subset inspired by AAPM TG-263 naming. It is not the
official or complete list.
"""

from __future__ import annotations

import re

MAX_NAME_LENGTH = 64

STANDARD_ROI_NAMES: frozenset[str] = frozenset(
    {
        # Body and equipment
        "BODY",
        "External",
        "Skin",
        "Couch",
        "CouchSurface",
        "CouchInterior",
        # Head and neck
        "Brain",
        "Brainstem",
        "Cochlea_L",
        "Cochlea_R",
        "Esophagus",
        "Eye_L",
        "Eye_R",
        "Larynx",
        "Lens_L",
        "Lens_R",
        "Lips",
        "Mandible",
        "OpticChiasm",
        "OpticNrv_L",
        "OpticNrv_R",
        "Oral_Cavity",
        "Parotid_L",
        "Parotid_R",
        "Pituitary",
        "SpinalCanal",
        "SpinalCord",
        "Submandib_L",
        "Submandib_R",
        "Thyroid",
        "Trachea",
        "BrachialPlex_L",
        "BrachialPlex_R",
        # Thorax
        "Breast_L",
        "Breast_R",
        "Heart",
        "Lung_L",
        "Lung_R",
        "Lungs",
        # Abdomen and pelvis
        "Bladder",
        "Bowel",
        "Bowel_Bag",
        "Bowel_Large",
        "Bowel_Small",
        "Canal_Anal",
        "Cervix",
        "Colon",
        "Duodenum",
        "Femur_Head_L",
        "Femur_Head_R",
        "Femur_L",
        "Femur_R",
        "Gallbladder",
        "Kidney_L",
        "Kidney_R",
        "Kidneys",
        "Liver",
        "Ovary_L",
        "Ovary_R",
        "Pancreas",
        "Penile_Bulb",
        "Prostate",
        "Rectum",
        "Spleen",
        "Stomach",
        "Uterus",
        "Vagina",
    }
)

_CANONICAL: dict[str, str] = {name.casefold(): name for name in STANDARD_ROI_NAMES}

# Target volumes: GTV, CTV, ITV, PTV with an optional p/n subtype, a short index and
# suffix tokens such as _High, _Mid, _Low, _Boost, _5000 or _50Gy.
_TARGET = re.compile(
    r"(?P<base>gtv|ctv|itv|ptv)(?P<sub>[pn]?)(?P<index>\d{0,2})(?P<rest>(?:_[A-Za-z0-9.]{1,12})*)",
    re.IGNORECASE,
)
_LEVEL_TOKENS = {"high": "High", "mid": "Mid", "low": "Low", "boost": "Boost"}
_DOSE_TOKEN = re.compile(r"(?P<number>\d{1,5}(?:\.\d{1,2})?)(?P<unit>cgy|gy)?", re.IGNORECASE)
_UNITS = {"cgy": "cGy", "gy": "Gy"}


def normalize(name: str) -> str:
    """Trim and replace runs of spaces, tabs and hyphens with one underscore."""
    return re.sub(r"[\s\-]+", "_", name.strip())


def _canonical_suffix_token(token: str) -> str | None:
    level = _LEVEL_TOKENS.get(token.casefold())
    if level is not None:
        return level
    match = _DOSE_TOKEN.fullmatch(token)
    if match is None:
        return None
    unit = match.group("unit")
    return match.group("number") + (_UNITS[unit.casefold()] if unit else "")


def _standard_target_name(normalized: str) -> str | None:
    match = _TARGET.fullmatch(normalized)
    if match is None:
        return None
    suffix = ""
    for token in [part for part in match.group("rest").split("_") if part]:
        canonical = _canonical_suffix_token(token)
        if canonical is None:
            return None
        suffix += "_" + canonical
    return match.group("base").upper() + match.group("sub").lower() + match.group("index") + suffix


def standardize_roi_name(name: object, extra_names: frozenset[str] = frozenset()) -> str | None:
    """Return a safe canonical name, or ``None`` when the name must be redacted.

    The returned text is built from the standard list, fixed target tokens or the operator's
    own spelling. It is never a copy of arbitrary input text.
    """
    if not isinstance(name, str):
        return None
    normalized = normalize(name)
    if not normalized or len(normalized) > MAX_NAME_LENGTH:
        return None

    standard = _CANONICAL.get(normalized.casefold())
    if standard is not None:
        return standard
    target = _standard_target_name(normalized)
    if target is not None:
        return target

    operator_names = {normalize(extra).casefold(): normalize(extra) for extra in extra_names}
    return operator_names.get(normalized.casefold())
