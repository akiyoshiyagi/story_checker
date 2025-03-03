import os
import logging
import json
from typing import Dict, List, Any, Optional
import asyncio
import time
import random
import re
import openai

# Azure OpenAI SDKをインポート
from openai import AsyncAzureOpenAI
from ..config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT_NAME
)

logger = logging.getLogger("bullet-points-api")

class AzureOpenAIService:
    def __init__(self):
        # Azure OpenAI APIの設定
        self.client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        # デプロイメント名
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
        
        # リトライ設定
        self.max_retries = 3
        self.retry_delay = 2  # 秒
    
    async def evaluate(self, prompt: str, data: Dict[str, Any]) -> str:
        """
        プロンプトとデータを使用して評価を行う
        
        Args:
            prompt: プロンプトテンプレート
            data: 評価データ
            
        Returns:
            評価結果の文字列
        """
        # プロンプトにデータを埋め込む
        formatted_prompt = self._format_prompt(prompt, data)
        
        # フォーマットされたプロンプトをログに出力
        logger.info(f"フォーマットされたプロンプト: {formatted_prompt[:500]}...")
        logger.info(f"評価データ: {json.dumps(data, ensure_ascii=False)[:500]}...")
        
        # 評価を実行
        return await self.evaluate_text(formatted_prompt)
    
    def _format_prompt(self, prompt: str, data: Dict[str, Any]) -> str:
        """
        プロンプトにデータを埋め込む
        
        Args:
            prompt: プロンプトテンプレート
            data: 埋め込むデータ
            
        Returns:
            フォーマットされたプロンプト
        """
        # 評価対象のテキストを抽出
        evaluation_text = self._extract_evaluation_text(data)
        
        # プロンプトにテキストを埋め込む（JSONではなく評価対象のテキストを直接埋め込む）
        formatted_prompt = prompt.replace("{{data}}", evaluation_text)
        
        return formatted_prompt
    
    def _extract_evaluation_text(self, data: Dict[str, Any]) -> str:
        """
        評価対象のテキストを抽出する
        
        Args:
            data: 評価データ
            
        Returns:
            評価対象のテキスト
        """
        # ドキュメント全体の評価の場合
        if "document" in data and "full_text" in data["document"]:
            return data["document"]["full_text"]
        
        # すべてのサマリーの評価の場合
        if "summaries" in data:
            if isinstance(data["summaries"], dict) and "texts" in data["summaries"]:
                return "\n\n".join(data["summaries"]["texts"])
            elif isinstance(data["summaries"], list):
                return "\n\n".join(data["summaries"])
        
        # サマリーペアの評価の場合
        if "previous_summary" in data and "current_summary" in data:
            previous = data["previous_summary"].get("summary_text", "")
            current = data["current_summary"].get("summary_text", "")
            return f"前のサマリー:\n{previous}\n\n現在のサマリー:\n{current}"
        
        # サマリーとメッセージの評価の場合
        if "summary" in data:
            summary_text = data["summary"].get("summary_text", "")
            messages = data["summary"].get("messages", [])
            
            result = f"サマリー:\n{summary_text}\n\nメッセージ:"
            for i, msg in enumerate(messages):
                result += f"\n{i+1}. {msg.get('message_text', '')}"
            
            return result
        
        # メッセージとボディの評価の場合
        if "message" in data:
            message_text = data["message"].get("message_text", "")
            bodies = data["message"].get("bodies", [])
            
            result = f"メッセージ:\n{message_text}\n\nボディ:"
            for i, body in enumerate(bodies):
                result += f"\n{i+1}. {body.get('body_text', '')}"
            
            return result
        
        # その他の場合はJSON文字列をそのまま返す
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    async def evaluate_text(self, prompt_with_text: str) -> str:
        """
        テキストを評価する
        
        Args:
            prompt_with_text: プロンプトとテキストを含む文字列
            
        Returns:
            評価結果の文字列
        """
        # リトライカウンタ
        retry_count = 0
        
        while True:
            try:
                # システムメッセージとユーザーメッセージを設定
                messages = [
                    {"role": "system", "content": "あなたは戦略コンサルティングの専門家であり、ストーリーテリングと論理構成の評価者です。必ず有効なJSONを出力してください。"},
                    {"role": "user", "content": prompt_with_text}
                ]
                
                # リクエストの詳細をログに出力
                logger.info(f"Azure OpenAI APIにリクエスト送信: {len(prompt_with_text)}文字")
                logger.debug(f"リクエストメッセージ: {json.dumps(messages, ensure_ascii=False)}")
                # プロンプト全文をログに出力
                logger.info(f"リクエスト全文: {prompt_with_text[:1000]}...")
                
                # Azure OpenAI APIを呼び出す（新しいバージョンのSDKに対応）
                response = await self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                )
                
                # レスポンスからテキストを取得
                result_text = response.choices[0].message.content
                
                # レスポンスの詳細をログに記録
                logger.info(f"evaluate_text: Azure OpenAI APIからのレスポンス: {len(result_text)}文字")
                logger.info(f"レスポンス内容: {result_text}")
                
                # 制御文字を削除
                result_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', result_text)
                
                # JSONの形式を確認し、必要に応じて修正
                try:
                    # JSONとして解析できるか確認
                    json_data = json.loads(result_text)
                    
                    # 必要なフィールドが含まれているか確認
                    if "has_issues" not in json_data and "issues_found" not in json_data:
                        json_data["has_issues"] = False
                    
                    if "issues" not in json_data and "details" not in json_data:
                        json_data["issues"] = "問題なし"
                    
                    # 整形されたJSONを返す
                    return json.dumps(json_data, ensure_ascii=False)
                except json.JSONDecodeError as e:
                    # JSONとして解析できない場合は、エラーログを出力して修正を試みる
                    logger.warning(f"APIからの応答がJSONとして解析できませんでした: {str(e)}")
                    
                    # JSONブロックを抽出する試み
                    json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1).strip()
                        logger.debug(f"JSONブロックを抽出しました: {json_str[:100]}...")
                        try:
                            json_data = json.loads(json_str)
                            # 必要なフィールドが含まれているか確認
                            if "has_issues" not in json_data and "issues_found" not in json_data:
                                json_data["has_issues"] = False
                            
                            if "issues" not in json_data and "details" not in json_data:
                                json_data["issues"] = "問題なし"
                            
                            # 整形されたJSONを返す
                            return json.dumps(json_data, ensure_ascii=False)
                        except json.JSONDecodeError:
                            logger.warning("JSONブロック内のJSONとして解析できませんでした。")
                    
                    # 最初の有効なJSONオブジェクトを抽出する試み
                    try:
                        # 最初の { から最後の } までを抽出
                        json_obj_match = re.search(r'(\{.*\})', result_text, re.DOTALL)
                        if json_obj_match:
                            json_str = json_obj_match.group(1).strip()
                            logger.debug(f"JSONオブジェクトを抽出しました: {json_str[:100]}...")
                            json_data = json.loads(json_str)
                            # 必要なフィールドが含まれているか確認
                            if "has_issues" not in json_data and "issues_found" not in json_data:
                                json_data["has_issues"] = False
                            
                            if "issues" not in json_data and "details" not in json_data:
                                json_data["issues"] = "問題なし"
                            
                            # 整形されたJSONを返す
                            return json.dumps(json_data, ensure_ascii=False)
                    except Exception as e:
                        logger.warning(f"JSONオブジェクトの抽出に失敗しました: {str(e)}")
                    
                    # デフォルトのJSONを返す
                    default_json = {
                        "has_issues": False,
                        "issues": "JSONの解析に失敗したため、評価できませんでした。"
                    }
                    return json.dumps(default_json, ensure_ascii=False)
                
            except Exception as e:
                # エラーログを出力
                logger.error(f"Azure OpenAI API呼び出しエラー: {str(e)}")
                
                # リトライカウンタをインクリメント
                retry_count += 1
                
                if retry_count < self.max_retries:
                    # リトライ前に少し待機（ジッターを追加）
                    delay = self.retry_delay * (1 + random.random())
                    logger.info(f"リトライ {retry_count}/{self.max_retries} を {delay:.2f}秒後に実行します")
                    await asyncio.sleep(delay)
                else:
                    # 最大リトライ回数に達した場合はエラーを返す
                    logger.error(f"最大リトライ回数 ({self.max_retries}) に達しました")
                    return """{"has_issues": false, "issues": "評価中にAPIエラーが発生したため評価できませんでした。"}"""
        
        # 念のため（ここには到達しないはず）
        return """{"has_issues": false, "issues": "不明なエラーのため評価できませんでした。"}"""
    
    async def evaluate_summary(self, summary: str, messages: List[str], prompt: str) -> Dict[str, Any]:
        """
        サマリーとメッセージを評価する（後方互換性のため）
        
        Args:
            summary: 評価対象のサマリー文
            messages: サマリーに関連するメッセージのリスト
            prompt: 評価用のプロンプト
            
        Returns:
            評価結果を含む辞書
        """
        # 新しいevaluate_textメソッドを使用
        result_json = await self.evaluate_text(f"{prompt}\n\nサマリー: {summary}\n\nメッセージ: {' '.join(messages)}")
        
        try:
            # JSONとして解析
            result_data = json.loads(result_json)
            
            # 古いフォーマットに変換
            return {
                "summary": json.dumps(result_data, ensure_ascii=False),
                "has_issues": result_data.get("has_issues", False) or result_data.get("issues_found", False),
                "issues": result_data.get("issues", "問題なし") if result_data.get("issues", "") != "" else "問題なし"
            }
        except json.JSONDecodeError:
            # JSONとして解析できない場合
            return {
                "summary": result_json,
                "has_issues": "問題なし" not in result_json,
                "issues": result_json.replace(summary, "").replace("問題点：", "").strip() or "問題なし"
            } 