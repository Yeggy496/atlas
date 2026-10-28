"""Find a valid incumbent before spending the remaining budget on objectives."""
from dataclasses import dataclass
from time import monotonic

from ortools.sat.python import cp_model


@dataclass
class SearchResult:
    solver: cp_model.CpSolver
    status: cp_model.CpSolverStatus
    wall_time: float
    objective: float
    best_bound: float
    source: str


def _solver(seconds, workers):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.000001, seconds)
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = 42
    return solver


def search(model, seconds, workers, objective=None):
    started = monotonic()
    seed = None
    spent = 0.0
    if objective is not None:
        feasibility = model.clone()
        feasibility.clear_objective()
        first = _solver(min(10.0, seconds / 3), workers)
        status = first.solve(feasibility)
        spent = first.wall_time
        if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
            return SearchResult(first, status, spent, 0.0, 0.0, 'feasibility')
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            seed = first
            # The clone has exactly the same variables and hard constraints.
            model.clear_hints()
            for index in range(len(model.proto.variables)):
                var = model.get_int_var_from_proto_index(index)
                model.add_hint(var, first.value(var))
        remaining = seconds - (monotonic() - started)
        if seed is not None and remaining <= 0:
            return SearchResult(seed, cp_model.FEASIBLE, spent, float(seed.value(objective)), 0.0, 'feasibility')
    else:
        remaining = seconds

    final = _solver(remaining, workers)
    status = final.solve(model)
    spent += final.wall_time
    if status == cp_model.UNKNOWN and seed is not None:
        # A satisfaction solve's OPTIMAL does not prove the optimization objective.
        return SearchResult(seed, cp_model.FEASIBLE, spent, float(seed.value(objective)),
                            float(final.best_objective_bound), 'feasibility')
    return SearchResult(final, status, spent,
                        float(final.value(objective)) if objective is not None and status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0.0,
                        float(final.best_objective_bound), 'optimization' if objective is not None else 'feasibility')
