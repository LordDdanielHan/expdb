# code for determining whether (k, l) is an exponent pair [up to epsilons] in the sense of
# Graham and Kolesnik (1991) "Van der Corput's Method of Exponential Sums"

from hypotheses import *
from bound_beta import *
import copy
from fractions import Fraction as frac
import itertools
import numpy as np
from scipy.spatial import ConvexHull

# Note: for the purposes of this database, we use the definition of exponent pair that allows for epsilon losses in the bound.
class Exp_pair:
    def __init__(self, k, l):
        self.k = k
        self.l = l

    def __repr__(self):
        return f"The exponent pair ({self.k}, {self.l})"

    def __eq__(self, other):
        if isinstance(other, Exp_pair):
            return (self.k, self.l) == (other.k, other.l)
        return False


########################################################################################
# Constructors for exponent pairs


def literature_exp_pair(k, l, ref):
    return Hypothesis(
        f"{ref.author()} exponent pair",
        "Exponent pair",
        Exp_pair(k, l),
        f"See [{ref.author()}, {ref.year()}]",
        ref,
    )


def derived_exp_pair(k, l, proof, dependencies):
    year = Reference.max_year(tuple(d.reference for d in dependencies))
    bound = Hypothesis(
        f"Derived exponent pair ({k}, {l})",
        "Exponent pair",
        Exp_pair(k, l),
        proof,
        Reference.derived(year),
    )
    bound.dependencies = dependencies
    return bound


# Trivial exponent pair
trivial_exp_pair = Hypothesis(
    f"Trivial exponent pair (0, 1)",
    "Exponent pair",
    Exp_pair(frac(0, 1), frac(1, 1)),
    f"Triangle inequality",
    Reference.trivial(),
)

# The exponent pair conjecture
exponent_pair_conjecture = Hypothesis(
    f"Exponent pair conjecture",
    "Exponent pair",
    Exp_pair(0, 0),
    f"Conjecture",
    Reference.conjectured(),
)

###############################################################################


# Compute a list of exponent pairs generated by a initial set of exponent pairs,
# and a list of transforms.
# Parameters:
#   - 'search_depth' (integer) the maximum number of times we apply a transform.
#   - 'prune' (Boolean) if true, the set of exponent pairs is pruned at each iteration.
#                       Based on our current knowledge this should allow us to
#                       compute the same convex hull but faster, however future
#                       additions to the set of exponent pair transforms may mean
#                       that pruning leads to suboptimal exponent pairs.
def compute_exp_pairs(hypothesis_set, search_depth=5, prune=True):
    pairs = hypothesis_set.list_hypotheses("Exponent pair")
    transforms = hypothesis_set.list_hypotheses("Exponent pair transform")

    pairs = {(p.data.k, p.data.l): p for p in pairs}
    for i in range(search_depth):
        for h in transforms:
            for p in list(pairs):
                tp = h.data.transform(pairs[p])
                key = (tp.data.k, tp.data.l)
                if key not in pairs:
                    pairs[key] = tp

        if prune:
            if len(pairs) < 3:
                continue  # Don't prune if set is too small
            pairs = [p for p in pairs.values()]
            conv = ConvexHull(np.array([[p.data.k, p.data.l] for p in pairs]))
            verts = [pairs[v] for v in conv.vertices]
            pairs = {(p.data.k, p.data.l): p for p in verts}

    return [p for p in pairs.values()]


# Compute the convex hull of exponent pairs from the literature. This method merely
# only uses existing Exponent Pair hypotheses (it does not expand the set of
# exponent pairs via transformations or other results)
def compute_convex_hull(hypothesis_set):
    pairs = hypothesis_set.list_hypotheses("Exponent pair")

    # Computed convex hull is stored within `hypothesis_list` the first time
    # to avoid repeatedly computing it for multiple values of sigma.
    if not hypothesis_set.data_valid or "convex_hull" not in hypothesis_set.data:
        if len(pairs) < 3:
            hypothesis_set.data["convex_hull"] = list(pairs)
        else:
            conv = ConvexHull(np.array([[p.data.k, p.data.l] for p in pairs]))
            vertices = [pairs[v] for v in conv.vertices]
            hypothesis_set.data["convex_hull"] = vertices
            hypothesis_set.data_valid = True

    return hypothesis_set.data["convex_hull"]


