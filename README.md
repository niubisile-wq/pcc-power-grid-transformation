# Task-Semantic Proof-Carrying Validation for Power-Grid Model Transformation

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21796488.svg)](https://doi.org/10.5281/zenodo.21796488)

Research code and evidence package for the manuscript *Task-semantic
proof-carrying validation prevents unsafe execution of transformed power-system
models.*

The repository implements a task-bound proof-carrying contract (PCC), a
fail-closed solver gate, and the controlled experiments used to study semantic
loss across power-grid transformations. It also contains the CGMES structural
and task-semantic validation evidence reported in the manuscript.

## What this repository is for

- Reproducing the main claims, tables, and figures in the EPSR submission.
- Providing a reviewer-facing evidence bundle with the scripts that generate
  the reported statistics.
- Keeping the manuscript source, bibliography, and frozen protocols in one
  place.

## What is intentionally not included

- Local virtual environments such as `.venv_pcc_v2/` and `.venv_pypowsybl/`.
- Transient caches such as `.pytest_cache/` and `tmp/`.
- Regenerable output directories such as `outputs/`.
- Private checkpoints or external research assets that cannot be redistributed.

## Repository layout

- `pcc/`: reference PCC contract and signed canonicalizer.
- `protocols/`: frozen benchmark protocols for the main experiments.
- `experiments/`: semantic-gate, mutation, N-1, AC-OPF, model-interface,
  boundary, replay, serialization, and performance audits.
- `cgmes/`: adapters, validation workers, analysis scripts, corpus registries,
  protocols, and tests for the CGMES interoperability audit.
- `manuscript/`: LaTeX manuscript source, bibliography, submission checklist,
  and author-facing submission notes.

## Environment

Python 3.12 was used for the reported Windows runs. A practical base
environment can be installed with:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

The complete package snapshot used for the CGMES audit is retained in
`cgmes/requirements-lock.txt`. Some model-facing experiments additionally
require their upstream research repositories or checkpoints; those assets are
not redistributed here.

## Running the core checks

From the repository root, expose the two source directories on `PYTHONPATH`.
These are the quickest reviewer checks for the core contract and CGMES mapping
logic.

PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\pcc;$PWD\experiments"
python experiments/run_protocol_audit.py
python experiments/run_protocol_combo_attack_v3.py
python experiments/run_nminus1_risk_ranking_extended.py
python experiments/run_opf_heterogeneous_policy_audit.py
python -m unittest discover -s cgmes/tests -p "test_pcc_contract.py" -v
python -m unittest discover -s cgmes/tests -p "test_full_mapping.py" -v
```

Bash:

```bash
export PYTHONPATH="$PWD/pcc:$PWD/experiments"
python experiments/run_protocol_audit.py
python experiments/run_protocol_combo_attack_v3.py
python experiments/run_nminus1_risk_ranking_extended.py
python experiments/run_opf_heterogeneous_policy_audit.py
python -m unittest discover -s cgmes/tests -p "test_pcc_contract.py" -v
python -m unittest discover -s cgmes/tests -p "test_full_mapping.py" -v
```

Individual scripts document their inputs and write locations. Several public
network experiments download data through the corresponding upstream packages
or APIs. The CGMES corpus builders use the official ENTSO-E resources recorded
in `cgmes/corpus/official_cgmes_corpus_manifest.json`.

## Data and generated artifacts

Third-party public datasets are not relicensed; their source records and hashes
are retained in the corpus manifests. The working repository includes generated
machine summaries, manuscript tables, audit logs, and manuscript source. A
final archive release will freeze the submission figures and source-data bundle.

The remaining CGMES tests are evidence-integrity checks and therefore expect
the downloaded corpus and generated result tables to have been rebuilt first.

## Reproducibility checklist

For a fresh machine, a reviewer can use this order:

1. Create a Python 3.12 environment and install `requirements.txt`.
2. Run the core contract and mapping tests from the repository root.
3. Rebuild the EPSR evidence dashboard and manuscript tables:

```powershell
$env:PYTHONPATH=(Resolve-Path cgmes).Path
py -3.12 experiments/run_dc_scopf_confirmatory_statistics.py
py -3.12 experiments/build_epsr_evidence_dashboard.py
py -3.12 experiments/build_epsr_manuscript_tables.py
py -3.12 experiments/build_epsr_submission_manifest.py
```

4. Compile the manuscript in `manuscript/` with `pdflatex` and `bibtex`.

If you only want to inspect the submission logic, start with the scripts above
and the manuscript source in `manuscript/EPSR_template.tex`.

## PCC v2 task-semantic gate

The PCC v2 implementation adds a three-state task contract (`accept`, `reject`,
`unresolved`), proof-guided repair, and a runtime gate which binds verification
and solver execution to hashed inputs and an execution receipt.

Run the focused regression suite:

```powershell
$env:PYTHONPATH=(Resolve-Path cgmes).Path
py -3.12 -m unittest cgmes.tests.test_pcc_v2 -v
```

Run the frozen 22-network semantic matrix:

```powershell
py -3.12 experiments/run_pcc_v2_attack_matrix.py
```

The native PyPSA/HiGHS DC-SCOPF experiment uses the isolated dependencies in
`requirements-pcc-v2.txt`. Pilot and confirmatory runs use distinct filenames;
the exhaustive confirmatory mode is `--candidate-mode all`.

## EPSR evidence package

The submission-oriented evidence chain is machine checked. The semantic
confirmatory corpus is protected by
`protocols/semantic_confirmatory_lock_v2.json`. After the frozen five-network
by ten-state DC-SCOPF campaign is complete, build its statistics, dashboard,
and manuscript tables with:

```powershell
$env:PYTHONPATH=(Resolve-Path cgmes).Path
py -3.12 experiments/run_dc_scopf_confirmatory_statistics.py
py -3.12 experiments/build_epsr_evidence_dashboard.py
py -3.12 experiments/build_epsr_manuscript_tables.py
py -3.12 experiments/manage_dc_scopf_confirmatory_lock_v2.py --create
powershell -ExecutionPolicy Bypass -File experiments/run_epsr_evidence_audit.ps1 -RequireSubmissionReady
py -3.12 experiments/build_epsr_submission_manifest.py
```

The last command fails closed unless all nine evidence families pass. It
rebuilds deterministic statistical summaries and tables, executes the
regression suite, and verifies the content-addressed confirmatory locks. The
machine-readable decision is written to
`outputs/epsr_evidence_dashboard/epsr_evidence_dashboard.json`.
The submission-manifest command intentionally exits nonzero until the five
figure triplets, figure source manifest, author declarations, and final archive
version are present.

Standards claims are intentionally separated: APL 1.1.1 SHACL results, the
locally implemented QoCDC 4.1.4 Level 1-4 subset, PCC task-semantic decisions,
and native PowSyBl import results are reported as distinct evidence families.

## Current evidence status

The frozen campaign covers 22 semantic-benchmark networks, 56 AC N-1 attempts,
35 AC-OPF attempts, and 50 DC-SCOPF operating states comprising 12,340
candidate-outage rows. All nine submission evidence families currently pass.
The authoritative status is the machine-readable dashboard, and the clean-room
audit must pass before any result is promoted into the manuscript.

## Author

Zixuan Liu, Detroit Green Technology Institute, Hubei University of Technology.
Wei Xiong, School of Electrical and Electronic Engineering, Hubei University of Technology; Department of Computer Science and Engineering, University of South Carolina.

## Citation

Please cite the archived release used in the manuscript:

> Liu, Z. & Xiong, W. (2026). *Proof-Carrying Contracts for Task-Safe Power-System
> Model Transformation* (v1.0.0) [Software]. Zenodo.
> https://doi.org/10.5281/zenodo.21796488

Machine-readable citation metadata are provided in `CITATION.cff`.

## License

No open-source license has yet been assigned. Copyright remains with the authors.
