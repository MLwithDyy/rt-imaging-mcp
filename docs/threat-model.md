# Threat Model

Status: draft v0.1. Every rule in "Hard rules" must be enforced in code and covered by an automated test
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

## 6. Acknowledged limits

These belong in the README and must not be hidden:

- The allowlist reduces risk. It does not guarantee anonymity. Data should be de-identified before use.
- Folder and file names are controlled by the user and may contain identifiers (R4 reduces, not removes, this).
- Prompt injection through file content cannot be fully prevented by the server (R5).
- Radiomics features derived from images can carry information about a patient and are returned as is.
- For full privacy, use a locally hosted model so that no tool output leaves the machine.
- This project is for research and education only. It is not a medical device.

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

## 8. Review

Revisit this document whenever a new tool is added, a new file format is supported, or the output of an
existing tool changes. Record changes in the commit message and in this file's status line.
