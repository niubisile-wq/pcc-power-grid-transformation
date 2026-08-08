# EPSR competitive landscape and experimental bar

Date: 2026-08-07  
Target: *Electric Power Systems Research* (EPSR)  
Working paper position: proof-carrying power-grid model transformation for preventing semantically unsafe downstream security assessment and optimization.

## 1. Executive conclusion

The strongest defensible paper is not another CGMES converter and not a post-hoc failure audit. It is an operational-safety paper with the following causal chain:

1. A grid-model transformation can remain syntactically valid while silently changing task-relevant semantics.
2. Existing artifact-, identity-, footprint-, and invariant-level checks leave measurable unsafe acceptance gaps.
3. PCC attaches a task-specific proof obligation to the transformed artifact and fails closed before the solver starts.
4. Across multiple networks and downstream tasks, PCC eliminates observed harmful solver starts while retaining every lawful transformation.
5. The prevented errors have operational consequences: contingency overload underestimation and materially changed OPF cost/feasibility.

This framing fits EPSR's stated emphasis on applied power-system research, new procedures, security assessment, and optimization. The manuscript must avoid claiming universal CGMES conformance, universal solver independence, or proof of real-world blackout prevention. It may claim complete prevention in the preregistered tested scope, with exact denominators and confidence bounds.

## 2. Search method and limitations

The investigation used title/abstract/DOI searches across publisher pages, official documentation, arXiv, OSTI mirrors of author manuscripts, and journal pages. The intended Crossref/PubMed preflight timed out and OpenAlex returned HTTP 429, so bibliographic discovery was completed through primary publisher, repository, and project sources. Results below are therefore a targeted competitive reconnaissance, not a claim of exhaustive systematic-review coverage.

Search concepts included combinations of:

- CGMES/CIM conversion, validation, interoperability, ontology, and model transformation;
- security-constrained OPF/economic dispatch, contingency screening, decomposition, and learning proxies;
- cyber-physical attacks on contingency analysis;
- semantics preservation and proof obligations in model transformation;
- multi-network benchmarks, solver reproducibility, and uncertainty-aware SCOPF.

## 3. Same-field experimental benchmark

| Research line | Representative evidence | Typical experimental level | What it means for this paper |
|---|---|---|---|
| CGMES-to-operational-model conversion | Memari and Aljamous (2023), model-driven CGMES conversion using ontology validation/inference, Neo4j and pandapower, including large real-world grids | End-to-end conversion architecture, standards-aware validation, real-network demonstration | PCC must be distinguished from conversion: its novelty is task-semantic proof and fail-closed control of solver execution |
| ML-assisted N-k SCOPF | EPSR (2024), constraint-driven deep learning on IEEE 39- and 118-bus systems, reporting feasibility/quality and up to 173x acceleration | Two canonical systems; operational feasibility, cost/error, and speed | A strong EPSR paper can succeed with a few canonical systems when consequence and comparative metrics are sharp; our 22-network semantic campaign provides breadth, but must still show operational effect |
| Large-scale SCED proxy learning | Chen et al., EPSR 2022, optimization proxies for large-scale SCED | Large-system scalability plus optimality/feasibility comparison | Report both safety and overhead; do not present validation accuracy alone |
| Scalable exact SCOPF | Decomposition/screening studies on large networks; recent nonlinear multi-period SCOPF | Multiple test systems, convergence/optimality, runtime, contingency scale | The paper needs a scaling curve and explicit completed/failed denominator, not only aggregate success |
| Probabilistic/chance-constrained SCOPF | Preventive and chance-constrained SCOPF studies using IEEE 118-bus and European data | Reliability guarantee or violation probability under uncertainty | PCC's guarantee is conditional on declared proof obligations and tested mutation model; state that boundary clearly |
| Adversarial contingency analysis | SEGAN 2024 formal analytics of stealthy attacks against contingency analysis; TPWRS 2025 bilevel N-k adversarial robustness | Attack success/impact and defensive robustness | Consequence-based adversarial mutations are a strong adjacent comparison; PCC differs by guarding transformation semantics before computation |
| Formal semantics preservation | Formal model-transformation research | Preservation properties, proof structure, often without power-system consequences | PCC must connect formal preservation to actual N-1/OPF outcomes, which is the interdisciplinary contribution |
| Reproducible OPF tooling | PowerModels.jl official formulations and benchmark tooling | Independent implementation/formulation and open cases | A second stack is necessary to show the key observation is not a PYPOWER/PyPSA artifact |

## 4. Frontier directions to learn from

### 4.1 Scale and decomposition

