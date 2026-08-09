# Cover letter - Electric Power Systems Research

9 August 2026

Dear Editor,

We are pleased to submit our manuscript, "Proof-Carrying Contracts for Task-Safe Power-System Model Transformation," for consideration as a Research Article in *Electric Power Systems Research*.

Power-system security studies now depend on long model-preparation chains. A grid model may move from CIM or CGMES exchange files into internal network objects, and then into an optimization-ready formulation before N-1 analysis, OPF, or SCOPF is launched. Much of the recent progress in *Electric Power Systems Research* and neighboring venues has strengthened the final computation, including scalable stochastic N-1 pre-dispatch, chance-constrained OPF, safe learning-based operation, reliability evaluation, and security-constrained optimization under uncertainty. These advances share an important premise: the solver-facing model still represents the task selected on the source model.

Our manuscript focuses on the point where this premise must be checked. A transformed model can be syntactically valid, signed, importable, and numerically solvable while no longer representing the selected contingency or optimization task. A branch can be omitted, two devices can be merged, a rating or generator limit can change, or an outage can be mapped to another target asset. In these cases, the solver may return a valid numerical answer for a study that is not the one originally intended. Schema validation, identifier matching, provenance, import tests, and convergence checks do not by themselves establish task preservation.

We propose proof-carrying contracts (PCC) for task-safe power-system model transformation. PCC binds source and target task projections to authoritative asset relations, required electrical and economic attributes, converter trace evidence, and intervention semantics. A protected fail-closed gate releases the transformed model to N-1 analysis, AC-OPF, or DC-SCOPF only when these obligations are satisfied. This moves validation from a post-hoc check to a condition for execution. The relevant question is not only whether the file is valid or the solver converges, but whether the computation being released is still the declared grid task.

PCC complements existing validation and optimization work by acting between the exchange layer and the solver layer. CGMES/CIM and SHACL-style checks establish structural and profile properties of exchange artifacts. OPF and SCOPF methods improve the optimization model, uncertainty treatment, or computational efficiency after the study has been formed. PCC verifies the handoff between these layers: selected assets must be covered, allowed relations must hold, task-critical attributes must remain within tolerance, and outage or dispatch interventions must still select the intended objects. In practical terms, it checks whether a valid model artifact has become a valid operational computation.

The experiments show that this gate changes what reaches the solver. Across 22 public networks and 1,980 transformations, PCC rejected all 1,320 harmful transformations and accepted all 660 lawful controls. It blocked all 53 consequential AC N-1 launches, all 25 consequential AC-OPF launches, and all 369 false-secure DC-SCOPF launches found in the paired campaign. No harmful protected solver start was observed. The DC-SCOPF experiment covered 50 operating states and 12,340 candidate-outage rows. Independent PYPOWER/PIPS and Julia/PowerModels/HiGHS implementations agreed on every tested status and all eight mutually optimal objectives, with a maximum relative objective error of 4.70 x 10^-12. We also separate task-semantic validation from official CGMES structural checks, test an untouched public CGMES holdout, and demonstrate verification scaling to 13,659 assets.

We believe the manuscript is well suited to *Electric Power Systems Research* because it strengthens power-system analysis at the point where exchanged grid data becomes an executable security or optimization study. It contributes to contingency analysis, OPF, SCOPF, CGMES/CIM-based interoperability, model validation, and reproducible computation. Its practical value is direct: it keeps a valid answer to a semantically changed problem from entering the operational workflow.

The manuscript is original, has not been published previously, is not under consideration elsewhere, and has been approved by all authors. No earlier conference version of this manuscript has been published or submitted. The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper. This work was supported in part by the National Natural Science Foundation of China (62202148), the Natural Science Foundation of Hubei Province (2022CFB908 and 2019CFB530), and the China Scholarship Council (201808420418). The code and frozen evidence package are available at Zenodo DOI 10.5281/zenodo.21796488.

Thank you for your consideration.

Sincerely,

Wei Xiong  
Corresponding author  
School of Electrical and Electronic Engineering, Hubei University of Technology  
Department of Computer Science and Engineering, University of South Carolina  
xw@mail.hbut.edu.cn
