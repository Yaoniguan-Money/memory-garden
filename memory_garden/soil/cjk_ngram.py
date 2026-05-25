"""CJK 字符 bigram 生成与 FTS 查询构造（jieba 为可选依赖）。"""



from __future__ import annotations



import re



from memory_garden.runtime_config import CjkScriptConfig, default_garden_runtime_config





def _cjk_ranges(config: CjkScriptConfig | None = None) -> list[tuple[int, int]]:

    return (config or default_garden_runtime_config().cjk).codepoint_ranges





def _codepoint_in_ranges(cp: int, ranges: list[tuple[int, int]]) -> bool:

    return any(lo <= cp <= hi for lo, hi in ranges)





def contains_cjk(text: str, *, config: CjkScriptConfig | None = None) -> bool:

    ranges = _cjk_ranges(config)

    return any(_codepoint_in_ranges(ord(ch), ranges) for ch in text)





def _iter_cjk_segments(text: str, ranges: list[tuple[int, int]]) -> list[str]:

    segments: list[str] = []

    buf: list[str] = []

    for ch in text:

        if _codepoint_in_ranges(ord(ch), ranges):

            buf.append(ch)

        elif buf:

            segments.append("".join(buf))

            buf = []

    if buf:

        segments.append("".join(buf))

    return segments





def _bigram_tokens(segment: str) -> list[str]:

    if len(segment) <= 1:

        return [segment] if segment else []

    return [segment[i : i + 2] for i in range(len(segment) - 1)]





def cjk_bigram_index_text(text: str, *, config: CjkScriptConfig | None = None) -> str:

    """将文本中的连续 CJK 字符序列转为空格分隔 bigram token。"""

    ranges = _cjk_ranges(config)

    tokens: list[str] = []

    for segment in _iter_cjk_segments(text, ranges):

        tokens.extend(_bigram_tokens(segment))

    return " ".join(tokens)





def build_cjk_fts_match_query(query: str, *, config: CjkScriptConfig | None = None) -> str:

    """构造 FTS5 ``body_ngram`` 列 MATCH 子句内容（bigram OR 链）。"""

    grams = cjk_bigram_index_text(query, config=config).split()

    if not grams:

        return ""

    escaped = [g.replace('"', '""') for g in grams]

    return " OR ".join(f'"{g}"' for g in escaped)





def build_cjk_like_pattern(query: str, *, config: CjkScriptConfig | None = None) -> str:

    """保留 LIKE 回退：取长度 >=2 的 CJK 片段。"""

    ranges = _cjk_ranges(config)

    segments = [seg for seg in _iter_cjk_segments(query, ranges) if len(seg) >= 2]

    return segments[0] if segments else query.strip()





try:

    import jieba



    HAS_JIEBA = True

except ImportError:

    HAS_JIEBA = False





def jieba_tokenize(text: str, *, config: CjkScriptConfig | None = None) -> list[str]:

    """中文分词；无 jieba 时回退 bigram token。"""

    if not text or not text.strip():

        return []

    ranges = _cjk_ranges(config)

    if not HAS_JIEBA:

        tokens: list[str] = []

        for segment in _iter_cjk_segments(text, ranges):

            tokens.extend(_bigram_tokens(segment))

        return tokens

    seg_list = jieba.lcut(text)

    return [t.strip() for t in seg_list if t.strip()]





def cjk_index_text(text: str, *, config: CjkScriptConfig | None = None) -> str:

    """索引侧 CJK token 文本（jieba 词级或 bigram）。"""

    return " ".join(jieba_tokenize(text, config=config))





def build_cjk_token_query(text: str, *, config: CjkScriptConfig | None = None) -> str:

    """构造 FTS5 body_ngram MATCH 子句（优先 jieba，回退 bigram）。"""

    ranges = _cjk_ranges(config)

    tokens = jieba_tokenize(text, config=config)

    cjk_tokens = [t for t in tokens if any(_codepoint_in_ranges(ord(c), ranges) for c in t)]

    if not cjk_tokens:

        return ""

    escaped = [t.replace('"', '""') for t in cjk_tokens]

    return " OR ".join(f'"{t}"' for t in escaped)






