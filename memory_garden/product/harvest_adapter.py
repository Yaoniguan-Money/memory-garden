"""Product 层与 Harvest 子系统之间的薄适配层。"""



from __future__ import annotations



from memory_garden.harvest.bounded_scan import scan_memory_cards

from memory_garden.harvest.candidate_source import select_product_candidate_source

from memory_garden.harvest.local_embedding import cosine_similarity, embed_local

from memory_garden.harvest.models import HarvestQuery

from memory_garden.harvest.retrieval_diagnostics import (

    PRODUCT_SCAN_LIMIT,

    RETRIEVAL_DIAGNOSTICS_KEY,

    RETRIEVAL_LATENCY_MS_KEY,

    attach_retrieval_diagnostics,

    build_retrieval_diagnostics,

    get_coarse_top_m,

    get_product_scan_limit,

    get_retrieval_strategy,

    get_vector_top_n,

    get_score_top_n,

    resolve_total_available_after_scan,

)



__all__ = [

    "PRODUCT_SCAN_LIMIT",

    "RETRIEVAL_DIAGNOSTICS_KEY",

    "RETRIEVAL_LATENCY_MS_KEY",

    "HarvestQuery",

    "attach_retrieval_diagnostics",

    "build_retrieval_diagnostics",

    "cosine_similarity",

    "embed_local",

    "get_coarse_top_m",

    "get_product_scan_limit",

    "get_retrieval_strategy",

    "get_vector_top_n",

    "get_score_top_n",

    "resolve_total_available_after_scan",

    "scan_memory_cards",

    "select_product_candidate_source",

]

