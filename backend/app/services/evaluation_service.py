import json
import asyncio
import re
import os
import sys
import traceback
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

# 直接標準出力を使用
print("evaluation_service: モジュールを初期化しています...")

# 評価範囲ごとの評価観点を定義
def get_criteria_for_scope(scope: EvaluationScope) -> List[EvaluationCriteria]:
    """
    評価範囲ごとの評価観点を取得する
    
    Args:
        scope: 評価範囲
        
    Returns:
        評価観点のリスト
    """
    # 評価範囲ごとの評価観点を定義
    scope_criteria_map = {
        EvaluationScope.DOCUMENT_WIDE: [
            EvaluationCriteria.RHETORICAL_EXPRESSION
        ],
        EvaluationScope.ALL_SUMMARIES: [
            EvaluationCriteria.PREVIOUS_DISCUSSION_REVIEW,
            EvaluationCriteria.SCQA_PRESENCE,
            EvaluationCriteria.DUPLICATE_TRANSITION_CONJUNCTIONS
        ],
        EvaluationScope.SUMMARY_PAIRS: [
            EvaluationCriteria.CONJUNCTION_VALIDITY,
            EvaluationCriteria.INAPPROPRIATE_CONJUNCTIONS,
            EvaluationCriteria.LOGICAL_CONSISTENCY_WITH_PREVIOUS
        ],
        EvaluationScope.SUMMARY_WITH_MESSAGES: [
            EvaluationCriteria.SEQUENTIAL_DEVELOPMENT
        ],
        EvaluationScope.MESSAGES_UNDER_SUMMARY: [
            EvaluationCriteria.CONJUNCTION_APPROPRIATENESS,
            EvaluationCriteria.DUPLICATE_TRANSITION_WORDS,
            EvaluationCriteria.AVOID_UNNECESSARY_NUMBERING
        ],
        EvaluationScope.MESSAGE_WITH_BODIES: [
            EvaluationCriteria.MESSAGE_BODY_CONSISTENCY
        ]
        # EvaluationScope.SENTENCE: [
        #     EvaluationCriteria.RHETORICAL_EXPRESSION
        # ]
    }
    
    return scope_criteria_map.get(scope, [])

