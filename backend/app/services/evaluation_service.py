import logging
import json
import asyncio
import re
import os
from typing import List, Dict, Any, Optional

from ..models import (
    BulletPointsRequest, 
    EvaluationResult, 
    CriteriaResult,
    EvaluationScope,
    EvaluationCriteria
)
# 循環インポートを解決するため、main.pyからのインポートを削除
# from ..main import get_criteria_for_scope, load_prompt

logger = logging.getLogger("bullet-points-api")

# 評価範囲ごとの評価観点を定義
def get_criteria_for_scope(scope: EvaluationScope) -> List[EvaluationCriteria]:
    """
    評価範囲に応じた評価観点のリストを返す
    
    Args:
        scope: 評価範囲
        
    Returns:
        評価観点のリスト
    """
    criteria_map = {
        EvaluationScope.DOCUMENT_WIDE: [
            EvaluationCriteria.RHETORICAL_EXPRESSION,  # 修辞表現の確認
        ],
        EvaluationScope.ALL_SUMMARIES: [
            EvaluationCriteria.PREVIOUS_DISCUSSION_REVIEW,  # 前回討議の振り返りの有無
            EvaluationCriteria.SCQA_PRESENCE,  # SCQAの有無
            EvaluationCriteria.DUPLICATE_TRANSITION_CONJUNCTIONS,  # 転換の接続詞の重複利用
        ],
        EvaluationScope.SUMMARY_PAIRS: [
            EvaluationCriteria.CONJUNCTION_VALIDITY,  # 前のサマリー文を踏まえたときの、接続詞の妥当性
            EvaluationCriteria.INAPPROPRIATE_CONJUNCTIONS,  # サマリー文に不適切な接続詞の有無
            EvaluationCriteria.LOGICAL_CONSISTENCY_WITH_PREVIOUS,  # 直前のサマリーとの論理的整合性
        ],
        EvaluationScope.SUMMARY_WITH_MESSAGES: [
            EvaluationCriteria.SEQUENTIAL_DEVELOPMENT,  # 逐次的展開の評価
        ],
        EvaluationScope.MESSAGES_UNDER_SUMMARY: [
            EvaluationCriteria.CONJUNCTION_APPROPRIATENESS,  # 接続詞の適切性
            EvaluationCriteria.DUPLICATE_TRANSITION_WORDS,  # 転換の接続詞の二重利用
            EvaluationCriteria.AVOID_UNNECESSARY_NUMBERING,  # 無駄なナンバリングの回避
        ],
        EvaluationScope.MESSAGE_WITH_BODIES: [
            EvaluationCriteria.MESSAGE_BODY_CONSISTENCY,  # メッセージとボディの論理的整合性
        ],
    }
    
    return criteria_map.get(scope, [])

# プロンプトの読み込み
def load_prompt(criteria: EvaluationCriteria, scope: EvaluationScope):
    """
    評価観点と評価範囲に応じたプロンプトを読み込む
    
    Args:
        criteria: 評価観点
        scope: 評価範囲
        
    Returns:
        プロンプトの文字列
    """
    # プロンプトファイルのパスを構築
    prompt_filename = f"{criteria.value}_{scope.value}.txt"
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", prompt_filename)
    
    # プロンプトファイルが存在しない場合はデフォルトのプロンプトを使用
    if not os.path.exists(prompt_path):
        prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", "default_prompt.txt")
    
    # プロンプトを読み込む
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

