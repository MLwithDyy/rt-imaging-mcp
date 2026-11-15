# Threat Model

Status: draft v0.4 (rules R1-R11 implemented and tested for the first six tools; CI added). Every rule in "Hard rules" must be enforced in code and covered by an automated test
before the tool that depends on it is merged.

## 1. Purpose and scope

`rt-imaging-mcp` is a local MCP server that lets an AI agent inspect medical image files
(DICOM, NIfTI) and radiotherapy objects (RTSTRUCT, RTDOSE, RTPLAN) on the user's own disk.

In scope:
- Reading files below one configured root directory.
- Returning structured, minimal summaries to the MCP client.

Out of scope:
- Clinical use or any medical decision making.
- Network access to PACS or other DICOM servers.
- Writing, deleting, moving or sending files.
- Network authentication (the default and supported transport is stdio).
- Regulatory compliance (HIPAA, GDPR and similar). This project does not make a deployment compliant.

## 2. The core problem

Running the server locally protects the raw files. It does **not** protect what the tools return.
Tool output is placed into the context of the language model used by the MCP client. If that model is
hosted in the cloud, every tool result is transmitted to that provider.

Therefore the security boundary of this project is **the tool output**, not the file system.

## 3. Assets

| Asset | Why it matters |
|---|---|
| Patient identity (direct identifiers: name, ID, birth date, address) | Privacy of individuals |
| Indirect identifiers (dates, UIDs, device serial numbers, free-text descriptions, institution) | Can re-identify a person when combined with other data |
| Pixel data | May contain burned-in annotations (names, IDs) that cannot be reliably filtered |
| Local directory structure and absolute paths | Folder names often contain patient names or hospital identifiers |
| Files outside the configured root | Unrelated sensitive data on the user's machine |

## 4. Actors and threats

| ID | Threat | Example |
|---|---|---|
| T1 | Identifier leakage through tool output | `get_metadata` returns `PatientName` to a cloud model |
| T2 | Indirect re-identification | Study dates, UIDs or `SeriesDescription` containing a name are returned |
| T3 | Path traversal | The agent requests `../../home/user/.ssh/id_rsa` or follows a symlink out of the root |
| T4 | Path disclosure | Output contains `/home/alice/Budi_Santoso_CT_2024/` |
| T5 | Prompt injection through file content | A free-text DICOM field contains instructions aimed at the agent |
| T6 | Data leakage through error messages | An exception message quotes a tag value |
| T7 | Resource exhaustion | Scanning a huge directory or loading a very large volume into memory |
| T8 | Accidental commit of patient data | A `.dcm` file enters the git history of a public repository |
| T9 | Identifier leakage through structure names | An RTSTRUCT ROI is named `PTV_Budi` or `Kasus 12 Bu Siti` |
| T10 | Free text or identifiers in RT dose and plan objects | A beam is named `Boost Bu Siti`, a plan label contains a name, a referenced UID links records |

## 5. Hard rules

### R1. Tag allowlist, never a denylist
Only DICOM attributes on an explicit allowlist are returned. Unknown attributes and all private tags
are rejected by default. A denylist fails silently whenever a tag is forgotten.

Default allowlist (technical attributes), by keyword:

`Modality`, `Rows`, `Columns`, `NumberOfFrames`, `BitsAllocated`, `BitsStored`, `PixelRepresentation`,
`PhotometricInterpretation`, `PixelSpacing`, `SliceThickness`, `SpacingBetweenSlices`,
`ImageOrientationPatient`, `ImagePositionPatient`, `SOPClassUID` (class only, not instance UIDs),
`TransferSyntaxUID`, `RescaleSlope`, `RescaleIntercept`.

Disabled by default (opt-in by the user, with a documented warning): study and series dates and times,
`StudyDescription`, `SeriesDescription`, `ProtocolName`, instance-level UIDs, `Manufacturer`, `ManufacturerModelName`.
These can carry indirect identifiers or free text.

Always blocked, no opt-in: patient name, patient ID, birth date, sex and age, address and phone,
institution and department, physician and operator names, accession number, device serial number,
any private tag, any tag in the DICOM "Basic Application Level Confidentiality Profile" identifier list that
is not on the allowlist above.