# Given a set of hypotheses, returns a set of exponent pairs implied by the beta
# bounds
def beta_bounds_to_exponent_pairs(hypothesis_set):
    if not isinstance(hypothesis_set, Hypothesis_Set):
        raise "hypothesis_set must be of type Hypothesis_Set"

    # Compute the best bound on beta - (imported bound_beta.py method)
    beta_bound = compute_best_beta_bounds(hypothesis_set)
    
    # If there are no beta bounds, or it does not cover the entire [0, 1/2]
    # interval, then there are no exponent pairs generated
    if len(beta_bound) == 0 or (
        beta_bound[0].data.bound.domain.x0 > 0
        or beta_bound[-1].data.bound.domain.x1 < frac(1, 2)
    ):
        return []

    # Get a list of critical points
    points = [[0, 0], [frac(1, 2), 0]]  # include the trivial point and a placeholder
    for h in beta_bound:
        piece = h.data.bound
        points.append([piece.domain.x0, piece.at(piece.domain.x0, extend_domain=True)])
        points.append([piece.domain.x1, piece.at(piece.domain.x1, extend_domain=True)])

    # Compute the convex hull containing the \beta bounds
    conv = ConvexHull(np.array(points))

    # Precompute the dependencies. Currently every beta bound that is on the boundary
    # of the convex hull is included in the dependencies for every exponent pair
    dep_indices = set()
    for v in conv.vertices:
        if v >= 2:  # skip the placeholder vertices:
            p = points[v]
            for i in range(len(beta_bound)):
                f = beta_bound[i].data.bound
                if (f.domain.x0 == p[0] and f.at(p[0], extend_domain=True) == p[1]) or (
                    f.domain.x1 == p[0] and f.at(p[0], extend_domain=True) == p[1]
                ):
                    dep_indices.add(i)
    dependencies = [beta_bound[i] for i in dep_indices]
    # Keep track of the existing set of exponent pairs,
    known_ephs = hypothesis_set.list_hypotheses("Exponent pair")
    known_eps = {(p.data.k, p.data.l):p for p in known_ephs}
    all_eps = [e for e in known_ephs]
    
    for i in range(len(conv.vertices)):
        p1 = points[conv.vertices[i]]
        p2 = points[conv.vertices[(i + 1) % len(conv.vertices)]]
        # Remove degenerate cases
        if (
            (p1[1] == 0 and p2[1] == 0)
            or (p1[0] == 0 and p2[0] == 0)
            or (p1[0] == frac(1, 2) and p2[0] == frac(1, 2))
        ):
            continue

        # Tangent line \beta = m * \alpha + c \implies the exponent pair (c, m + c)
        m = (p2[1] - p1[1]) / (p2[0] - p1[0])
        c = (p1[1] * p2[0] - p1[0] * p2[1]) / (p2[0] - p1[0])
        key = (c, m + c)
        h = None
        if key not in known_eps:
            h = derived_exp_pair(
                key[0],
                key[1],
                f"Follows from combining {len(dependencies)} bounds on \\beta",
                set(dependencies),
            )
            all_eps.append(h)
        else:
            h = known_eps[key]

        # Since we only consider \alpha \in [0, 1/2], we need to apply the B transformation to
        # also get those exponent pairs which are B transforms of the new exponent pairs
        B = hypothesis_set.find_hypothesis(keywords="van der Corput B transform")
        if B is None:
            continue
        Bh = B.data.transform(h)
        if (Bh.data.k, Bh.data.l) not in known_eps:
            all_eps.append(Bh)
    return all_eps


# Returns whether point p lies in the triangle with vertices a, b, c (all points 
# two-dimensional)
def in_triangle(a, b, c, p):
     d = ((b[1] - c[1])*(a[0] - c[0]) + (c[0] - b[0])*(a[1] - c[1]))
     x = ((b[1] - c[1])*(p[0] - c[0]) + (c[0] - b[0])*(p[1] - c[1]))
     y = ((c[1] - a[1])*(p[0] - c[0]) + (a[0] - c[0])*(p[1] - c[1]))
     return 0 <= x and x <= d and 0 <= y and y <= d and x + y <= d;


