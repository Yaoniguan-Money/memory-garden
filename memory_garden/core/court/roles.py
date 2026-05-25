"""法庭角色论述生成（模板化中文陈述，非 LLM）。"""

from __future__ import annotations

from memory_garden.core.court.case import RuleOutcome
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.models import Seed


def triangulate_arguments(seed: Seed, outcome: RuleOutcome) -> tuple[str, str, str]:
    """生成控方、辩方、隐私守卫三方论点，均为非空字符串。"""
    excerpt = seed.source_excerpt[:120] if len(seed.source_excerpt) > 120 else seed.source_excerpt
    vt = outcome.verdict_type

    if vt == CourtVerdictType.forget:
        prosecutor = (
            "控方认为：用户表达了明确的遗忘或删除请求，将该片段写入长期记忆会与用户意志冲突，"
            "且可能造成不必要的回溯负担。"
        )
        defender = (
            "辩方认为：即便用户情绪波动，也应尊重「此刻不想保留」的边界信号，避免强行留存。"
        )
        privacy = (
            "隐私守卫：遗忘请求本身可能涉及先前对话片段；在未审计具体内容前，不应扩散或固化相关线索。"
        )

    elif vt == CourtVerdictType.greenhouse:
        prosecutor = (
            "控方认为：片段疑似包含敏感个人信息，一旦固化为可检索记忆，将增加泄露与误用风险。"
        )
        defender = (
            "辩方认为：其中也可能包含用户真实需求（如医疗随访），完全丢弃会损害可用性，宜隔离而非公开采摘。"
        )
        privacy = (
            "隐私守卫：敏感字段需要温室级隔离与最小暴露策略，禁止进入默认采摘路径。"
        )

    elif vt == CourtVerdictType.compost:
        prosecutor = (
            "控方认为：强烈负面自评若凝固成长期身份标签，会放大自我叙事风险，不宜直接种下。"
        )
        defender = (
            "辩方认为：情绪碎片仍有短期上下文价值，可通过堆肥转化而非身份级固化。"
        )
        privacy = (
            "隐私守卫：负面情绪可与敏感经历交织，需谨慎限制对外暴露范围。"
        )

    elif vt == CourtVerdictType.prune:
        prosecutor = (
            "控方认为：用户否定旧方向时，继续保留旧结论会造成花园叙事自相矛盾，应考虑修剪。"
        )
        defender = (
            "辩方认为：修剪目标需准确，否则可能误伤仍有效的相邻记忆，必须在理由充分时执行。"
        )
        privacy = (
            "隐私守卫：若被修剪对象曾含敏感信息，应在日志与副本策略上额外审慎。"
        )

    elif vt == CourtVerdictType.plant:
        prosecutor = (
            "控方认为：即便表述稳定，也存在口头偏好随时变更的可能，长期写入并非零风险。"
        )
        defender = (
            "辩方认为：该片段呈现可持续偏好或约束，能够帮助对话保持一致性与尊重用户边界，值得种下。"
        )
        privacy = (
            "隐私守卫：确认其中未夹带敏感标识或可追踪个人信息后再进入常规采摘。"
        )

    else:  # hold 及其他保守裁决
        prosecutor = (
            "控方认为：当前证据不足以支持写入长期记忆，贸然种下会产生噪声与潜在误导。"
        )
        defender = (
            "辩方认为：片段或许仍有潜在价值，完全丢弃可能错过后续澄清机会。"
        )
        privacy = (
            "隐私守卫：在信号不明确时，优先限制扩散范围，避免误把闲聊当作事实陈述。"
        )

    # 附带摘要增强可解释性（仍保持非空）
    tag = f"【摘录】{excerpt}"
    return (
        f"{prosecutor} {tag}",
        f"{defender} {tag}",
        f"{privacy} {tag}",
    )
