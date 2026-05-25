"""规则版种子策略：关键词与短语（仅字符串匹配，无 LLM）。"""

from __future__ import annotations

# 明确遗忘 / 删除记忆意图 —— 命中则不生成候选种子（避免控制句被偏好化）
FORGET_OR_PURGE_PHRASES: tuple[str, ...] = (
    "忘掉",
    "不要记住",
    "别记住",
    "删除记忆",
    "forget this",
    "forget_this",
)

# 花园控制口令 —— 不作为记忆输入
CONTROL_COMMANDS: tuple[str, ...] = (
    "花花开",
    "花花关",
)

# 长期偏好 / 习惯倾向提示词
PREFERENCE_MARKERS: tuple[str, ...] = (
    "喜欢",
    "偏好",
    "希望",
    "以后",
    "从现在起",
    "以后回复",
    "我更喜欢",
    "更喜欢",
    "local-first",
    "local first",
)

# 约束 / 反感表达提示词（「不要记住」等已在遗忘短语中单独处理）
# 注意：不使用单字标记（如「别」），避免误匹配「特别」「告别」等
CONSTRAINT_MARKERS: tuple[str, ...] = (
    "不要",
    "别再说了",
    "不可以",
    "禁止",
    "避免",
    "少一点",
    "别再",
    "切勿",
)

# 负面自我评价提示词
NEGATIVE_SELF_TALK_MARKERS: tuple[str, ...] = (
    "我不行",
    "我很差",
    "我没用",
    "我完蛋了",
    "我好废",
    "什么都做不好",
)

# 敏感个人信息提示词
SENSITIVE_MARKERS: tuple[str, ...] = (
    "身份证",
    "手机号",
    "住址",
    "密码",
    "银行卡",
    "病历",
    "诊断",
)

# 用户明确纠正 —— 应触发 MERGE/PRUNE 而非新建
CORRECTION_MARKERS: tuple[str, ...] = (
    "不是那样的",
    "你理解错了",
    "改一下",
    "纠正",
    "不对",
    "之前说错了",
    "我不是那个意思",
    "重新记",
)

# 采纳信号 —— 用户认可助手建议，可升格为记忆
ADOPTION_MARKERS: tuple[str, ...] = (
    "就这样",
    "我认可",
    "按这个来",
    "这个很好",
    "这个方向对",
    "采纳",
    "照这个",
    "就按你说的",
)

# 身份声明 —— 用户描述自己是谁
IDENTITY_MARKERS: tuple[str, ...] = (
    "我是",
    "我的工作是",
    "我从事",
    "我的角色是",
    "我负责",
    "我主要做",
    "我的背景是",
)

# 流程/程序性描述 —— 用户描述工作方式
PROCEDURAL_MARKERS: tuple[str, ...] = (
    "第一步",
    "第二步",
    "先做",
    "再做",
    "流程是",
    "工作流",
    "我的工作方式是",
    "我通常先",
)

# 边界设定 —— 用户明确划定底线
BOUNDARY_MARKERS: tuple[str, ...] = (
    "不能接受",
    "底线是",
    "我拒绝",
    "绝不允许",
    "这是我的边界",
    "不可触碰",
)

# 临时/短暂内容 —— 不应固化为长期记忆
EPHEMERAL_MARKERS: tuple[str, ...] = (
    "今天天气",
    "我刚才看到",
    "刚刚发生的",
    "临时",
    "就这一次",
    "暂时",
)

# 明确记忆指令 —— 用户要求记住
EXPLICIT_REMEMBER_MARKERS: tuple[str, ...] = (
    "记住",
    "请记住",
    "别忘了",
    "提醒我",
    "记下来",
    "保存这条",
    "以后用到",
)

# 不确定性 —— 用户自己也不确定
UNCERTAINTY_MARKERS: tuple[str, ...] = (
    "也许",
    "可能吧",
    "不太确定",
    "看情况",
    "有时候",
    "不一定",
    "再说吧",
    "还不确定",
)

# 未来意图 —— 用户计划做某事
FUTURE_INTENT_MARKERS: tuple[str, ...] = (
    "我计划",
    "我打算",
    "准备做",
    "后面要",
    "接下来想",
    "下一步",
    "目标是",
    "想实现",
)

# 社交礼仪 —— 不形成记忆
SOCIAL_PLEASANTRIES: tuple[str, ...] = (
    "谢谢",
    "感谢",
    "辛苦了",
    "你好",
    "再见",
)

# 假设/反事实 —— 不稳定信号
HYPOTHETICAL_MARKERS: tuple[str, ...] = (
    "假如",
    "假设",
    "如果有一天",
    "万一",
    "要是",
    "倘若",
)

# 第三方声明 —— 用户替别人说话
THIRD_PARTY_MARKERS: tuple[str, ...] = (
    "他说",
    "她说",
    "他们说",
    "有人告诉我",
    "听说",
    "据说",
)


def text_matches_forget_or_control(text: str) -> bool:
    """是否包含遗忘指令或控制口令（大小写不敏感匹配英文短语）。"""
    lower = text.casefold()
    for phrase in FORGET_OR_PURGE_PHRASES:
        if phrase.casefold() in lower:
            return True
    for cmd in CONTROL_COMMANDS:
        if cmd in text:
            return True
    return False


def text_matches_marker_set(text: str, markers: tuple[str, ...]) -> bool:
    """任一关键词子串命中即 True。"""
    return any(m in text for m in markers)
