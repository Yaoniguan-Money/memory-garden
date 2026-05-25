"""检索扫描与截断的可观测 diagnostics（规则路径，不改变检索算法）。"""



from __future__ import annotations



from collections.abc import Callable

from typing import Any



from pydantic import BaseModel, ConfigDict



from memory_garden.runtime_config import GardenRuntimeConfig, default_garden_runtime_config



RETRIEVAL_DIAGNOSTICS_KEY = "retrieval_diagnostics"

RETRIEVAL_LATENCY_MS_KEY = "retrieval_latency_ms"





def get_product_scan_limit(runtime: GardenRuntimeConfig | None = None) -> int:

    """产品有界扫描上限（来自运行时配置树，非模块内魔法数）。"""

    cfg = runtime or default_garden_runtime_config()

    return cfg.retrieval.scan_limit





def get_coarse_top_m(runtime: GardenRuntimeConfig | None = None) -> int:

    cfg = runtime or default_garden_runtime_config()

    return cfg.retrieval.coarse_top_m





# 向后兼容：等于 ``GardenRuntimeConfig.default().retrieval.scan_limit``

PRODUCT_SCAN_LIMIT = get_product_scan_limit()


def get_retrieval_strategy(runtime: GardenRuntimeConfig | None = None) -> str:
    cfg = runtime or default_garden_runtime_config()
    return cfg.retrieval.strategy.value


def get_vector_top_n(runtime: GardenRuntimeConfig | None = None) -> int:
    cfg = runtime or default_garden_runtime_config()
    return cfg.retrieval.vector_top_n


def get_score_top_n(runtime: GardenRuntimeConfig | None = None) -> int:
    cfg = runtime or default_garden_runtime_config()
    return cfg.retrieval.score_top_n





class RetrievalDiagnostics(BaseModel):

    model_config = ConfigDict(validate_assignment=True, extra="forbid")



    total_available: int

    scanned_count: int

    candidate_count: int

    truncated: bool

    source: str

    fallback_reason: str = ""

    candidate_source: str = ""





def build_retrieval_diagnostics(

    *,

    total_available: int,

    scanned_count: int,

    candidate_count: int,

    source: str,

    fallback_reason: str = "",

    candidate_source: str = "",

) -> dict[str, Any]:

    """构建 diagnostics 字典，并保证 ``truncated == (scanned_count < total_available)``。"""

    truncated = scanned_count < total_available

    return RetrievalDiagnostics(

        total_available=total_available,

        scanned_count=scanned_count,

        candidate_count=candidate_count,

        truncated=truncated,

        source=source,

        fallback_reason=fallback_reason,

        candidate_source=candidate_source,

    ).model_dump(mode="json")





def attach_retrieval_diagnostics(metadata: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:

    merged = dict(metadata)

    merged[RETRIEVAL_DIAGNOSTICS_KEY] = diagnostics

    return merged





def resolve_total_available_after_scan(

    *,

    scanned_count: int,

    scan_limit: int,

    count_all: Callable[[], int] | None = None,

) -> int:

    """扫描未触达 limit 时总量等于已扫描数；触达 limit 时可选回调统计全量。"""

    if scanned_count < scan_limit:

        return scanned_count

    if count_all is not None:

        return count_all()

    return scanned_count


