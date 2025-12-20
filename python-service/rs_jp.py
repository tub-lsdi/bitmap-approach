import time
from loguru import logger


class RSJPAlgorithm:
    """
    Row-level Semantic Join Path algorithm using row-level PMI scores.
    """

    def create_bridge(
        self,
        list_r: list[str],
        list_s: list[str],
        pmi_scores: dict,
        top_k: int = 1,
    ) -> tuple[list[dict], dict]:
        """
        Create a bridge table using RS-JP algorithm.

        Args:
            list_r: Normalized list of strings from R set
            list_s: Normalized list of strings from S set
            pmi_scores: Dict[(r_val, s_val)] -> npmi_score (from Go service)
            top_k: Number of top candidates per R value (default: 1)

        Returns:
            Tuple of (results, timings):
            - results: List[{"r_val": str, "s_val": str, "npmi": float}]
            - timings: Dict with timing information for each step
        """
        start_time = time.time()
        timings = {}

        logger.info(
            f"RS-JP: Starting with |R|={len(list_r)}, |S|={len(list_s)}, "
            f"{len(pmi_scores)} PMI scores, top_k={top_k}"
        )

        # Step 1: Group by R value
        step1_start = time.time()
        r_to_candidates = {}
        for (r_val, s_val), pmi in pmi_scores.items():
            if r_val not in r_to_candidates:
                r_to_candidates[r_val] = []
            r_to_candidates[r_val].append({"s_val": s_val, "pmi": pmi})
        step1_duration = time.time() - step1_start
        timings['step1_group_by_r'] = step1_duration

        # Step 2: Select top-k per R value
        step2_start = time.time()
        results = []
        for r_val in list_r:
            if r_val in r_to_candidates:
                # Sort by PMI descending
                candidates = sorted(
                    r_to_candidates[r_val],
                    key=lambda x: x["pmi"],
                    reverse=True
                )
                # Take top-k
                for candidate in candidates[:top_k]:
                    results.append({
                        "r_val": r_val,
                        "s_val": candidate["s_val"],
                        "npmi": candidate["pmi"]
                    })
            else:
                logger.debug(f"RS-JP: No PMI scores found for r_val={r_val}")

        step2_duration = time.time() - step2_start
        timings['step2_select_topk'] = step2_duration

        # Step 3: Format output (negligible, but track for consistency)
        timings['step3_format_output'] = 0.0

        total_duration = time.time() - start_time
        timings['total_duration'] = total_duration

        logger.info(f"RS-JP: Complete! Generated {len(results)} mappings")
        logger.info(f"RS-JP: Total duration: {total_duration:.2f}s")
        logger.info(f"RS-JP: Timings breakdown: {timings}")

        return results, timings
