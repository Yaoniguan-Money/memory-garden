"""第二层：运行时策略（阈值与开关），不含业务执行逻辑。

与 TriggerDecision / 编排意图的字段对应（命名不一一等同业务实现，仅表达开关与阈值）：

- **开庭（Court）**
  - ``court_turn_threshold``：按「用户回合数」累计的开庭阈值（亦称 turn-based court threshold）。
  - ``court_pending_seed_threshold``：按「待审 pending 种子数量」的开庭阈值（seed threshold for court）。
  - ``enable_auto_court``：是否允许自动开庭路径（仍须编排层实际调用 Core）。
  - ``enable_strong_signal_trigger``：是否允许**强信号**作为开庭候选触发开关（具体何种信号由后续编排定义）。
  - ``enable_topic_shift_trigger``：是否允许**话题切换**作为触发开庭/检查的开关。

- **梦境（Dream）**
  - ``dream_turn_threshold``：按回合数的 dream 阈值。
  - ``enable_auto_dream``：是否允许自动 dream。

- **反馈与收尾**
  - ``feedback_mode``：反馈展示粒度；具体 ``RuntimeFeedback`` 文案生成放在后续 Feedback Stage。
  - ``auto_close_on_session_end``：会话正常结束时是否由编排层自动推进关闭语义（写 ``closed_at``、状态迁移等）。

- **简报**
  - ``enable_harvest_brief``：是否允许挂接 ``GardenBrief``（非 Harvester 实现）。

不设复杂策略 DSL；编排层读取上述布尔与阈值后写入 ``TriggerDecision.reasons`` 等即可。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FeedbackMode(str, Enum):
    """对用户可见反馈的粒度（不涉及 LLM）。

    - ``closing_only``：仅在会话收尾（关闭）时生成用户可见反馈。
    - ``every_turn``：每回合可附加极简真实统计（须由编排层 ``GardenRuntime`` 挂载）。
    - ``debug_only``：便于测试/开发的可见反馈路径（不改变会话生命周期）。
    - ``minimal`` / ``normal``：兼容旧配置；分别近似 ``every_turn`` / ``closing_only``。
    """

    off = "off"
    closing_only = "closing_only"
    debug_only = "debug_only"
    every_turn = "every_turn"
    minimal = "minimal"
    normal = "normal"


class RuntimePolicy(BaseModel):
    """单次会话或全局可注入的运行策略：仅数据，不执行 tick。"""

    model_config = ConfigDict(validate_assignment=True)

    feedback_mode: FeedbackMode = Field(
        default=FeedbackMode.closing_only,
        description="反馈展示强度（默认仅收尾可见）",
    )
    court_turn_threshold: int | None = Field(
        default=None,
        ge=1,
        description="（回合阈值）距上次开庭或会话开始满多少轮用户回合可考虑开庭；None 表示不由该维度触发",
    )
    court_pending_seed_threshold: int | None = Field(
        default=None,
        ge=1,
        description="（种子数量阈值）pending 种子数达到该值时可考虑开庭；None 表示不由该维度触发",
    )
    dream_turn_threshold: int | None = Field(
        default=None,
        ge=1,
        description="（回合阈值）满多少轮可考虑触发 dream；None 表示不由阈值触发",
    )
    prune_check_turn_threshold: int | None = Field(
        default=None,
        ge=1,
        description="满多少轮可考虑修剪检查；None 表示不由阈值触发",
    )
    enable_auto_court: bool = Field(default=False, description="是否允许自动开庭候选（仍须编排层调用）")
    enable_auto_dream: bool = Field(default=False, description="是否允许自动梦境周期")
    enable_strong_signal_trigger: bool = Field(
        default=False,
        description="是否承认强信号作为触发维度（与 TriggerDecision.strong_signal 配对）",
    )
    enable_topic_shift_trigger: bool = Field(
        default=False,
        description="是否承认话题切换作为触发维度（与 TriggerDecision.topic_shift 配对）",
    )
    auto_close_on_session_end: bool = Field(
        default=False,
        description="会话正常结束时是否自动关闭（编排层据此写 closed_at / 状态；非命令实现）",
    )
    enable_harvest_brief: bool = Field(
        default=False,
        description="是否在编排层挂接 GardenBrief（非 Harvester 实现）",
    )