*Covers T1, T2.*

### R2. Pixel data is never returned
Tools return only derived summaries (shape, spacing, orientation, intensity statistics, counts).
No raw pixel arrays, no rendered images, no thumbnails.
Reason: burned-in annotations cannot be reliably detected and removed automatically.

*Covers T1.*

### R3. Safe path handling
- One root directory is configured at startup. There is no default root, and the server refuses to start without one.
- Every path argument is resolved with `Path.resolve()` and must remain inside the resolved root.
- `..` segments are rejected. Symlinks that resolve outside the root are rejected.
- Only regular files and directories are accepted (no devices, sockets, FIFOs).

*Covers T3.*

### R4. Output paths are relative to the root
Tools never return absolute paths. Directory or file names are still returned relative to the root,
so the user is responsible for keeping identifying names out of the tree. Tools offer an option to
return opaque indices (`series_001`) instead of names.

*Covers T4.*

### R5. File content is data, never instructions
All text originating from files is returned only inside structured fields, never concatenated into
instructions or tool descriptions. Free-text fields are off by default (see R1). The README documents
that prompt injection through file content is possible and cannot be fully prevented by this server.

*Covers T5.*

### R6. Errors do not echo data
Error messages state what went wrong (for example "tag not allowed", "path outside root", "file is not DICOM")
and never quote values read from files.

*Covers T6.*

### R7. Read-only
No tool writes, deletes, moves, renames or sends files. No network calls are made by the server.

### R8. Bounded work
Every tool has limits: maximum files per scan, maximum directory depth, maximum file size, and a timeout.
Limits are configurable and have conservative defaults.

*Covers T7.*

### R9. No patient data in the repository
- `.gitignore` blocks common medical image extensions and data folders.
- A pre-commit hook (`scripts/check_no_medical_images.py`) rejects files with medical image extensions
  and files containing the DICOM magic bytes, even without an extension.
- Tests generate synthetic data at run time. Test data is never stored in the repository.
- Contributors must never attach real patient data to issues or pull requests.

*Covers T8.*

### R10. Structure names are standardised or redacted
ROI names in RT structure sets are free text. A name is returned only when it matches the built-in standard list
(a subset inspired by AAPM TG-263, not the official list), matches a target-volume pattern built from fixed tokens
(`GTV`, `CTV`, `ITV`, `PTV` with optional `p`/`n`, a short index and suffixes such as `_High` or `_5000`), or was
enabled by the human operator with `--enable-roi-name`. Everything else is reported as `name: null`.
Returned names are canonical spellings, never a copy of arbitrary input. The interpreted type is returned only
when it is one of the DICOM enumerated code strings. Structure set labels, observation labels, ROI descriptions
and absolute contour coordinates are never returned.

*Covers T9.*

### R11. RT dose and plan output is numbers and enumerated codes only
`rt_dose_summary` and `rt_plan_summary` return numbers (sizes, spacings, doses, angles, energies, counts) and DICOM
enumerated code strings that appear on a fixed allowlist (for example `GY`, `PHYSICAL`, `PHOTON`, `APPROVED`). A code
string that is not on the allowlist is returned as `null`, so free text hidden in a code field is never echoed. Plan
and beam labels, names and descriptions, machine and institution names, reviewer names, dose reference descriptions,
referenced UIDs and the position of the dose grid in patient space are never returned. The dose array is read to compute
statistics (maximum, mean, non-zero count) but is never returned.

*Covers T10.*

## 6. Acknowledged limits

These belong in the README and must not be hidden:

- The allowlist reduces risk. It does not guarantee anonymity. Data should be de-identified before use.
- Folder and file names are controlled by the user and may contain identifiers (R4 reduces, not removes, this).
- Prompt injection through file content cannot be fully prevented by the server (R5).
- Radiomics features derived from images can carry information about a patient and are returned as is.
- For full privacy, use a locally hosted model so that no tool output leaves the machine.
- This project is for research and education only. It is not a medical device.
- Path checks resolve a path and then use it. A symlink swapped in between the check and the read (time-of-check
  to time-of-use race) is not prevented. Run the server on a directory that untrusted parties cannot modify.
