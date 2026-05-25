"""CJK 分词与 FTS 查询构造测试。"""

from __future__ import annotations

from memory_garden.soil.cjk_ngram import (
    HAS_JIEBA,
    build_cjk_fts_match_query,
    build_cjk_token_query,
    cjk_bigram_index_text,
    cjk_index_text,
    jieba_tokenize,
)


def test_bigram_index_text_splits_continuous_cjk():
    text = cjk_bigram_index_text("中华人民共和国")
    assert "人民" in text
    assert len(text.split()) >= 4


def test_build_cjk_fts_match_query_or_chain():
    q = build_cjk_fts_match_query("深色 主题")
    assert " OR " in q
    assert '"' in q


def test_build_cjk_token_query_empty_for_ascii_only():
    assert build_cjk_token_query("hello world") == ""


def test_jieba_tokenize_fallback_without_jieba_matches_bigram_style():
  # 无 jieba 时与 bigram 行为一致
    tokens = jieba_tokenize("记忆花园")
    assert tokens
    if not HAS_JIEBA:
        assert "记忆" in tokens or "忆花" in tokens


def test_cjk_index_text_non_empty_for_chinese():
    indexed = cjk_index_text("用户偏好深色界面")
    assert indexed.strip()


def test_long_chinese_sentence_token_query_not_empty():
    sentence = "记忆花园支持本地优先的可审计记忆层用于智能体"
    q = build_cjk_token_query(sentence)
    assert q
    assert " OR " in q