# Find a proof of the exponent pair (k, l), assuming a set of hypotheses. 
# If deep_search is true, then all points inside the convex hull (not 
# just the vertices on the boundary) are searched. This tends to return
# the least complex proof (measured in terms of dependencies) is returned. 
# Unfortunately, this can be slow for large hypothesis sets. 
# If reduce_dependencies is true, then only the dependencies crucial to the
# proof are returned
def construct_proof(k, l, hypotheses, reduce_dependencies=True, deep_search=True):
    
    ephs = hypotheses.list_hypotheses(hypothesis_type="Exponent pair")
    if len(ephs) == 0: return None
    
    # First check if the exact exponent pair is in the set, since that 
    # only takes O(n) time
    hyp = next((h for h in ephs if (h.data.k, h.data.l) == (k, l)), None)
    if hyp is not None: return hyp

    # Compute the convex hull to check if it contains the desired exponent 
    # If not - exit early
    verts = compute_convex_hull(hypotheses)
    conv = Polytope.from_V_rep([[v.data.k, v.data.l] for v in verts])
    if not conv.contains([k, l]): return None

    # The exponent pair is contained in the convex hull - if reduce_dependencies,
    # is set to false, return the entire hull as dependencies
    if not reduce_dependencies:
        proof = "Follows from convexity and the exponent pairs " + ", ".join(
            f"({v.data.k}, {v.data.l})" for v in verts)
        return derived_exp_pair(k, l, proof, set(verts))
    
    # Otherwise, instead of including all vertices of the convex hull, include only 
    # the three vertices defining a triangle containing the exponent pair. 
    # This becomes an optimisation problem: given points p_1, ..., p_N,
    # and their associated values v_1, ..., v_N, find the triangle with 
    # vertices (p_a, p_b, p_c) containing (k, l) such that v_a + v_b + v_c is minimal. 
    lowest_comp = float("inf")
    best_tri = None

    # If deep search is selected, we need to include all exponent pairs in the 
    # hypothesis set, not just those on the boundary of the convex hull
    if deep_search: verts = ephs

    # Perform a naive brute-force search in O(n^3) time
    for tri in itertools.combinations(verts, 3):
        if in_triangle((tri[0].data.k, tri[0].data.l),
                        (tri[1].data.k, tri[1].data.l),
                        (tri[2].data.k, tri[2].data.l),
                        (k, l)):
            comp = sum(v.proof_complexity() for v in tri)
            if comp < lowest_comp:
                lowest_comp = comp
                best_tri = tri

    proof = "Follows from convexity and the exponent pairs " + ", ".join(
            f"({v.data.k}, {v.data.l})" for v in best_tri)
    return derived_exp_pair(k, l, proof, set(best_tri))


# This method attempts to prove that (k, l) is an exponent pair from the
# set of hypotheses. If successful, it returns the new bound as a Hypothesis object
# otherwise, None is returned
def find_best_proof(k, l, hypotheses, method=Proof_Optimization_Method.DATE):
    if not isinstance(hypotheses, Hypothesis_Set):
        raise ValueError("hypotheses must be of type Hypothesis_Set")

    # Generate a proof of the exponent pair (k, l) by minimising the date of the
    # last dependency
    if method == Proof_Optimization_Method.DATE:
        from_year = min(
            h.reference.year()
            for h in hypotheses
            if h.reference.year() != "Unknown date"
        )
        to_year = max(
            h.reference.year()
            for h in hypotheses
            if h.reference.year() != "Unknown date"
        )

        num_hypotheses = 0
        for year in range(from_year, to_year + 1):
            hyps = Hypothesis_Set(
                h
                for h in hypotheses
                if (h.reference.year() == "Unknown date" or h.reference.year() <= year)
            )
            # Only proceed if there are new hypotheses
            if len(hyps) == num_hypotheses:
                continue
            num_hypotheses = len(hyps)

            # Compute the set of exponent pairs known as of the current "year"
            hyps.add_hypotheses(beta_bounds_to_exponent_pairs(hyps))
            hyps.add_hypotheses(compute_exp_pairs(hyps, prune=True))
            eph = construct_proof(k, l, hyps, reduce_dependencies=True, deep_search=False)
            if eph is not None:
                return eph
        return None

    # Generate a proof of the exponent pair (k, l) by minimising the complexity
    # of dependencies
    elif method == Proof_Optimization_Method.COMPLEXITY:
        # In general, this optimisation is difficult, and the optimal solution 
        # is not guaranteed. The current (heuristic) method is to try two approaches. 
        # 1. First, start with all known exponent pairs, and iteratively apply 
        # transformations until their convex hull contains the desired exponent pair
        # In particular, no beta bounds are considered at this stage. There is also 
        # no pruning at each stage, since there may be low-complexity exponent pairs 
        # lying away from the boundary of the convex hull at any time. 
        MAX_ITERATIONS = 10
        hyps = copy.copy(hypotheses)
        for i in range(MAX_ITERATIONS):
            hyps.add_hypotheses(compute_exp_pairs(hyps, search_depth=1, prune=False))
            eph = construct_proof(k, l, hyps, reduce_dependencies=True, deep_search=True)
            if eph is not None:
                return eph

        # 2. If that above approach fails, then start with all baseline 
        # hypotheses (i.e. those hypothesis with complexity 1), including beta bounds 
        # and their implied exponent pairs. 
        hyps = copy.copy(hypotheses)
        hyps.add_hypotheses(beta_bounds_to_exponent_pairs(hyps))
        for i in range(MAX_ITERATIONS):
            hyps.add_hypotheses(compute_exp_pairs(hyps, search_depth=1, prune=False))
            eph = construct_proof(k, l, hyps, reduce_dependencies=True, deep_search=True)
            if eph is not None:
                return eph
        return None

    elif method == Proof_Optimization_Method.NONE:
        hyps = copy.copy(hypotheses)
        hyps.add_hypotheses(beta_bounds_to_exponent_pairs(hyps))
        hyps.add_hypotheses(compute_exp_pairs(hyps, prune=True))
        return construct_proof(k, l, hypotheses, deep_search=False, reduce_dependencies=False)
    else:
        raise NotImplementedError()
