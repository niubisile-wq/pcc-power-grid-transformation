# Proof-Carrying Canonicalization for Power-Grid Model Transformation

Research code for the manuscript **“Identity Preservation in Power-Grid Model
Transformation: Proof-Carrying Canonicalization for N–1 Contingency Analysis
and AC Optimal Power Flow.”**

The repository implements a task-bound proof-carrying canonicalization (PCC)
contract and the controlled experiments used to study identity loss across
power-grid transformations. It also contains the source code for the CGMES
interoperability audit described in the manuscript.

## Repository layout

- `pcc/`: reference PCC contract and signed canonicalizer.
- `protocols/`: frozen benchmark protocols for the main experiments.
- `experiments/`: semantic-gate, mutation, N–1, AC-OPF, model-interface,
  boundary, replay, serialization, and performance audits.
- `cgmes/`: adapters, validation workers, analysis scripts, corpus registries,
  protocols, and tests for the CGMES interoperability audit.

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

This code release intentionally excludes raw public datasets, third-party model
weights, virtual environments, logs, generated result tables, figures, and the
manuscript files. Corpus registries and hashes are included so that acquired
inputs can be checked against the study records.

The remaining CGMES tests are evidence-integrity checks and therefore expect
the downloaded corpus and generated result tables to have been rebuilt first.

## Author

Zixuan Liu, Detroit Green Technology Institute, Hubei University of Technology.

## License

No open-source license has yet been assigned. Copyright remains with the author.