Frontier SCOPF research is moving toward large contingency sets, decomposition, screening, and parallel solution. For this manuscript, scale is not merely network bus count: report network size, candidate-contingency count, state count, completed denominator, failed states, wall time, and peak memory. The case300/case500 campaign is therefore a core result rather than supplementary decoration.

### 4.2 Learned optimization proxies with feasibility safeguards

Recent EPSR work emphasizes large speedups while preserving feasibility and near-optimal cost. PCC should not compete as a faster optimizer. It should be positioned as a composable safety gate that can protect classical or learned downstream solvers. The empirical analogue is: lawful transformations pass, unsafe ones are stopped, and gate latency is small relative to the downstream computation.

### 4.3 Uncertainty-aware security guarantees

Chance-constrained and probabilistic SCOPF papers make their guarantee domain explicit. PCC must do the same: the guarantee applies to declared task semantics, proof schema, mutation family, and frozen implementation. Claims outside that domain become future work, not implied coverage.

### 4.4 Adversarially chosen operational consequences

The leading security literature evaluates attacks by their physical or economic effect rather than malformed-data counts. Our N-1 and OPF experiments follow this stronger standard by quantifying overload underestimation, feasibility changes, and objective changes before showing that PCC prevents the corresponding solver launch.

### 4.5 Official machine-readable standards plus independent execution

Standards-aware papers are stronger when they use frozen official artifacts, machine-readable validation, and reproducible execution. The paper should report APL 1.1.1 SHACL, the explicitly bounded QoCDC 4.1.4 subset, hashes, software versions, and the transformer-aware PowerModels/DCMP/HiGHS cross-stack check. The QoCDC subset must never be labeled full QoCDC compliance.

## 5. Minimum experimental bar for an EPSR submission

| Gate | Required evidence | Current status (2026-08-07) |
|---|---|---|
| Strong comparator ladder | Signed artifact, global identity, task footprint, invariants, full PCC; paired tests | Ready: 22 networks; harmful accepts 1320/1320/880/440/220/0; lawful accepts 660/660 for every method |
| Operational N-1 consequence | Multi-network overload consequence, uncertainty interval, failures retained | Ready: 53/56 valid; 53/53 unsafe results prevented; 0 harmful starts; median loading delta 3.879 percentage points; network sign test p=0.00390625 |
| OPF consequence | Multi-network cost/feasibility consequence and failures retained | Ready: 25/35 valid over five networks; 25/25 prevented; 0 harmful starts; median relative cost effect 5.96%; network sign test p=0.03125 |
| Large DC-SCOPF campaign | Five networks x ten states, all candidate branches, explicit failures | In progress: 36/50 state runs completed through case300 offset 5; 5,232 evaluated rows; 271 false-secure dispatches prevented; 0 harmful starts; 0 failed states |
| Official-standard evidence | Frozen APL/QoCDC artifacts, hashes, positive and negative controls | Ready within stated scope: official Svedala APL SHACL positive control; PCC separation; 15-check QoCDC L1-L4 subset and two negative controls |
| Untouched holdout | Source frozen before inspection; mechanical selection; lawful and harmful tests | Ready for task-semantic scope: complete proof accepted, missing proof rejected before solver start, and pypowsybl imports 59 elements. Raw APL SHACL is nonconforming and reported separately, so no global-conformance claim is made |
| Independent solver stack | Frozen Julia/PowerModels environment; status/objective/generation agreement under matched equations | Ready: transformer-aware DCMP/HiGHS gives 9/9 status and 8/8 mutually optimal numerical agreement; max objective error 4.70e-12. Unaligned DCP is retained as a negative formulation control |
| Runtime/scaling | Gate latency, downstream time avoided, size trend, hardware metadata | Existing scaling evidence ready; final table must merge DC-SCOPF and cross-stack timings |
| Statistical discipline | Exact denominators, familywise correction, cluster-aware intervals | Ready for semantic/N-1/OPF; must be applied to final DC-SCOPF endpoints |
| Reproducibility | Protocols, hashes, environment versions, one-command tables/figures | Mostly ready; clean-room rerun and immutable final lock pending |

## 6. Where the current evidence is stronger, equal, or weaker

Stronger than a typical two-case algorithm paper:

- semantic evaluation spans 22 networks with a preregistered ordered baseline ladder;
- lawful-retention and harmful-acceptance denominators are both reported;
- paired exact tests and multiplicity correction replace visual-only claims;
- the causal endpoint is downstream solver launch and operational consequence, not schema-error count;
- official standards artifacts and deliberately invalid negative controls are included.

Comparable to the stronger same-tier work:

