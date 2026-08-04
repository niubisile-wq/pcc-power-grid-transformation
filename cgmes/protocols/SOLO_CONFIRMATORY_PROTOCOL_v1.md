# Solo confirmatory protocol v1

Status: **frozen for post-smoke development experiments at 2026-08-03T23:49:50+08:00**  
Manuscript: *Proof-carrying canonicalization exposes identity-loss risks in public power-grid benchmarks*

The two-model import smoke test preceded this freeze and is exploratory feasibility evidence only.
It cannot be counted as an internal-validation or final-holdout result. No internal-validation or
future final-holdout model had been imported by the experiment scripts at freeze time.

## Primary hypotheses

H1: At least one preregistered public software round-trip produces a non-injected source-target
identity mapping anomaly while the target remains parseable.

H2: At least one such anomaly passes the applicable structural or numerical baseline but is
rejected by the identity-aware PCC gate.

H3: For anomalies admitted to operational replay, the transformed representation changes a
preregistered PF, named-asset N−1, N−1 ranking or AC-OPF endpoint relative to the source or a
verifiably repaired representation.

H4: Full PCC reduces harmful false accepts relative to identity-only on cases whose identity
relation is valid but whose task scope, snapshot, version, provenance, payload or signature is
invalid.

Failure to support a hypothesis is a reportable result and triggers the positioning rules below;
it is not a reason to redefine an endpoint.

## Corpus assignment

- Development: CGMES 2.4.15 Test Configurations 4.0.3.
- Internal validation: CGMES CAS Test Configurations 3.0.3.
- Reference specifications only: Application Profiles 3.0.2 and Network Code Profiles 2.4.2.
- Final holdout: not yet available. Existing local archives were already extracted before this
  protocol was drafted and therefore cannot be called untouched holdouts. A later versioned
  public model release must be acquired after code/container freeze.

The exact package and extracted-file hashes are recorded in
`corpus/official_cgmes_corpus_manifest.json`.

## Inclusion and exclusion

Include every model bundle belonging to a preregistered configuration and supported by at least
one frozen adapter. Include every outcome from every attempted route. Exclude only documentation,
profile definitions used solely as validation shapes, duplicate byte-identical files, or models
whose required profile is explicitly unsupported before execution. Each exclusion must have a
machine-readable reason and remain in the attempt table.

Natural interoperability cases must arise from a frozen software route. Manual injection,
post-result editing and selective retention are forbidden. Human adjudication may label the
meaning of an automatically detected mapping anomaly, but adjudicators must not see downstream
decision endpoints until the mapping label is frozen.

## Toolchains and environments

The minimum experiment uses two official development models and two independent public tools.
Preferred tools are pandapower and VeraGrid; PyPowSyBl is the preregistered fallback if one cannot
import the selected profile. Exact versions, interpreter version, operating system and dependency
lock are recorded for every run. A tool import failure is a result, not permission to omit a route.

## Mapping and validation

All adapters emit the frozen common asset schema. Mapping status is one of: exact, renamed,
lawful_split, lawful_merge, unsupported_split, unsupported_merge, dropped, created, ambiguous or
unresolved. An mRID change alone is not harmful. Lawfulness requires an explicit reproducible
identity relation, verifiable common parent or documented tool transformation.

The eight frozen gates B0–B7 and their descriptive names are defined in
`baseline_contract_v1.yaml`. Manuscript tables use descriptive names, never historical shorthand.

## Endpoints

Primary validation endpoints are harmful FAR, lawful FRR and unresolved rate. Secondary endpoints
are error-type recall, manual-review rate, latency p50/p95/p99, certificate bytes and peak memory.
Operational endpoints are paired convergence, maximum voltage and loading difference, named-asset
N−1 safety class, rank correlation/overlap, AC-OPF cost regret and load shedding.

Paired-valid means that both source and target complete the same task under the same frozen solver
protocol. All failures and non-convergence remain in the total denominator and a separate failure
table.

## Statistics

- Paired binary decisions: McNemar test with exact confidence intervals where applicable.
- FAR/FRR: exact Clopper-Pearson or Wilson intervals, always with numerator and denominator.
- Regret and ranking: bootstrap by network/model unit, not by asset row.
- Network, toolchain and version are stratification units.
- Multiplicity: Holm adjustment within each declared endpoint family.
- No threshold, inclusion rule or primary endpoint may change after the corresponding holdout is run.

## Run locking and reruns

Before a confirmatory run, generate `manifests/RUN_LOCK.json` containing input hashes, Git commit if
available, script hashes, environment lock hash, tool versions, protocol hashes and container digest.
The final holdout is run once. Reruns are allowed only for preregistered infrastructure failures
that occur before endpoints are computed. Every attempt is logged and retained.

## Gates and positioning

- Gate 1: no natural non-injected mapping anomaly -> remove any public-benchmark prevalence/risk
  implication and position the work as a formal task-aware validation framework.
- Gate 2: full PCC does not outperform identity-only in task-relevant cases -> make task-aware
  identity-relation validation the core method; move broader contract fields to engineering scope.
- Gate 3: no reproducible operational consequence -> retain interoperability/data-quality claims
  only; do not claim observed decision risk.

Only simultaneous positive evidence across the relevant gates permits the stronger NC-facing story.
No outcome guarantees journal acceptance.

## Evidence boundaries

Public test models are not field-operation data. Public software conversions are evidence only for
the tested versions and routes. Single-team cross-environment replication is not independent
external replication. No industry prevalence, production deployment or field-event rate will be
claimed.