- Tool results never contain data from files in error messages (R6), but logs written to stderr by the server
  process or the MCP client are outside the tool output. Do not assume those logs are free of file content.
- `dicom_scan_directory` returns folder and file names relative to the root by default. Use `opaque_paths=true`
  to omit them. Folder names are chosen by the user and may contain identifiers.
- Planar-contour volumes in `rt_structure_summary` are approximations (net slice area times median slice spacing,
  nested contours treated as holes). They are not clinical volumes and are not validated against a treatment
  planning system.
- The standard structure-name list is a partial, hand-written subset. Valid structure names that are not on it
  (for example in Indonesian) are redacted until the operator enables them.
- `rt_dose_summary` statistics cover the whole dose grid, which usually includes voxels outside the patient. They are
  not structure doses. The dose array is loaded into memory (bounded by the RT file size limit of 256 MiB) and only
  uncompressed pixel data is supported.
- `rt_plan_summary` reports what the plan file states and does not infer a treatment technique.
- Numbers can still carry information (for example a very specific beam meterset). They are not treated as identifiers.
- Only DICOM Part 10 files (with the "DICM" preamble and a transfer syntax in the file meta) are recognised.
  Older files without a preamble are reported as non-DICOM.

## 7. Test mapping

Each rule maps to at least one automated test. A tool is not merged without its security tests.

| Rule | Test idea |
|---|---|
| R1 | A synthetic file containing `PatientName`, `PatientID` and a private tag never shows them in output, in any tool |
| R1 | A tag outside the allowlist is rejected, including after a library upgrade adds new attributes |
| R2 | No tool output contains pixel arrays; response size stays below a fixed bound |
| R3 | `../`, absolute paths outside the root, and symlinks pointing outside the root are all rejected |
| R4 | Output never contains the root path or any absolute path |
| R6 | Triggering errors with identifying tag values never leaks those values in the message |
| R7 | Static check that the codebase imports no write/network APIs in the server package |
| R8 | A directory exceeding the limits returns a bounded, truncated result with a clear flag |
| R9 | The pre-commit script blocks a synthetic DICOM file with no extension |
| R10 | Names with extra text (`PTV_Budi`) are redacted; returned names never echo raw input; operator-enabled names pass |
| R11 | Plan and dose files full of fake free text produce output without any of it; unknown code strings become `null`; a guard test proves the fake values are really written to the files |

## 8. Review

Revisit this document whenever a new tool is added, a new file format is supported, or the output of an
existing tool changes. Record changes in the commit message and in this file's status line.

## 9. Implementation status

| Rule | Enforced in | Tests |
|---|---|---|
| R1 | `security/allowlist.py`, `config.py` | `test_security_allowlist.py`, `test_dicom_tools.py`, `test_server.py` |
| R2 | tools never read pixel data or NIfTI arrays | `test_security_allowlist.py`, `test_nifti_tools.py`, `test_server.py` |
| R3 | `security/paths.py`, `config.py` | `test_security_paths.py`, `test_config.py` |
| R4 | `security/paths.py`, `tools/dicom.py` | `test_security_paths.py`, `test_dicom_tools.py`, `test_server.py` |
| R5 | free-text fields off by default (R1); documented limit | `test_security_allowlist.py`, `test_nifti_tools.py` |
| R6 | `security/errors.py`, `server.py` | `test_server.py`, `test_nifti_tools.py`, `test_security_paths.py` |
| R7 | read-only tools; tripwire on source | `test_static_rules.py`, `test_server.py` |
| R8 | `config.py`, `security/paths.py` | `test_security_paths.py`, `test_dicom_tools.py` |
| R9 | `.gitignore`, `scripts/check_no_medical_images.py`, CI step on tracked files | `test_precommit_guard.py` |
| R10 | `security/roi_names.py`, `tools/rt.py` | `test_roi_names.py`, `test_rt_tools.py`, `test_server.py` |
| R11 | `tools/rt_common.py`, `tools/rt_dose.py`, `tools/rt_plan.py` | `test_rt_dose_plan.py`, `test_synthetic.py`, `test_server.py` |

The guard script is tested directly. CI also runs it over every tracked file, so a commit made with `--no-verify` is still caught after the push (the data would already be in the history, so the hook remains the primary defence).
