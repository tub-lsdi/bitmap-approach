import pulp
import time
from loguru import logger


class CSJPLPAlgorithm:
    """
    Uses column-level PMI scores and linear programming to find optimal join mappings.
    """

    def create_bridge(
        self,
        list_r: list[str],
        list_s: list[str],
        w_ijkl_scores: dict,
        top_k: int = 1,
    ) -> tuple[list[dict], dict]:
        """
        Create a bridge table using CS-JP-LP algorithm.

        1. Use provided PMI scores (from Go service)
        2. Formulate and solve CLP
        3. Round to half-integral solution (Algorithm 1)
        4. Convert to integral solution (Algorithm 2)
        5. Extract join function
        6. Optional greedy refinement

        Args:
            list_r: Normalized list of strings from R set
            list_s: Normalized list of strings from S set
            w_ijkl_scores: PMI scores as dict[(ri, sj, rk, sl)] -> column PMI score
            top_k: IGNORED in CS-JP-LP. This parameter is kept for API consistency
                   with RS-JP but has no effect. CS-JP-LP is a global optimization
                   problem that finds ONE complete mapping with the highest aggregate
                   column-level score. Unlike RS-JP (which independently finds top-k
                   candidates per row), CS-JP-LP considers all rows jointly, so there
                   is only one globally optimal solution.

        Returns:
            Tuple of (results, timings):
            - results: List of dictionaries with r_val, s_val, and npmi fields.
              Each result represents one row in the optimal global mapping.
              Note: 'npmi' field contains aggregate PMI score (sum), not a single PMI value.
            - timings: Dictionary with timing information for each step
        """
        start_time = time.time()
        timings = {}

        logger.info(
            f"CS-JP-LP: Starting with |R|={len(list_r)}, |S|={len(list_s)}, {len(w_ijkl_scores)} PMI scores")

        # Warn if top_k > 1 (parameter is ignored)
        if top_k > 1:
            logger.warning(
                f"CS-JP-LP: top_k={top_k} is ignored. CS-JP-LP always returns "
                f"ONE globally optimal mapping. Use RS-JP if you need top-k "
                f"candidates per row."
            )

        # Step 1: Solve CILP using Algorithm 2 (which constructs CLP, calls Algorithm 1, and converts to integral)
        step1_start = time.time()
        logger.info("CS-JP-LP: Step 1 - Solving CILP (calling Algorithm 2)...")
        x_star, z_star = self._algorithm_2_solve_cilp(
            list_r, list_s, w_ijkl_scores)
        step1_duration = time.time() - step1_start
        timings['step1_solve_cilp'] = step1_duration
        logger.info(
            f"CS-JP-LP: Step 1 - CILP solved, obtained integral solution ({step1_duration:.2f}s)")

        # Note: z_star is returned by Algorithm 2 per the paper's formal specification (which states
        # Algorithm 2 returns both x* and z*), but is not used in subsequent steps. The z* variables
        # are auxiliary variables introduced to linearize the quadratic term xij×xkl in the original
        # CIQP formulation. Once we have the integral solution x*, we only need it to extract the
        # join function J(ri) = sj where x*ij = 1. The z* values would only be needed to verify the
        # objective function value, but are not required for the actual join mapping.

        # Step 3: Extract join function
        step2_start = time.time()
        logger.info(
            "CS-JP-LP: Step 2 - Extracting join function from solution...")
        join_mapping = self._extract_join_function(list_r, list_s, x_star)
        step2_duration = time.time() - step2_start
        timings['step2_extract_join'] = step2_duration
        logger.info(
            f"CS-JP-LP: Step 2 - Extracted {len([v for v in join_mapping.values() if v is not None])} mappings ({step2_duration:.2f}s)")

        # DISABLED: Greedy refinement disabled for performance testing
        # join_mapping = self._greedy_refinement(
        #     list_r, list_s, join_mapping, w_ijkl_scores
        # )

        # Convert to output format
        step3_start = time.time()
        logger.info("CS-JP-LP: Step 3 - Converting to output format...")
        result = []
        for r_val, s_val in join_mapping.items():
            if s_val is not None:  # Not ⊥
                # Calculate the objective score for this mapping
                score = self._calculate_mapping_score(
                    r_val, s_val, join_mapping, w_ijkl_scores
                )
                result.append(
                    {
                        "r_val": r_val,
                        "s_val": s_val,
                        "npmi": score,  # Use 'npmi' field name
                    }
                )

        step3_duration = time.time() - step3_start
        timings['step3_convert_output'] = step3_duration

        total_duration = time.time() - start_time
        timings['total_duration'] = total_duration

        logger.info(
            f"CS-JP-LP: Complete! Generated {len(result)} final mappings ({step3_duration:.2f}s)")
        logger.info(f"CS-JP-LP: Total duration: {total_duration:.2f}s")
        logger.info(f"CS-JP-LP: Timings breakdown: {timings}")

        return result, timings

    def _solve_clp(self, list_r: list[str], list_s: list[str], w_ijkl_scores: dict):
        """
        Formulate CILP, relax to CLP, and solve.

        Returns:
            x_bar: dict[(ri, sj)] -> fractional value in [0, 1]
            z_bar: dict[(ri, sj, rk, sl)] -> fractional value in [0, 1]
        """
        logger.info(
            f"  Formulating LP with {len(list_r)} x {len(list_s)} = {len(list_r) * len(list_s)} x variables...")

        prob = pulp.LpProblem("CLP", pulp.LpMinimize)

        x_vars = {}
        for i, ri in enumerate(list_r):
            for j, sj in enumerate(list_s):
                x_vars[(ri, sj)] = pulp.LpVariable(
                    f"x_{i}_{j}", lowBound=0, upBound=1, cat="Continuous"
                )

        logger.info(
            f"  Creating {len(w_ijkl_scores)} z variables from PMI scores...")
        z_vars = {}
        r_index = {r: i for i, r in enumerate(list_r)}
        s_index = {s: j for j, s in enumerate(list_s)}

        for (ri, sj, rk, sl), w_ijkl in w_ijkl_scores.items():
            if ri != rk:
                i = r_index[ri]
                j = s_index[sj]
                k = r_index[rk]
                l = s_index[sl]
                z_vars[(ri, sj, rk, sl)] = pulp.LpVariable(
                    f"z_{i}_{j}_{k}_{l}", lowBound=0, upBound=1, cat="Continuous"
                )

        objective = pulp.lpSum(
            [
                w_ijkl * (1 - z_vars[(ri, sj, rk, sl)])
                for (ri, sj, rk, sl), w_ijkl in w_ijkl_scores.items()
                if (ri, sj, rk, sl) in z_vars
            ]
        )
        prob += objective

        # Each ri maps to at most one sj
        for ri in list_r:
            prob += pulp.lpSum([x_vars[(ri, sj)] for sj in list_s]) <= 1

        logger.info(f"  Adding {len(z_vars)} constraints...")
        for ri, sj, rk, sl in z_vars.keys():
            prob += z_vars[(ri, sj, rk, sl)] <= 0.5 * (
                x_vars[(ri, sj)] + x_vars[(rk, sl)]
            )

        logger.info(
            "  Solving LP problem")
        prob.solve(pulp.HiGHS_CMD(msg=0))
        logger.info(f"  LP solved with status: {pulp.LpStatus[prob.status]}")

        if prob.status != pulp.LpStatusOptimal:
            logger.warning(f"LP solver status: {pulp.LpStatus[prob.status]}")

        x_bar = {}
        for (ri, sj), var in x_vars.items():
            x_bar[(ri, sj)] = var.varValue if var.varValue is not None else 0.0

        z_bar = {}
        for (ri, sj, rk, sl), var in z_vars.items():
            z_bar[(ri, sj, rk, sl)
                  ] = var.varValue if var.varValue is not None else 0.0

        return x_bar, z_bar

    def _algorithm_1_round_to_half_integral(
        self, list_r: list[str], list_s: list[str], w_ijkl_scores: dict
    ):
        """
        Round to Half-Integral Solution.

        Input: CLP program (via list_r, list_s, w_ijkl_scores)
        Output: Half-integral solution (x̃*ᵢⱼ, z̃*ᵢⱼₖₗ) where x̃*ᵢⱼ ∈ {0, 1} and z̃*ᵢⱼₖₗ ∈ {0, 1/2, 1}

        Returns:
            x_tilde: dict[(ri, sj)] -> value in {0, 1}
            z_tilde: dict[(ri, sj, rk, sl)] -> value in {0, 1/2, 1}
        """
        logger.info("  Algorithm 1: Solving CLP...")
        x_bar, z_bar = self._solve_clp(list_r, list_s, w_ijkl_scores)

        logger.info(
            f"  Algorithm 1: Rounding {len(list_r)} x variables to integral values...")
        x_tilde = {}
        for ri in list_r:
            x_values_for_ri = {sj: x_bar.get((ri, sj), 0.0) for sj in list_s}
            all_integral = all(
                abs(val - round(val)) < 1e-9 for val in x_values_for_ri.values()
            )

            if all_integral:
                for sj in list_s:
                    x_tilde[(ri, sj)] = round(x_bar.get((ri, sj), 0.0))
            else:
                # Calculate contribution scores: cᵢⱼ = Σ(rₖ∈R, k≠i) Σ(sₗ∈S) (1/2) × wᵢⱼₖₗ
                #
                # OPTIMIZATION:
                # The sum Σ(rₖ∈R, k≠i) Σ(sₗ∈S) wᵢⱼₖₗ includes terms where wᵢⱼₖₗ may be zero
                # (quadruples that never co-occur in the data). Since adding zero does not
                # affect the sum, we can equivalently iterate only over the quadruples
                # present in w_ijkl_scores rather than all O(|R|²|S|²) possible combinations.
                # This optimization is particularly effective when the PMI score dictionary
                # is sparse, which is typical in real-world data where most value pairs do
                # not co-occur across tables.
                #
                # Original formulation (explicit nested loops over all combinations):
                # contribution_scores = {}
                # for sj in list_s:
                #     c_ij = 0.0
                #     for rk in list_r:
                #         if rk != ri:  # k ≠ i
                #             for sl in list_s:
                #                 w_ijkl = w_ijkl_scores.get((ri, sj, rk, sl), 0.0)
                #                 c_ij += 0.5 * w_ijkl
                #     contribution_scores[sj] = c_ij

                contribution_scores = {sj: 0.0 for sj in list_s}
                for (r_i_key, s_j_key, r_k_key, s_l_key), w_ijkl in w_ijkl_scores.items():
                    # Check if ri appears in FIRST position of quadruple
                    if r_i_key == ri and r_k_key != ri:
                        contribution_scores[s_j_key] += 0.5 * w_ijkl
                    # Check if ri appears in THIRD position of quadruple
                    elif r_k_key == ri and r_i_key != ri:
                        contribution_scores[s_l_key] += 0.5 * w_ijkl

                if contribution_scores:
                    p = max(contribution_scores.items(), key=lambda x: x[1])[0]
                    for sj in list_s:
                        x_tilde[(ri, sj)] = 1 if sj == p else 0
                else:
                    for sj in list_s:
                        x_tilde[(ri, sj)] = 0

        # COMMENTED OUT FOR MEMORY OPTIMIZATION:
        # Since z_tilde is never read or used in any subsequent computation (algorithm correctness depends only on
        # x_tilde), we skip creating it to avoid the memory issue.
        #
        # Original code:
        # z_tilde = {}
        # for ri in list_r:
        #     for sj in list_s:
        #         for rk in list_r:
        #             if rk != ri:  # k ≠ i
        #                 for sl in list_s:
        #                     z_tilde[(ri, sj, rk, sl)] = 0.5 * (
        #                         x_tilde.get((ri, sj), 0) +
        #                         x_tilde.get((rk, sl), 0)
        #                     )

        z_tilde = {}
        return x_tilde, z_tilde

    def _algorithm_2_solve_cilp(
        self, list_r: list[str], list_s: list[str], w_ijkl_scores: dict
    ):
        """
        Solve CILP.

        Input: CILP program (via list_r, list_s, w_ijkl_scores)
        Output: Integral solution (x*ᵢⱼ, z*ᵢⱼₖₗ) where both are in {0, 1}

        Returns:
            x_star: dict[(ri, sj)] -> value in {0, 1}
            z_star: dict[(ri, sj, rk, sl)] -> value in {0, 1}
        """
        # The CLP is defined implicitly by list_r, list_s, w_ijkl_scores
        x_tilde, z_tilde = self._algorithm_1_round_to_half_integral(
            list_r, list_s, w_ijkl_scores
        )

        x_star = x_tilde.copy()

        # COMMENTED OUT FOR MEMORY OPTIMIZATION:
        # This calculation creates O(|R|² × |S|²) dictionary entries. As noted in create_bridge(),
        # z_star is never used in subsequent steps - the algorithm's correctness
        # depends only on x_star.
        #
        # Original code:
        # z_star = {}
        # for ri in list_r:
        #     for sj in list_s:
        #         for rk in list_r:
        #             if rk != ri:  # k ≠ i
        #                 for sl in list_s:
        #                     # If x*ᵢⱼ = 1 AND x*ₖₗ = 1: z*ᵢⱼₖₗ ← 1, else 0
        #                     if (
        #                         x_star.get((ri, sj), 0) == 1
        #                         and x_star.get((rk, sl), 0) == 1
        #                     ):
        #                         z_star[(ri, sj, rk, sl)] = 1
        #                     else:
        #                         z_star[(ri, sj, rk, sl)] = 0

        z_star = {}
        return x_star, z_star

    def _extract_join_function(
        self, list_r: list[str], list_s: list[str], x_star: dict
    ):
        """
        Extract the Join Function.

        Returns:
            join_mapping: dict[ri] -> sj or None (for ⊥)
        """
        join_mapping = {}

        for ri in list_r:
            mapped_sj = None
            for sj in list_s:
                if x_star.get((ri, sj), 0) == 1:
                    mapped_sj = sj
                    break
            join_mapping[ri] = mapped_sj

        return join_mapping

    def _greedy_refinement(
        self,
        list_r: list[str],
        list_s: list[str],
        join_mapping: dict,
        w_ijkl_scores: dict,
    ):
        """
        Optional Greedy Refinement.

        Returns:
            improved_mapping: dict[ri] -> sj or None
        """
        improved = True
        current_mapping = join_mapping.copy()

        while improved:
            improved = False
            current_score = self._calculate_total_objective(
                current_mapping, w_ijkl_scores
            )

            for ri in list_r:
                best_sj = current_mapping[ri]
                best_score = current_score

                candidates = list_s + [None]
                for sj in candidates:
                    if sj == current_mapping[ri]:
                        continue

                    test_mapping = current_mapping.copy()
                    test_mapping[ri] = sj
                    test_score = self._calculate_total_objective(
                        test_mapping, w_ijkl_scores
                    )

                    if test_score > best_score:
                        best_score = test_score
                        best_sj = sj

                if best_sj != current_mapping[ri]:
                    current_mapping[ri] = best_sj
                    current_score = best_score
                    improved = True

        return current_mapping

    def _calculate_total_objective(self, join_mapping: dict, w_ijkl_scores: dict):
        """
        Calculate the total objective score for a join mapping.
        """
        total_score = 0.0

        for (ri, sj, rk, sl), w_ijkl in w_ijkl_scores.items():
            if join_mapping.get(ri) == sj and join_mapping.get(rk) == sl:
                total_score += w_ijkl

        return total_score

    def _calculate_mapping_score(
        self, r_val: str, s_val: str, join_mapping: dict, w_ijkl_scores: dict
    ):
        """
        Calculate the contribution score for a specific (r_val, s_val) mapping.

        Returns the sum of column-level PMI scores

        Note: This is an aggregate score (sum of multiple PMI values), not bounded.
        Values can be large as they represent cumulative evidence for this mapping
        across all column-level co-occurrences.
        """
        score = 0.0

        for (ri, sj, rk, sl), w_ijkl in w_ijkl_scores.items():
            if ri == r_val and sj == s_val and join_mapping.get(rk) == sl:
                score += w_ijkl
            elif rk == r_val and sl == s_val and join_mapping.get(ri) == sj:
                score += w_ijkl

        return score
