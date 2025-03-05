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
    EvaluationCriteria,
    Summary,
    Message
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
        # 各評価範囲ごとの評価関数を定義
        evaluation_functions = {
            EvaluationScope.DOCUMENT_WIDE: self._evaluate_document_wide,
            EvaluationScope.ALL_SUMMARIES: self._evaluate_all_summaries,
            EvaluationScope.SUMMARY_PAIRS: self._evaluate_summary_pairs,
            EvaluationScope.SUMMARY_WITH_MESSAGES: self._evaluate_summary_with_messages,
            EvaluationScope.MESSAGES_UNDER_SUMMARY: self._evaluate_messages_under_summary,
            EvaluationScope.MESSAGE_WITH_BODIES: self._evaluate_message_with_bodies
        }
        
        # 各評価範囲ごとに並列で評価を実行
        tasks = []
        for scope, evaluation_function in evaluation_functions.items():
            tasks.append(evaluation_function(request))
        
        # 並列実行して結果を取得
        results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        results = []
        for scope_results in results_list:
            results.extend(scope_results)
        
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
            
        # 各評価観点ごとに並列で評価を実行
        tasks = []
        for criteria in criteria_list:
            tasks.append(self._evaluate_criteria_document_wide(request, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_results in criteria_results_list:
            results.extend(criteria_results)
        
        return results
    
    async def _evaluate_criteria_document_wide(self, request: BulletPointsRequest, criteria: EvaluationCriteria, scope: EvaluationScope) -> List[EvaluationResult]:
        """
        ドキュメント全体の特定の評価観点に対する評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果のリスト
        """
        results = []
        
        # 修辞表現の評価の場合は一文ずつ評価する
        if criteria == EvaluationCriteria.RHETORICAL_EXPRESSION:
            # 一文ずつ評価するためのプロンプトを読み込む
            prompt = load_prompt(criteria, EvaluationScope.SENTENCE)
            
            # すべてのサマリーとメッセージを収集
            all_sentences = []
            
            # サマリーとメッセージの文を収集（bodyは評価対象外）
            for summary in request.summaries:
                # サマリーを文単位に分割
                summary_sentences = self._split_into_sentences(summary.content)
                for sentence in summary_sentences:
                    if sentence.strip():  # 空文字でない場合
                        all_sentences.append({
                            "text": sentence,
                            "type": "サマリー",
                            "original": summary.content
                        })
                
                for message in summary.messages:
                    # メッセージを文単位に分割
                    message_sentences = self._split_into_sentences(message.content)
                    for sentence in message_sentences:
                        if sentence.strip():  # 空文字でない場合
                            all_sentences.append({
                                "text": sentence,
                                "type": "メッセージ",
                                "original": message.content
                            })
            
            # 各文を評価（同一評価観点内は直列処理）
            for sentence_info in all_sentences:
                # 評価データを準備
                evaluation_data = sentence_info["text"]
                
                # OpenAI APIを使用して評価
                response = await self.openai_service.evaluate(prompt, evaluation_data)
                
                # レスポンスの解析
                criteria_result = self._parse_evaluation_response(response, criteria)
                
                # 問題がある場合のみ結果に追加
                if criteria_result.has_issues:
                    # 評価結果の作成
                    result = EvaluationResult(
                        target_text=sentence_info["text"],
                        scope=scope,
                        criteria_results=[criteria_result]
                    )
                    
                    results.append(result)
        else:
            # 他の評価観点は従来通りドキュメント全体で評価
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
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        テキストを文単位に分割する
        
        Args:
            text: 分割するテキスト
            
        Returns:
            文のリスト
        """
        # 句点で分割
        sentences = re.split(r'(?<=[。．！？])', text)
        # 空文字を除去
        return [s for s in sentences if s.strip()]
    
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
            
        # 各評価観点ごとに並列で評価を実行
        tasks = []
        for criteria in criteria_list:
            tasks.append(self._evaluate_criteria_all_summaries(request, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_results in criteria_results_list:
            results.extend(criteria_results)
        
        return results
    
    async def _evaluate_criteria_all_summaries(self, request: BulletPointsRequest, criteria: EvaluationCriteria, scope: EvaluationScope) -> List[EvaluationResult]:
        """
        すべてのサマリーの特定の評価観点に対する評価を行う
        
        Args:
            request: 箇条書きデータのリクエスト
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果のリスト
        """
        results = []
        
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
        
        # 各サマリーペアごとに評価タスクを作成
        tasks = []
        for i in range(1, len(request.summaries)):
            previous_summary = request.summaries[i-1]
            current_summary = request.summaries[i]
            
            # 各評価観点ごとに並列で評価を実行
            for criteria in criteria_list:
                tasks.append(self._evaluate_criteria_summary_pair(previous_summary, current_summary, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_result in criteria_results_list:
            if criteria_result:  # Noneでない場合のみ追加
                results.append(criteria_result)
        
        return results
    
    async def _evaluate_criteria_summary_pair(self, previous_summary: Summary, current_summary: Summary, criteria: EvaluationCriteria, scope: EvaluationScope) -> Optional[EvaluationResult]:
        """
        サマリーペアの特定の評価観点に対する評価を行う
        
        Args:
            previous_summary: 前のサマリー
            current_summary: 現在のサマリー
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
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
        
        return result
    
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
        
        # 各サマリーと評価観点ごとに評価タスクを作成
        tasks = []
        for i, summary in enumerate(request.summaries):
            for criteria in criteria_list:
                tasks.append(self._evaluate_criteria_summary_with_messages(summary, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_result in criteria_results_list:
            if criteria_result:  # Noneでない場合のみ追加
                results.append(criteria_result)
        
        return results
    
    async def _evaluate_criteria_summary_with_messages(self, summary: Summary, criteria: EvaluationCriteria, scope: EvaluationScope) -> Optional[EvaluationResult]:
        """
        サマリーとメッセージの特定の評価観点に対する評価を行う
        
        Args:
            summary: サマリー
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
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
        
        return result
    
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
        
        # 各サマリーと評価観点ごとに評価タスクを作成
        tasks = []
        for i, summary in enumerate(request.summaries):
            for criteria in criteria_list:
                tasks.append(self._evaluate_criteria_messages_under_summary(summary, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_result in criteria_results_list:
            if criteria_result:  # Noneでない場合のみ追加
                results.append(criteria_result)
        
        return results
    
    async def _evaluate_criteria_messages_under_summary(self, summary: Summary, criteria: EvaluationCriteria, scope: EvaluationScope) -> Optional[EvaluationResult]:
        """
        サマリー配下のメッセージの特定の評価観点に対する評価を行う
        
        Args:
            summary: サマリー
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
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
        # メッセージのテキストを結合
        message_texts = [message.content for message in summary.messages]
        target_text = "\n".join(message_texts)
        
        result = EvaluationResult(
            target_text=target_text,
            scope=scope,
            criteria_results=[criteria_result]
        )
        
        return result
    
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
        
        # 各メッセージと評価観点ごとに評価タスクを作成
        tasks = []
        for i, summary in enumerate(request.summaries):
            for j, message in enumerate(summary.messages):
                if not message.bodies:
                    continue
                
                for criteria in criteria_list:
                    tasks.append(self._evaluate_criteria_message_with_bodies(message, criteria, scope))
        
        # 並列実行して結果を取得
        criteria_results_list = await asyncio.gather(*tasks)
        
        # 結果を平坦化
        for criteria_result in criteria_results_list:
            if criteria_result:  # Noneでない場合のみ追加
                results.append(criteria_result)
        
        return results
    
    async def _evaluate_criteria_message_with_bodies(self, message: Message, criteria: EvaluationCriteria, scope: EvaluationScope) -> Optional[EvaluationResult]:
        """
        メッセージとボディの特定の評価観点に対する評価を行う
        
        Args:
            message: メッセージ
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
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
        # ボディのテキストを結合
        body_texts = [body.content for body in message.bodies]
        target_text = message.content + "\n" + "\n".join(body_texts)
        
        result = EvaluationResult(
            target_text=target_text,
            scope=scope,
            criteria_results=[criteria_result]
        )
        
        return result
    
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