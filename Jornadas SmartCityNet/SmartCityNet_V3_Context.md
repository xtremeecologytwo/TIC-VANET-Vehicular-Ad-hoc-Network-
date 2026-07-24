# SmartCityNet V3 - Manuscript Context and Revision Protocol

## 1. Purpose of this file

This document records the scientific scope, structural decisions, mathematical conventions, retained evidence, and pending tasks for `SmartCityNet_V3.tex`. It is intended to prevent future revisions from reconstructing the manuscript history or reintroducing material that was deliberately removed.

## 2. Central message of Version 3

The article is not an optimization-model paper and does not claim a new graph algorithm. Its central contribution is a reproducible web-based preprocessing platform that converts:

`geographical area -> SUMO mobility snapshots -> candidate RSUs -> direct V2V/V2I matrices -> minimum-hop connectivity -> optimization-ready dataset`.

The final scientific product is an optimization-ready, traceable dataset. The matrices are intermediate representations used to generate this dataset.

## 3. Intended venue and page strategy

- Target style: MDPI Engineering Proceedings.
- Total venue limit discussed in the project: approximately eight pages including references and mandatory statements.
- V3 is written to be concise but is not prematurely forced into exactly eight pages.
- A later editorial iteration will reduce length after verified experimental results and references are inserted.

## 4. Definitive main structure

1. Introduction
2. Related Work
3. Web Platform and Connectivity-Data Generation
4. Experimental Results
5. Conclusions and Future Work

There is no independent Discussion section.

Section 4 contains only:

- 4.1 Experimental Settings
- 4.2 Results

Limitations and interpretation are incorporated into the Results narrative. There is no Section 4.3.

## 5. Revision-color convention

- Black: translated or revised content inherited from the original Spanish manuscript.
- Blue: technical additions accepted during the V2-V3 revision.
- Red: evidence, measurements, references, metadata, or decisions that remain pending.

Red text must not be converted into factual claims without supporting evidence.

## 6. Accepted contributions

The V3 contributions are:

1. A Streamlit frontend integrated with a Python/SUMO backend.
2. Automatic direct V2V and V2I connectivity generation under binary range and building-obstruction conditions.
3. Candidate-RSU filtering using minimum junction degree and greedy spatial clustering.
4. Cumulative and minimum-hop connectivity matrices.
5. Export of optimization-ready matrices and sparse tuples.
6. A formal correctness result for cumulative and first-arrival multi-hop matrices.
7. A sensitivity analysis of minimum degree and clustering radius on candidate-set reduction.

## 7. Material deliberately removed

The following material must not be reintroduced into the current conference version unless the scope is explicitly changed:

- BFS validation experiments.
- Theoretical BFS-versus-matrix complexity comparison.
- Two-scenario comparison.
- A separate Discussion section.
- A long Python/NumPy code listing for multi-hop processing.
- A long OPL `.dat` listing.
- A second proof of the first-arrival result.
- A detailed computational-geometry discussion of collinearity, shared endpoints, and numerical tolerances.
- Claims that the matrix recurrence is a new graph algorithm.

BFS remains only as future work.

## 8. Architecture and pseudocode decisions

- Keep one compact architecture/workflow figure.
- Do not retain a second pipeline figure unless later evidence shows it is necessary.
- Candidate selection is expressed in language-independent pseudocode using `algorithm2e`.
- The algorithm is explicitly described as a preprocessing heuristic, not as an optimal placement method.

## 9. Mathematical definitions

For each snapshot `s`:

- `V_s`: active vehicles, with cardinality `n_s`.
- `R`: real candidate RSUs, with cardinality `m`.
- `A_s`: binary V2V adjacency matrix, dimension `n_s x n_s`.
- `B_s`: binary direct V2I matrix, dimension `n_s x m`.
- `A_tilde_s = beta(A_s + I)`.
- `R_{s,1} = B_s`.
- `R_{s,h} = beta(A_tilde_s R_{s,h-1})` for `h = 2,...,H`.
- `S_{s,1} = R_{s,1}`.
- `S_{s,h} = R_{s,h} - R_{s,h-1}` for `h >= 2`.

The recurrence is developed using ordinary dense matrix multiplication followed by thresholding.

A short note may state that Boolean-semiring multiplication could reduce average computational effort, but it does not change the dense worst-case order. Boolean implementation is future work.

## 10. Formal result

The proposition establishes:

`(R_{s,h})_{ik} = 1` if and only if vehicle `i` reaches real RSU `k` in at most `h` hops.

The corollary establishes:

