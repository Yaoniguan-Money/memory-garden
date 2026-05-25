"""第二层：Harvester / BriefWriter 安全占位实现（无 Core、无检索、无生成式大模型）。"""

from __future__ import annotations

from typing import Any

from memory_garden.runtime.session import GardenBrief, TurnContext


class NullHarvester:
    """空采摘器：永远返回字段占位且 ``source_memory_ids`` 为空的 ``GardenBrief``。"""

    def harvest(self, turn_context: TurnContext) -> GardenBrief:
        _ = turn_context  # 仅占位参数，不读取仓储、不做搜索
        return GardenBrief(
            intent="（未启用）本轮未执行记忆采摘",
            use="无可用药引：编排层可替换 Harvester",
            avoid="不臆测用户长期偏好",
            style="中性占位",
            safety="默认保守：无外链检索",
            nudge="若需记忆辅助请接入真实 Harvester",
            source_memory_ids=[],
        )


class TemplateBriefWriter:
    """模板简报写入：固定句式 + 对字符串型 ``selected_memories`` 轻量透传为 ``source_memory_ids``。"""

    def write(self, selected_memories: list[Any], turn_context: TurnContext) -> GardenBrief:
        _ = turn_context
        ids: list[str] = []
        seen: set[str] = set()
        for item in selected_memories:
            if isinstance(item, str):
                s = item.strip()
                if s and s not in seen:
                    seen.add(s)
                    ids.append(s)
        ids = ids[:32]
        return GardenBrief(
            intent="模板占位：意图字段待编排注入",
            use="模板占位：可选用线索仅限 source_memory_ids",
            avoid="模板占位：避免编造未出示的事实",
            style="模板占位：语气中性",
            safety="模板占位：敏感内容降级由上层负责",
            nudge="模板占位：提示用户复核摘要",
            source_memory_ids=ids,
        )