class EvaluationService:
    def __init__(self, openai_service):
        self.openai_service = openai_service
    
    async def evaluate_document(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        ドキュメント全体を評価する
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        # 評価結果のリスト
        results = []
        
        # ドキュメント全体の評価
        document_wide_results = await self._evaluate_document_wide(request)
        results.extend(document_wide_results)
        
        # すべてのサマリーの評価
        all_summaries_results = await self._evaluate_all_summaries(request)
        results.extend(all_summaries_results)
        
        # サマリーペアの評価
        summary_pairs_results = await self._evaluate_summary_pairs(request)
        results.extend(summary_pairs_results)
        
        # サマリーとメッセージの評価
        summary_with_messages_results = await self._evaluate_summary_with_messages(request)
        results.extend(summary_with_messages_results)
        
        # サマリー配下のメッセージの評価
        messages_under_summary_results = await self._evaluate_messages_under_summary(request)
        results.extend(messages_under_summary_results)
        
        # メッセージとボディの評価
        message_with_bodies_results = await self._evaluate_message_with_bodies(request)
        results.extend(message_with_bodies_results)
        
        return results
    
    async def _evaluate_document_wide(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        ドキュメント全体の評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.DOCUMENT_WIDE
        criteria_list = get_criteria_for_scope(scope)
        
        # サマリーとメッセージが存在しない場合は評価しない
        if not request.summaries:
            return results
            
        for criteria in criteria_list:
            # プロンプトの読み込み
            prompt = load_prompt(criteria, scope)
            
            # ドキュメント全体のテキストを構築
            all_text = []
            
            # すべてのサマリーとメッセージを収集
            for summary in request.summaries:
                all_text.append(f"【サマリー】{summary.content}")
                
                for message in summary.messages:
                    all_text.append(f"【メッセージ】{message.content}")
                    
                    for body in message.bodies:
                        all_text.append(f"【ボディ】{body.content}")
            
            # 全テキストを結合
            full_document_text = "\n".join(all_text)
            
            # 評価データを準備
            evaluation_data = {
                "document": {
                    "full_text": full_document_text,
                    "summaries_count": len(request.summaries),
                    "total_items_count": len(all_text)
                }
            }
            
            # OpenAI APIを使用して評価
            response = await self.openai_service.evaluate(prompt, evaluation_data)
            
            # レスポンスの解析
            criteria_result = self._parse_evaluation_response(response, criteria)
            
            # 評価結果の作成
            target_text = " ".join(all_text)
            # 末尾の制御文字を削除
            target_text = target_text.rstrip('\u0005')
                
            result = EvaluationResult(
                target_text=target_text,
                scope=scope,
                criteria_results=[criteria_result]
            )
            
            results.append(result)
        
        return results
    
    async def _evaluate_all_summaries(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        すべてのサマリーの評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.ALL_SUMMARIES
        criteria_list = get_criteria_for_scope(scope)
        
        # サマリーが存在しない場合は評価しない
        if not request.summaries:
            return results
            
        for criteria in criteria_list:
            # プロンプトの読み込み
            prompt = load_prompt(criteria, scope)
            
            # すべてのサマリーテキストを収集
            all_summaries = []
            for summary in request.summaries:
                all_summaries.append(summary.content)
            
            # 評価対象のデータを準備
            evaluation_data = {
                "summaries": {
                    "texts": all_summaries,
                    "count": len(all_summaries)
                }
            }
            
            # OpenAI APIを使用して評価
            response = await self.openai_service.evaluate(prompt, evaluation_data)
            
            # レスポンスの解析
            criteria_result = self._parse_evaluation_response(response, criteria)
            
            # 評価結果の作成
            target_text = "\n".join(all_summaries)
            # 末尾の制御文字を削除
            target_text = target_text.rstrip('\u0005')
                
            result = EvaluationResult(
                target_text=target_text,
                scope=scope,
                criteria_results=[criteria_result]
            )
            
            results.append(result)
        
        return results
    
    async def _evaluate_summary_pairs(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        サマリーペアの評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.SUMMARY_PAIRS
        criteria_list = get_criteria_for_scope(scope)
        
        # サマリーが2つ以上ある場合のみ評価
        if len(request.summaries) < 2:
            return results
        
        for i in range(1, len(request.summaries)):
            previous_summary = request.summaries[i-1]
            current_summary = request.summaries[i]
            
            for criteria in criteria_list:
                # プロンプトの読み込み
                prompt = load_prompt(criteria, scope)
                
                # 評価対象のデータを準備
                evaluation_data = {
                    "previous_summary": {
                        "summary_text": previous_summary.content
                    },
                    "current_summary": {
                        "summary_text": current_summary.content
                    }
                }
                
                # OpenAI APIを使用して評価
                response = await self.openai_service.evaluate(prompt, evaluation_data)
                
                # レスポンスの解析
                criteria_result = self._parse_evaluation_response(response, criteria)
                
                # 評価結果の作成
                target_text = current_summary.content
                # 末尾の制御文字を削除
                target_text = target_text.rstrip('\u0005')
                    
                result = EvaluationResult(
                    target_text=target_text,
                    scope=scope,
                    criteria_results=[criteria_result]
                )
                
                results.append(result)
        
        return results
    
    async def _evaluate_summary_with_messages(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        サマリーとメッセージの評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.SUMMARY_WITH_MESSAGES
        criteria_list = get_criteria_for_scope(scope)
        
        for i, summary in enumerate(request.summaries):
            for criteria in criteria_list:
                # プロンプトの読み込み
                prompt = load_prompt(criteria, scope)
                
                # 評価対象のデータを準備
                evaluation_data = {
                    "summary": {
                        "summary_text": summary.content,
                        "messages": [
                            {
                                "message_text": message.content
                            } for message in summary.messages
                        ]
                    }
                }
                
                # OpenAI APIを使用して評価
                response = await self.openai_service.evaluate(prompt, evaluation_data)
                
                # レスポンスの解析
                criteria_result = self._parse_evaluation_response(response, criteria)
                
                # 評価結果の作成
                result = EvaluationResult(
                    target_text=summary.content,
                    scope=scope,
                    criteria_results=[criteria_result]
                )
                
                results.append(result)
        
        return results
    
    async def _evaluate_messages_under_summary(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        サマリー配下のメッセージの評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.MESSAGES_UNDER_SUMMARY
        criteria_list = get_criteria_for_scope(scope)
        
        for i, summary in enumerate(request.summaries):
            for criteria in criteria_list:
                # プロンプトの読み込み
                prompt = load_prompt(criteria, scope)
                
                # 評価対象のデータを準備
                evaluation_data = {
                    "summary": {
                        "summary_text": summary.content,
                        "messages": [
                            {
                                "message_text": message.content
                            } for message in summary.messages
                        ]
                    }
                }
                
                # OpenAI APIを使用して評価
                response = await self.openai_service.evaluate(prompt, evaluation_data)
                
                # レスポンスの解析
                criteria_result = self._parse_evaluation_response(response, criteria)
                
                # 評価結果の作成
                result = EvaluationResult(
                    target_text=summary.content,
                    scope=scope,
                    criteria_results=[criteria_result]
                )
                
                results.append(result)
        
        return results
    
    async def _evaluate_message_with_bodies(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        メッセージとボディの評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        scope = EvaluationScope.MESSAGE_WITH_BODIES
        criteria_list = get_criteria_for_scope(scope)
        
        for i, summary in enumerate(request.summaries):
            for j, message in enumerate(summary.messages):
                if not message.bodies:
                    continue
                
                for criteria in criteria_list:
                    # プロンプトの読み込み
                    prompt = load_prompt(criteria, scope)
                    
                    # 評価対象のデータを準備
                    evaluation_data = {
                        "message": {
                            "message_text": message.content,
                            "bodies": [{"body_text": body.content} for body in message.bodies]
                        }
                    }
                    
                    # OpenAI APIを使用して評価
                    response = await self.openai_service.evaluate(prompt, evaluation_data)
                    
                    # レスポンスの解析
                    criteria_result = self._parse_evaluation_response(response, criteria)
                    
                    # 評価結果の作成
                    target_text = message.content
                    # 末尾の制御文字を削除
                    target_text = target_text.rstrip('\u0005')
                        
                    result = EvaluationResult(
                        target_text=target_text,
                        scope=scope,
                        criteria_results=[criteria_result]
                    )
                    
                    results.append(result)
        
        return results
    
    def _parse_evaluation_response(self, response: str, criteria: EvaluationCriteria) -> CriteriaResult:
        """
        評価レスポンスを解析する
        
        Args:
            response: OpenAI APIからのレスポンス
            criteria: 評価観点
            
        Returns:
            評価結果
        """
        try:
            # レスポンスをJSONとして解析
            result = json.loads(response)
            
            # レスポンスの詳細をログに出力
            logger.info(f"評価レスポンス解析: criteria={criteria}, has_issues={result.get('has_issues', False)}")
            logger.info(f"評価レスポンス全文: {response}")
            
            # 問題があるかどうかを取得
            has_issues = result.get("has_issues", False)
            
            # 問題の詳細を取得
            issues = result.get("issues", "")
            if not issues and "details" in result:
                issues = result.get("details", "")
            
            # 評価結果を作成
            return CriteriaResult(
                criteria=criteria,
                has_issues=has_issues,
                issues=issues
            )
        except json.JSONDecodeError as e:
            logger.error(f"評価レスポンスのJSONデコードエラー: {str(e)}")
            logger.error(f"不正なレスポンス: {response}")
            return CriteriaResult(
                criteria=criteria,
                has_issues=False,
                issues="評価レスポンスの解析に失敗しました"
            )
        except Exception as e:
            logger.error(f"評価レスポンスの解析エラー: {str(e)}")
            return CriteriaResult(
                criteria=criteria,
                has_issues=False,
                issues=f"評価レスポンスの解析中にエラーが発生しました: {str(e)}"
            ) 