`(S_{s,h})_{ik} = 1` if and only if the minimum hop count is exactly `h`.

Only one induction proof is retained.

The purple matrix illustration is retained as the visual explanation of cumulative and first-arrival matrices.

## 11. Artificial RSU semantics

The artificial RSU `r_inf` is always available to every vehicle.

It does not represent only physical disconnection. It represents the optimization alternative of leaving a vehicle unserved because:

- a reachable real RSU is not deployed;
- deployed RSUs are saturated;
- cost, capacity, or other optimization constraints lead to no service.

Therefore, a vehicle can have both real-RSU tuples and its artificial tuple.

## 12. Tuple definition and cardinality

For snapshot `s`:

`CVR_s = {<s,h,i,k> : (S_{s,h})_{ik}=1} union {<s,H+1,i,r_inf> : i in V_s}`.

Let:

`K_s = sum_h nnz(S_{s,h}) = nnz(R_{s,H})`.

Then:

`|CVR_s| = K_s + n_s`.

Bounds:

`n_s <= |CVR_s| <= n_s(m+1)`.

The hop limit `H` does not multiply the number of exported real tuples because each reachable pair is exported once, at its minimum hop.

## 13. Experimental design

Only one real scenario is used:

- Historic Centre of Quito, Ecuador.

The experiment varies:

- minimum junction degree `g_min`;
- greedy clustering radius `rho`.

Proposed compact configurations:

| Configuration | g_min | rho |
|---|---:|---:|
| A | 3 | 15 m |
| B | 3 | 20 m |
| C | 4 | 20 m |
| D | 5 | 25 m |

These values are proposals and may be adjusted to the actual interface.

For every configuration report:

- original eligible junctions `X`;
- retained candidates `Y`;
- reduction percentage `100(1-Y/X)`.

Suggested visuals:

1. A compact plot of retained candidates and reduction percentage by configuration.
2. Optionally, a map comparing the least and most restrictive configurations.

No independent performance or BFS plots are required for V3.

## 14. Preliminary inherited values

The original manuscript reported:

- 620 SUMO junctions;
- 160 candidate RSUs for the degree-4/radius-20 m configuration;
- approximately 74% reduction;
- 132 simulated vehicles;
- 31 snapshots;
- 1710 connectivity tuples.

These values are preliminary and must be reproduced with the final code. A previously reported range of 256-333 RSUs with connected vehicles is inconsistent with a filtered candidate set of 160 and must not be reused without clarification.

## 15. Results interpretation

The results should emphasize candidate-space reduction and its trade-off.

Do not claim that a smaller candidate set produces a better deployment. Candidate filtering can reduce model size and solution time but may remove useful locations. Later validation should measure its influence on:

- deployment objective value;
- coverage;
- disconnected demand;
- capacity feasibility;
- solver time and optimality gap.

## 16. Limitations retained in V3

- Buildings are represented as two-dimensional polygons.
- Connectivity is binary and geometric.
- No height, path loss, multipath, interference, channel load, or packet-delivery probability is modeled.
- Snapshots are independent; no time-respecting store-carry-forward paths are represented.
- Candidate filtering is heuristic.
- The influence of candidate filtering on final optimization quality is not yet measured.

## 17. Future work

The conclusion should mention:

- comparison against BFS implementations;
- sparse and Boolean-semiring matrix implementations;
- analysis of matrix densification by hop;
- dynamic tuple generation inside the optimization algorithm, including decomposition or column generation;
- richer propagation/reliability models;
- validation of candidate filtering through deployment cost, coverage, capacity, runtime, and optimality gap.

## 18. Writing style

- Technical English at approximately B1-B2 level.
- Direct, formal, and suitable for a young researcher.
- Avoid inflated vocabulary and AI-style section titles.
- Avoid repeating the contribution list in the conclusion.
- Distinguish software functionality from measured scientific results.

## 19. Pending evidence and metadata

Before submission, complete:

- verified sensitivity measurements;
- generated plots;
- bounding box and map date;
- SUMO, Python, and library versions;
- hardware and random seed;
- exact final interface defaults;
- code and dataset repository;
- full recent related-work bibliography;
- author list and CRediT contributions;
- funding/project identifier;
- acknowledgments and AI-disclosure policy;
- ORCID and complete affiliation required by the venue.

## 20. Generated deliverables

- `SmartCityNet_V3.tex`: reconstructed manuscript.
- `SmartCityNet_V3.pdf`: compiled verification copy using the available LaTeX environment.
- `SmartCityNet_V3_Context.md`: this context and revision protocol.