- canonical N-1/OPF benchmarks, operational effect sizes, scaling, and explicit failure accounting;
- reproducibility artifacts and version-frozen protocols;
- multiple downstream tasks rather than one accuracy metric.

Still weaker until remaining gates close:

- the 5x10 DC-SCOPF campaign is incomplete;
- no final manuscript figures, consolidated runtime table, clean-room rerun, or independent review package;
- evidence is benchmark/simulation based, not utility-field deployment. Practical value should therefore be phrased as deployment-relevant prevention, not deployed impact.

## 7. Manuscript argument and claim boundaries

Recommended central claim:

> In the preregistered multi-network transformation tasks, conventional artifact and semantic checks accepted unsafe transformations that changed N-1 or OPF conclusions, whereas PCC rejected every observed unsafe case before downstream solver execution while accepting every lawful control.

Supporting claims:

1. Safety gaps decrease monotonically as validation moves from artifact identity to task-semantic proof.
2. Accepted unsafe transformations cause statistically detectable operational and economic changes.
3. PCC prevention generalizes across network sizes, tasks, an untouched source, and an independent solver stack once the remaining gates are closed.
4. The gate is standards-compatible and auditable, with bounded APL/QoCDC claims.

Forbidden or premature claims:

- universal correctness for all CGMES profiles, solvers, contingencies, or transformations;
- full QoCDC 4.1.4 compliance;
- zero risk outside the mutation and proof-obligation scope;
- real-world reliability improvement without field deployment evidence;

## 8. Decision rule

Submit to EPSR only after all three open scientific gates are satisfied:

1. the complete 5x10 DC-SCOPF denominator is reported with no unexplained exclusions;
2. the frozen untouched bundle reproduces lawful acceptance and harmful fail-closed behavior, with SHACL/import outcomes reported separately;
3. the independent PowerModels stack agrees on status for all planned pairs and on objective/generation within the frozen tolerances for all mutually optimal pairs. This gate is now satisfied by the transformer-aware DCMP/HiGHS run; the original tap-omitting DCP failure remains reported as a negative formulation control.

If an open gate fails, do not erase or replace it. Narrow the corresponding claim, diagnose the failure, and decide whether an additional preregistered repair experiment is warranted.

## 9. Primary sources

1. EPSR journal scope and metrics: https://www.sciencedirect.com/journal/electric-power-systems-research
2. EPSR Guide for Authors and research-data/software linking: https://www.sciencedirect.com/journal/electric-power-systems-research/publish/guide-for-authors
3. Memari, M. and Aljamous, Y., model-based conversion of CGMES data to operational network models (2023): https://doi.org/10.1186/s42162-023-00290-3
4. Constraint-driven deep learning for N-k SCOPF, EPSR (2024): https://www.sciencedirect.com/science/article/pii/S0378779624005789
5. Chen et al., learning optimization proxies for large-scale SCED, EPSR (2022), DOI 10.1016/j.epsr.2022.108566: https://www.osti.gov/pages/biblio/1880377
6. Formal analytics of stealthy attacks against contingency analysis, SEGAN (2024), DOI 10.1016/j.segan.2024.101310: https://www.sciencedirect.com/science/article/pii/S2352467724000390
7. Distributed SC-ACOPF via ADMM, *Operations Research*, DOI 10.1287/opre.2023.2486: https://pubsonline.informs.org/doi/10.1287/opre.2023.2486
8. Large-scale bilevel N-k adversarial robustness, *IEEE Transactions on Power Systems* (2025), DOI 10.1109/TPWRS.2025.3579521: https://www.osti.gov/pages/biblio/2569194
9. Computationally efficient SCOPF: https://arxiv.org/abs/2006.00585
10. Scalable decomposition for SCOPF: https://arxiv.org/abs/1910.03685
11. Constraint screening for SCOPF: https://arxiv.org/abs/1910.09034
12. Preventive SCOPF with probabilistic guarantees, DOI 10.3390/en13092344: https://doi.org/10.3390/en13092344
13. Chance-constrained AC-OPF with N-1 security: https://arxiv.org/abs/1508.06061
14. Nonlinear multi-period SCOPF (2026): https://link.springer.com/article/10.1007/s40866-026-00355-8
15. Full semantics preservation in model transformation: https://ris.utwente.nl/ws/files/5096671/report.pdf
16. Interactive CGMES-to-Modelica conversion (2024): https://sites.ecse.rpi.edu/~vanfrl/documents/publications/conference/2024/CP246_GHLVMDC_CIMTOMODELICA_Interactive_1570997274.pdf
17. PowerModels.jl documentation: https://lanl-ansi.github.io/PowerModels.jl/stable/
18. Julia official downloads: https://julialang.org/downloads/manual-downloads/
