# Cover letter — Electric Power Systems Research

[Submission date]

Dear Editor,

Please consider our manuscript, “Task-semantic proof-carrying validation prevents unsafe execution of transformed power-system models,” for publication as a Research Article in *Electric Power Systems Research*.

Power-system studies increasingly depend on model conversion between exchange formats, internal representations, and optimization formulations. We identify an operationally consequential gap: a transformed model can remain parseable, signed, and numerically solvable while no longer representing the contingency or optimization task that the operator intended. Existing structural validation and solver-convergence checks do not close this gap.

We address the problem with a proof-carrying contract (PCC) and fail-closed execution gate. The method binds the exact source and target snapshots to authoritative asset relations, task-critical attributes, converter trace, and intervention semantics. The protected solver runs only after these task-specific obligations are verified.

The study demonstrates successful prevention, not only failure detection. Across 22 public networks and 1,980 transformations, PCC rejected all 1,320 harmful transformations and retained all 660 lawful controls. It prevented all 53 consequential AC N-1 launches, all 25 consequential AC-OPF launches, and all 369 strictly paired false-secure DC-SCOPF launches, with zero observed harmful starts. The frozen DC campaign covered 50 operating states and 12,340 candidate-outage rows. Transformer-aligned implementations in Windows PYPOWER/PIPS and WSL Julia/PowerModels/HiGHS agreed on every tested status and all eight mutually optimal objectives, with a maximum relative objective error of 4.70 × 10⁻¹². We additionally separate task-semantic validation from official CGMES structural checks, test an untouched CGMES holdout, and demonstrate verification scaling to 13,659 assets.

The practical contribution is an auditable safety layer for interoperable grid-model pipelines: it prevents a valid numerical answer to a semantically changed problem from entering an operational workflow. This system-level impact on contingency analysis and security-constrained optimization is directly aligned with the journal’s focus on power-system operation, security assessment, and evaluated procedures.

The manuscript is original, is not under consideration elsewhere, and has been approved by all authors. [Confirm or revise this sentence.] The authors declare [insert competing-interest statement]. Funding was provided by [insert funding statement]. The code and frozen evidence package are available at Zenodo DOI 10.5281/zenodo.21796488; the submission will cite the final immutable release version.

Thank you for your consideration.

Sincerely,

Zixuan Liu [confirm]  
Detroit Green Technology Institute, Hubei University of Technology [confirm postal address]  
[Postal address]  
[Email]  
[Telephone, if desired]