# プロンプトの読み込み
def load_prompt(prompt_name: str) -> str:
    """
    プロンプトファイルを読み込む
    
    Args:
        prompt_name: プロンプト名
        
    Returns:
        プロンプトの内容
    """
    # プロンプトファイルのパスを構築
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts", f"{prompt_name}.txt")
    
    # ファイルが存在するか確認
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {prompt_path}")
    
    # ファイルを読み込む
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read()
    
    return prompt

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
        文書全体の特定の評価観点に対する評価を行う
        
        Args:
            request: リクエスト
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果のリスト
        """
        if criteria == EvaluationCriteria.RHETORICAL_EXPRESSION:
            # 一文ずつ評価するためのプロンプトを読み込む
            prompt = load_prompt("rhetorical_expression_sentence")
            
            # サマリーとメッセージのテキストのみを収集（タイトルとボディは除外）
            all_texts = []
            
            # サマリーを追加
            for summary in request.summaries:
                all_texts.append(summary.content)
                
                # メッセージを追加
                for message in summary.messages:
                    all_texts.append(message.content)
                    
                    # ボディは追加しない
            
            # 文に分割
            sentences = []
            for text in all_texts:
                sentences.extend(self._split_into_sentences(text))
            
            print(f"修辞表現の評価対象: サマリーとメッセージの文章のみ（合計 {len(sentences)} 文）")
            
            # 各文を評価
            results = []
            for sentence in sentences:
                # 空の文はスキップ
                if not sentence.strip():
                    continue
                
                # 評価データを準備
                data = {
                    "target_text": sentence
                }
                
                # 評価を実行
                response = await self.openai_service.evaluate(prompt, data)
                
                # 評価結果を解析
                criteria_result = self._parse_evaluation_response(response, criteria)
                
                # 問題がある場合のみ結果に追加
                if criteria_result.has_issues:
                    results.append(EvaluationResult(
                        target_text=sentence,
                        scope=scope,
                        criteria_results=[criteria_result]
                    ))
            
            return results
        else:
            # 他の評価観点は従来通りドキュメント全体で評価
            # プロンプトの読み込み
            prompt = load_prompt(f"{criteria.value}_document_wide")
            
            # ドキュメント全体のテキストを構築
            document_text = ""
            
            # タイトルがあれば追加
            if request.title:
                document_text += f"タイトル: {request.title}\n\n"
            
            # サマリーを追加
            for i, summary in enumerate(request.summaries):
                document_text += f"サマリー {i+1}: {summary.content}\n"
                
                # メッセージを追加
                for j, message in enumerate(summary.messages):
                    document_text += f"  メッセージ {j+1}: {message.content}\n"
                    
                    # ボディを追加
                    for k, body in enumerate(message.bodies):
                        document_text += f"    ボディ {k+1}: {body.content}\n"
            
            document_text += "\n"
            
            # 評価データを準備
            data = {
                "document": {
                    "full_text": document_text
                }
            }
            
            # 評価を実行
            response = await self.openai_service.evaluate(prompt, data)
            
            # 評価結果を解析
            criteria_result = self._parse_evaluation_response(response, criteria)
            
            # 評価結果を作成
            result = EvaluationResult(
                target_text=document_text[:200] + "...",  # 長すぎるので省略
                scope=scope,
                criteria_results=[criteria_result]
            )
            
            return [result]
    
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
            request: リクエスト
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果のリスト
        """
        # プロンプトの読み込み
        prompt = load_prompt(f"{criteria.value}_all_summaries")
        
        # すべてのサマリーテキストを収集
        all_summaries = [summary.content for summary in request.summaries]
        
        # サマリーが存在しない場合は空のリストを返す
        if not all_summaries:
            print(f"警告: サマリーが見つかりません。評価をスキップします。")
            return []
        
        # 評価データを準備
        data = {
            "summaries": {
                "texts": all_summaries
            }
        }
        
        # 評価を実行
        response = await self.openai_service.evaluate(prompt, data)
        
        # 評価結果を解析
        criteria_result = self._parse_evaluation_response(response, criteria)
        
        # 評価結果を作成
        result = EvaluationResult(
            target_text="\n".join(all_summaries),
            scope=scope,
            criteria_results=[criteria_result]
        )
        
        return [result]
    
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
        prompt = load_prompt(f"{criteria.value}_summary_pairs")
        
        # 評価データを準備
        data = {
            "previous_summary": {
                "summary_text": previous_summary.content
            },
            "current_summary": {
                "summary_text": current_summary.content
            }
        }
        
        # 評価を実行
        response = await self.openai_service.evaluate(prompt, data)
        
        # 評価結果を解析
        criteria_result = self._parse_evaluation_response(response, criteria)
        
        # 評価結果を作成
        return EvaluationResult(
            target_text=f"{previous_summary.content}\n{current_summary.content}",
            scope=scope,
            criteria_results=[criteria_result]
        )
    
    async def _evaluate_summary_with_messages(self, request: BulletPointsRequest) -> List[EvaluationResult]:
        """
        サマリーとメッセージの評価を行う
        
        Args:
            request: リクエスト
            
        Returns:
            評価結果のリスト
        """
        results = []
        
        # サマリーごとに評価
        for summary in request.summaries:
            # メッセージが存在しない場合はスキップ
            if not summary.messages:
                continue
            
            # SEQUENTIAL_DEVELOPMENTの評価観点を使用
            # 実際の論理展開タイプは_evaluate_criteria_summary_with_messagesメソッド内で判断される
            criteria = EvaluationCriteria.SEQUENTIAL_DEVELOPMENT
            
            # 評価を実行
            result = await self._evaluate_criteria_summary_with_messages(
                summary=summary,
                criteria=criteria,
                scope=EvaluationScope.SUMMARY_WITH_MESSAGES
            )
            
            if result:
                results.append(result)
        
        return results
    
    async def _evaluate_criteria_summary_with_messages(self, summary: Summary, criteria: EvaluationCriteria, scope: EvaluationScope) -> Optional[EvaluationResult]:
        """
        サマリーとメッセージの評価を行う
        
        Args:
            summary: サマリー
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
        # サマリーとメッセージの内容を取得
        summary_text = summary.content
        messages = [message.content for message in summary.messages]
        
        # メッセージが存在しない場合はスキップ
        if not messages:
            return None
        
        # 評価データを準備
        data = {
            "summary": summary_text,
            "messages": messages
        }
        
        # SUMMARY_WITH_MESSAGESカテゴリーの場合、まず論理展開のタイプを分類する
        if scope == EvaluationScope.SUMMARY_WITH_MESSAGES:
            # 分類用のプロンプトを読み込む
            classifier_prompt = load_prompt("development_type_classifier")
            
            # 分類を実行
            classification_response = await self.openai_service.evaluate(classifier_prompt, data)
            
            try:
                # 分類結果をJSONとして解析
                classification_result = json.loads(classification_response)
                development_type = classification_result.get("development_type", "sequential_development")
                
                print(f"サマリーの論理展開タイプ: {development_type}")
                print(f"分類理由: {classification_result.get('explanation', '理由なし')}")
                
                # 論理展開のタイプに応じてプロンプトを選択
                if development_type == "individual_development":
                    # 独立的論理展開の場合
                    prompt = load_prompt("individual_development_summary_with_messages")
                else:
                    # 逐次的論理展開の場合（デフォルト）
                    prompt = load_prompt("sequential_development_summary_with_messages")
            except json.JSONDecodeError:
                # 分類に失敗した場合はデフォルトのプロンプトを使用
                print(f"論理展開タイプの分類に失敗しました。デフォルトのプロンプトを使用します。")
                prompt = load_prompt("sequential_development_summary_with_messages")
        else:
            # 通常の評価観点の場合は対応するプロンプトを読み込む
            prompt = load_prompt(criteria.value)
        
        # 評価を実行
        response = await self.openai_service.evaluate(prompt, data)
        
        # 評価結果を解析
        criteria_result = self._parse_evaluation_response(response, criteria)
        
        # 評価対象のテキストを結合（サマリーとメッセージを含める）
        target_text = f"{summary_text}\n\n" + "\n".join(messages)
        
        # 評価結果を作成
        return EvaluationResult(
            target_text=target_text,
            scope=scope,
            criteria_results=[criteria_result]
        )
    
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
        サマリー配下のメッセージ群の特定の評価観点に対する評価を行う
        
        Args:
            summary: サマリー
            criteria: 評価観点
            scope: 評価範囲
            
        Returns:
            評価結果
        """
        # メッセージが存在しない場合はスキップ
        if not summary.messages:
            return None
        
        # プロンプトの読み込み
        prompt = load_prompt(f"{criteria.value}_messages_under_summary")
        
        # メッセージテキストを収集
        message_texts = [message.content for message in summary.messages]
        
        # 評価データを準備
        data = {
            "summary": summary.content,
            "messages": message_texts
        }
        
        # 評価を実行
        response = await self.openai_service.evaluate(prompt, data)
        
        # 評価結果を解析
        criteria_result = self._parse_evaluation_response(response, criteria)
        
        # 評価結果を作成
        return EvaluationResult(
            target_text=f"{summary.content}\n" + "\n".join(message_texts),
            scope=scope,
            criteria_results=[criteria_result]
        )
    
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
        # ボディが存在しない場合はスキップ
        if not message.bodies:
            return None
        
        # プロンプトの読み込み
        prompt = load_prompt(f"{criteria.value}_message_with_bodies")
        
        # ボディテキストを収集
        body_texts = [body.content for body in message.bodies]
        
        # 評価データを準備
        data = {
            "message": message.content,
            "bodies": body_texts
        }
        
        # 評価を実行
        response = await self.openai_service.evaluate(prompt, data)
        
        # 評価結果を解析
        criteria_result = self._parse_evaluation_response(response, criteria)
        
        # 評価結果を作成
        return EvaluationResult(
            target_text=f"{message.content}\n" + "\n".join(body_texts),
            scope=scope,
            criteria_results=[criteria_result]
        )
    
    def _parse_evaluation_response(self, response: str, criteria: EvaluationCriteria) -> CriteriaResult:
        """
        評価レスポンスを解析してCriteriaResultに変換する
        
        Args:
            response: 評価レスポンス
            criteria: 評価観点
            
        Returns:
            CriteriaResult
        """
        try:
            print(f"\n===== 評価レスポンス解析開始: {criteria} =====")
            print(f"レスポンス文字数: {len(response)}")
            print(f"レスポンス先頭部分: {response[:200]}...")
            
            # JSONとして解析
            try:
                result = json.loads(response)
                print(f"JSONとして解析成功: {json.dumps(result, ensure_ascii=False)[:200]}...")
            except json.JSONDecodeError as e:
                print(f"JSONデコードエラー: {str(e)}")
                # JSONブロックを抽出する試み
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1).strip()
                    print(f"JSONブロックを抽出: {json_str[:200]}...")
                    result = json.loads(json_str)
                    print("JSONブロックの解析成功")
                else:
                    print("JSONブロックが見つかりませんでした")
                    # 最初の有効なJSONオブジェクトを抽出する試み
                    json_obj_match = re.search(r'(\{.*\})', response, re.DOTALL)
                    if json_obj_match:
                        json_str = json_obj_match.group(1).strip()
                        print(f"JSONオブジェクトを抽出: {json_str[:200]}...")
                        result = json.loads(json_str)
                        print("JSONオブジェクトの解析成功")
                    else:
                        print("JSONオブジェクトが見つかりませんでした")
                        raise ValueError("有効なJSONが見つかりませんでした")
            
            # レスポンスの詳細をログに出力
            print(f"評価レスポンス解析: criteria={criteria}, has_issues={result.get('has_issues', False)}")
            
            # 問題があるかどうかを取得
            has_issues = result.get("has_issues", False)
            if isinstance(has_issues, str):
                has_issues = has_issues.lower() == "true"
            
            # 問題の詳細を取得
            issues = result.get("issues", "問題なし")
            if not issues or issues == "":
                issues = "問題なし"
            
            print(f"解析結果: has_issues={has_issues}, issues={issues[:100]}...")
            print(f"===== 評価レスポンス解析終了: {criteria} =====\n")
            
            return CriteriaResult(
                criteria=criteria,
                has_issues=has_issues,
                issues=issues
            )
        except json.JSONDecodeError as e:
            print(f"評価レスポンスのJSONデコードエラー: {str(e)}")
            print(f"不正なレスポンス: {response}")
            return CriteriaResult(
                criteria=criteria,
                has_issues=False,
                issues="評価レスポンスの解析に失敗しました"
            )
        except Exception as e:
            print(f"評価レスポンスの解析エラー: {str(e)}")
            trace = traceback.format_exc()
            print(f"解析の詳細なエラー情報:\n{trace}")
            return CriteriaResult(
                criteria=criteria,
                has_issues=False,
                issues=f"評価レスポンスの解析中にエラーが発生しました: {str(e)}"
            )

    def calculate_score(self, all_results: List[EvaluationResult]) -> int:
        """
        評価結果に基づいてスコアを計算する
        
        Args:
            all_results: すべての評価結果
            
        Returns:
            スコア（0-100）
        """
        try:
            # 直接標準出力にも出力
            print("\n===== スコア計算開始 =====")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            print(f"評価結果の数: {len(all_results)}")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 評価結果の詳細を出力
            for i, result in enumerate(all_results):
                print(f"評価結果 {i+1}:")
                print(f"  スコープ: {result.scope}")
                print(f"  対象テキスト: {result.target_text[:50]}...")
                print(f"  評価観点の数: {len(result.criteria_results)}")
                for j, cr in enumerate(result.criteria_results):
                    print(f"    評価観点 {j+1}: {cr.criteria}, 問題あり = {cr.has_issues}")
                    if cr.has_issues:
                        print(f"      問題内容: {cr.issues[:100]}...")
                sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 満点は100点
            base_score = 100
            print(f"基本スコア: {base_score}点")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 評価軸の一覧（EvaluationCriteriaのすべての値）
            all_criteria = [
                EvaluationCriteria.RHETORICAL_EXPRESSION,
                EvaluationCriteria.PREVIOUS_DISCUSSION_REVIEW,
                EvaluationCriteria.SCQA_PRESENCE,
                EvaluationCriteria.DUPLICATE_TRANSITION_CONJUNCTIONS,
                EvaluationCriteria.CONJUNCTION_VALIDITY,
                EvaluationCriteria.INAPPROPRIATE_CONJUNCTIONS,
                EvaluationCriteria.LOGICAL_CONSISTENCY_WITH_PREVIOUS,
                EvaluationCriteria.SEQUENTIAL_DEVELOPMENT,
                EvaluationCriteria.CONJUNCTION_APPROPRIATENESS,
                EvaluationCriteria.DUPLICATE_TRANSITION_WORDS,
                EvaluationCriteria.AVOID_UNNECESSARY_NUMBERING,
                EvaluationCriteria.MESSAGE_BODY_CONSISTENCY
            ]
            
            print(f"評価軸の数: {len(all_criteria)}")
            print("評価軸一覧:")
            for i, criteria in enumerate(all_criteria):
                print(f"  {i+1}. {criteria}")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 各評価観点ごとに問題があるかどうかを確認
            criteria_with_issues = set()
            
            # 各評価結果を処理
            print("\n評価結果から問題のある評価観点を抽出:")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            for i, result in enumerate(all_results):
                print(f"評価結果 {i+1} (スコープ: {result.scope}):")
                for j, criteria_result in enumerate(result.criteria_results):
                    print(f"  評価観点 {j+1}: {criteria_result.criteria}, 問題あり = {criteria_result.has_issues}")
                    if criteria_result.has_issues:
                        # 問題がある評価観点を記録
                        criteria_with_issues.add(criteria_result.criteria)
                        print(f"    → 問題のある評価観点として追加: {criteria_result.criteria}")
                sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 問題がある評価観点の数
            num_criteria_with_issues = len(criteria_with_issues)
            print(f"\n問題のある評価観点の数: {num_criteria_with_issues}")
            print("問題のある評価観点一覧:")
            for i, criteria in enumerate(criteria_with_issues):
                print(f"  {i+1}. {criteria}")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 問題がある評価観点ごとに8点減点
            deduction = num_criteria_with_issues * 8
            print(f"\n減点計算: {num_criteria_with_issues} × 8 = {deduction}点")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # スコアを計算（最低10点）
            final_score = max(10, base_score - deduction)
            print(f"スコア計算: {base_score} - {deduction} = {base_score - deduction}")
            print(f"最終スコア (最低10点): {final_score}点")
            print("===== スコア計算終了 =====\n")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            # 整数値に変換して返す
            return int(final_score)
        except Exception as e:
            print(f"\nスコア計算中にエラーが発生しました: {str(e)}")
            trace = traceback.format_exc()
            print(f"スコア計算の詳細なエラー情報:\n{trace}")
            print("デフォルトスコア100を返します")
            sys.stdout.flush()  # 標準出力をフラッシュ
            # エラーが発生した場合はデフォルト値として100を返す
            return 100 