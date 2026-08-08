"""Exact active-constraint screening utilities for convex PyPSA SCLOPF."""

from __future__ import annotations

from collections import defaultdict
from itertools import product

import numpy as np
import pandas as pd
import xarray as xr


DUAL_TOLERANCE = 1e-7
SLACK_TOLERANCE = 1e-6


def create_security_constrained_model(network, outages):
    """Create PyPSA's SCLOPF Linopy model without invoking a solver."""
    branch_outages = pd.MultiIndex.from_tuples(
        list(outages), names=["component", "name"]
    )
    model = network.optimize.create_model()
    for sub_network in network.sub_networks.obj:
        branches = sub_network.branches_i()
        selected = branches.intersection(branch_outages)
        if selected.empty:
            continue
        sub_network.calculate_BODF()
        bodf_frame = pd.DataFrame(
            sub_network.BODF, index=branches, columns=branches
        )[selected]
        for outage_component, affected_component in product(
            selected.unique(0), branches.unique(0)
        ):
            outage_dim = outage_component + "-outage"
            outage_names = selected.get_loc_level(outage_component)[1]
            flow_outage = model.variables[outage_component + "-s"].loc[:, outage_names]
            flow_outage = flow_outage.rename({"name": outage_dim})
            bodf = xr.DataArray(
                bodf_frame.loc[affected_component, outage_component],
                dims=[affected_component, outage_dim],
            )
            added_flow = flow_outage * bodf
            for bound, kind in product(("lower", "upper"), ("fix", "ext")):
                constraint_name = affected_component + "-" + kind + "-s-" + bound
                if constraint_name not in model.constraints:
                    continue
                constraint = model.constraints[constraint_name]
                index = constraint.lhs.indexes["name"].intersection(
                    added_flow.indexes[affected_component]
                )
                added_aligned = added_flow.sel({affected_component: index}).rename(
                    {affected_component: "name"}
                )
                lhs = constraint.lhs.sel(name=index) + added_aligned
                name = (
                    constraint_name
                    + f"-security-for-{outage_dim}-in-sub-network-{sub_network.name}"
                )
                model.add_constraints(
                    lhs,
                    constraint.sign.sel(name=index),
                    constraint.rhs.sel(name=index),
                    name=name,
                )
    return model


def bodf_post_contingency_loadings(network, candidates) -> dict[str, float]:
    """Vectorize the same linear outage-flow relation used by PyPSA SCLOPF."""
    flow_parts = []
    rating_parts = []
    for component, frame, dynamic in (
        ("Line", network.lines, network.lines_t.p0),
        ("Transformer", network.transformers, network.transformers_t.p0),
    ):
        values = dynamic.loc["now"].astype(float).copy()
        values.index = pd.MultiIndex.from_tuples(
            [(component, str(name)) for name in values.index], names=["component", "name"]
        )
        ratings = frame.s_nom.astype(float).copy()
        ratings.index = pd.MultiIndex.from_tuples(
            [(component, str(name)) for name in ratings.index], names=["component", "name"]
        )
        flow_parts.append(values)
        rating_parts.append(ratings)
    flows = pd.concat(flow_parts)
    ratings = pd.concat(rating_parts)
    requested = {tuple(candidate) for candidate in candidates}
    result: dict[str, float] = {}
    for sub_network in network.sub_networks.obj:
        branches = sub_network.branches_i()
        outages = [tuple(item) for item in branches if tuple(item) in requested]
        if not outages:
            continue
        sub_network.calculate_BODF()
        outage_positions = branches.get_indexer(outages)
        base_flow = flows.loc[branches].to_numpy(dtype=float)
        rating = ratings.loc[branches].to_numpy(dtype=float)
        bodf = np.asarray(sub_network.BODF)[:, outage_positions]
        post = base_flow[:, None] + bodf * base_flow[outage_positions][None, :]
        loading = np.nanmax(np.abs(post) / rating[:, None], axis=0)
        for outage, value in zip(outages, loading):
            result[f"{outage[0]}:{outage[1]}"] = float(value)
    missing = {f"{component}:{name}" for component, name in candidates} - set(result)
    if missing:
        raise RuntimeError("bodf_post_loading_missing_candidates:" + ",".join(sorted(missing)))
    return result


def active_security_outages(
    network, *, dual_tolerance: float = DUAL_TOLERANCE, slack_tolerance: float = SLACK_TOLERANCE
) -> dict[str, dict]:
    """Return outage groups that can affect the solved convex optimum.

    An outage is conservatively active when any constraint in its security
    group is binding or has a nonzero dual. The solved Linopy model must still
    be attached to ``network`` and must have an optimal solution.
    """
    activity: dict[str, dict] = defaultdict(
        lambda: {"max_abs_dual": 0.0, "min_abs_slack": float("inf"), "groups": 0}
    )
    for name, constraint in network.model.constraints.items():
        if "security-for" not in name:
            continue
        outage_dims = [dim for dim in constraint.dual.dims if dim.endswith("-outage")]
        if len(outage_dims) != 1:
            raise RuntimeError(f"unexpected_outage_dimensions:{name}:{outage_dims}")
        outage_dim = outage_dims[0]
        component = outage_dim[: -len("-outage")]
        reduce_dims = [dim for dim in constraint.dual.dims if dim != outage_dim]
        dual = abs(constraint.dual).max(dim=reduce_dims).to_series()
        slack = abs(constraint.lhs.solution - constraint.rhs).min(
            dim=[dim for dim in constraint.rhs.dims if dim != outage_dim]
        ).to_series()
        for outage in dual.index:
            key = f"{component}:{outage}"
            item = activity[key]
            item["max_abs_dual"] = max(item["max_abs_dual"], float(dual.loc[outage]))
            item["min_abs_slack"] = min(item["min_abs_slack"], float(slack.loc[outage]))
            item["groups"] += 1
    return {
        key: {
            **value,
            "active": bool(
                value["max_abs_dual"] > dual_tolerance
                or value["min_abs_slack"] <= slack_tolerance
            ),
        }
        for key, value in sorted(activity.items())
    }
