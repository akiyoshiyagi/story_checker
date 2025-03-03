from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

# 評価範囲の列挙型
class EvaluationScope(str, Enum):
    DOCUMENT_WIDE = "document_wide"  # 文書全体をまとめて評価
    ALL_SUMMARIES = "all_summaries"  # サマリー文章だけをまとめて評価
    SUMMARY_PAIRS = "summary_pairs"  # サマリー内の前後の2文ごとに評価
    SUMMARY_WITH_MESSAGES = "summary_with_messages"  # サマリーとその配下のメッセージ群の塊ごとに評価
    MESSAGES_UNDER_SUMMARY = "messages_under_summary"  # サマリー配下のメッセージ群ごとに評価
    MESSAGE_WITH_BODIES = "message_with_bodies"  # メッセージとその配下のボディ群の塊ごとに評価

# 評価観点の列挙型
class EvaluationCriteria(str, Enum):
    # 文書全体の評価観点
    RHETORICAL_EXPRESSION = "rhetorical_expression"  # 修辞表現の確認
    
    # サマリー全体の評価観点
    PREVIOUS_DISCUSSION_REVIEW = "previous_discussion_review"  # 前回討議の振り返りの有無
    SCQA_PRESENCE = "scqa_presence"  # SCQAの有無
    DUPLICATE_TRANSITION_CONJUNCTIONS = "duplicate_transition_conjunctions"  # 転換の接続詞の重複利用
    
    # サマリーペアの評価観点
    CONJUNCTION_VALIDITY = "conjunction_validity"  # 前のサマリー文を踏まえたときの、接続詞の妥当性
    INAPPROPRIATE_CONJUNCTIONS = "inappropriate_conjunctions"  # サマリー文に不適切な接続詞の有無
    LOGICAL_CONSISTENCY_WITH_PREVIOUS = "logical_consistency_with_previous"  # 直前のサマリーとの論理的整合性
    
    # サマリーとメッセージの評価観点
    SEQUENTIAL_DEVELOPMENT = "sequential_development"  # 逐次的展開の評価
    
    # メッセージ群の評価観点
    CONJUNCTION_APPROPRIATENESS = "conjunction_appropriateness"  # 接続詞の適切性
    DUPLICATE_TRANSITION_WORDS = "duplicate_transition_words"  # 転換の接続詞の二重利用
    AVOID_UNNECESSARY_NUMBERING = "avoid_unnecessary_numbering"  # 無駄なナンバリングの回避
    
    # メッセージとボディの評価観点
    MESSAGE_BODY_CONSISTENCY = "message_body_consistency"  # メッセージとボディの論理的整合性

# データモデルの定義
class Body(BaseModel):
    content: str

class Message(BaseModel):
    content: str
    bodies: List[Body] = []

class Summary(BaseModel):
    content: str
    messages: List[Message] = []

class BulletPointsRequest(BaseModel):
    summaries: List[Summary]

class CriteriaResult(BaseModel):
    """評価基準の結果"""
    criteria: EvaluationCriteria
    has_issues: bool
    issues: str
    target_text: Optional[str] = None

class EvaluationResult(BaseModel):
    target_text: str
    scope: EvaluationScope
    criteria_results: List[CriteriaResult]

class EvaluationResponse(BaseModel):
    status: str
    message: str
    results: List[EvaluationResult] 