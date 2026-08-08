# EPSR finalization status

Date: 2026-08-07

## Current state

The scientific evidence package is complete under the local fail-closed gates.
The final Elsevier submission package is not complete because author-supplied
metadata/declarations and the immutable archive release DOI/tag still require
external confirmation.

## Verified ready items

- Evidence dashboard: `outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json`
  reports `ready_gates = 9`, `total_gates = 9`, and `submission_ready = true`.
- Clean-room audit: `outputs/epsr_clean_room_audit/audit_summary.json` reports
  `status = pass`.
- Manuscript draft: `manuscript/EPSR_MANUSCRIPT_DRAFT.md`.
- Supplementary information: `manuscript/EPSR_SUPPLEMENTARY_INFORMATION.md`.
- Main figures: five complete PDF/SVG/PNG triplets under `manuscript/figures/`.
- Figure legends and source manifest are present.
- Submission manifest: `outputs/epsr_submission_manifest/submission_manifest.json`
  reports `scientific_package_ready = true` and `figures_ready = true`.

## Archive candidate

- Candidate archive:
  `outputs/epsr_final_archive_candidate/epsr_pcc_v2_archive_candidate_20260807.zip`
- Candidate manifest:
  `outputs/epsr_final_archive_candidate/archive_candidate_manifest.json`
- Candidate checksum:
  `outputs/epsr_final_archive_candidate/epsr_pcc_v2_archive_candidate_20260807.zip.sha256`
- SHA-256:
  `c2e8a5e6b839edb662e58be4b63e6b6006679fe1cb4db225615f29e7dd387ea1`

This archive is a pre-release candidate. It must not be described as the final
immutable release until the author metadata/declaration form is completed and
the DOI-bound archive release has been minted.

## Remaining external inputs

Complete `manuscript/EPSR_AUTHOR_METADATA_TEMPLATE.json`, then run
`experiments/apply_epsr_author_metadata.py` to regenerate
`manuscript/EPSR_AUTHOR_INPUT_FORM.md`:

Alternatively, fill
`outputs/epsr_author_metadata/author_response_form.md`, then import the
non-empty answers into the JSON template with:

```powershell
py -3.12 experiments\import_epsr_author_response.py --apply
```

- Corresponding author email.
- Full affiliation postal address.
- Confirmed author order, spelling, corresponding author, and ORCID.
- Confirmed CRediT roles.
- Funding statement.
- Competing interests statement.
- Acknowledgements.
- Generative AI disclosure, if required by the journal policy.
- All-author approval and confirmation that the work is not under review
  elsewhere.
- Final release DOI and release tag.
- Code and source-data license confirmations.
- Confirmation that third-party datasets are referenced rather than relicensed.

For the generative-AI line, use the current Elsevier journal policy as the
source of truth. The policy page checked on 2026-08-07 says authors should
disclose generative AI tools used for manuscript preparation in a separate AI
declaration statement, while basic spelling, grammar, and punctuation checks do
not require a declaration:
`https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals`.

## Final gate interpretation

`outputs/epsr_submission_manifest/submission_manifest.json` is authoritative:

- `scientific_package_ready = true`
- `figures_ready = true`
- `author_metadata_ready = false`
- `final_archive_ready = false`
- `submission_package_ready = false`

After the external inputs are filled, rebuild the submission manifest and only
then freeze the final archive/release package.

## Machine checks to rerun

```powershell
py -3.12 experiments\validate_epsr_author_metadata.py
py -3.12 experiments\import_epsr_author_response.py
py -3.12 experiments\apply_epsr_author_metadata.py
py -3.12 experiments\build_epsr_submission_manifest.py
py -3.12 experiments\build_epsr_final_archive_candidate.py
py -3.12 experiments\validate_epsr_final_readiness.py
```

The one-command ordered entry point is:

```powershell
py -3.12 experiments\freeze_epsr_submission_package.py
```

The final readiness validator writes
`outputs/epsr_final_readiness/final_readiness.json`. It must report
`final_ready = true` before the archive candidate is promoted to a final release.
The author metadata validator writes
`outputs/epsr_author_metadata/author_metadata_validation.json`; it must report
`valid = true` before the author form can be regenerated.
