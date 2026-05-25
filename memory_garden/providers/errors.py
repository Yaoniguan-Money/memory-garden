"""Provider 层异常类型。"""


class ProviderError(Exception):
    """Provider 执行失败的基础异常。"""


class ProviderPolicyError(ProviderError):
    """Provider 策略拦截调用时抛出。"""
