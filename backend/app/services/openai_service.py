import os
import json
from typing import Dict, List, Any, Optional
import asyncio
import time
import random
import re
import openai
import sys
import traceback

# Azure OpenAI SDKをインポート
from openai import AsyncAzureOpenAI
from ..config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT_NAME
)

# 直接標準出力を使用
print("openai_service: モジュールを初期化しています...")

class AzureOpenAIService:
    def __init__(self):
        # Azure OpenAI APIの設定
        self.api_key = AZURE_OPENAI_API_KEY
        self.endpoint = AZURE_OPENAI_ENDPOINT
        self.api_version = AZURE_OPENAI_API_VERSION
        self.deployment_name = AZURE_OPENAI_DEPLOYMENT_NAME
        
        # クライアントの初期化
        self.client = AsyncAzureOpenAI(
            api_key=self.api_key,
            api_version=self.api_version,
            azure_endpoint=self.endpoint
        )
        
        print(f"Azure OpenAI API設定: エンドポイント={self.endpoint}, デプロイメント名={self.deployment_name}")
    
    async def evaluate(self, prompt: str, data: Dict[str, Any]) -> str:
        """
        プロンプトとデータを使用して評価を実行する
        
        Args:
            prompt: 評価用のプロンプト
            data: 評価対象のデータ
            
        Returns:
            評価結果のテキスト
        """
        # プロンプトにデータを埋め込む
        formatted_prompt = self._format_prompt(prompt, data)
        
        # 評価テキストを抽出
        evaluation_text = self._extract_evaluation_text(data)
        
        # 最終的なプロンプトを作成
        final_prompt = f"{formatted_prompt}\n\n{evaluation_text}"
        
        # OpenAI APIを使用して評価
        return await self.evaluate_text(final_prompt)
    
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
        # データの種類に応じて評価対象のテキストを抽出
        if "target_text" in data:
            return f"評価対象テキスト: {data['target_text']}"
        elif "previous_summary" in data and "current_summary" in data:
            return f"前のサマリー: {data['previous_summary']['summary_text']}\n\n現在のサマリー: {data['current_summary']['summary_text']}"
        elif "summary" in data and "messages" in data:
            messages_text = "\n".join([f"- {msg}" for msg in data["messages"]])
            return f"サマリー: {data['summary']}\n\nメッセージ:\n{messages_text}"
        elif "message" in data and "bodies" in data:
            bodies_text = "\n".join([f"- {body}" for body in data["bodies"]])
            return f"メッセージ: {data['message']}\n\nボディ:\n{bodies_text}"
        elif "summaries" in data:
            summaries_text = "\n\n".join([f"サマリー {i+1}: {summary}" for i, summary in enumerate(data["summaries"])])
            return f"サマリー一覧:\n{summaries_text}"
        else:
            # データをJSON文字列に変換
            return f"評価データ: {json.dumps(data, ensure_ascii=False)}"
    
    async def evaluate_text(self, prompt_with_text: str) -> str:
        """
        テキストを評価する
        
        Args:
            prompt_with_text: プロンプトとテキストを含む文字列
            
        Returns:
            評価結果のJSON文字列
        """
        retry_count = 0
        max_retries = 3
        
        while True:
            try:
                print(f"\n===== OpenAI API リクエスト開始 (試行 {retry_count + 1}/{max_retries}) =====")
                print(f"プロンプト文字数: {len(prompt_with_text)}")
                print(f"プロンプト先頭部分: {prompt_with_text[:200]}...")
                
                # メッセージを作成
                messages = [
                    {"role": "system", "content": "あなたは評価を行うAIアシスタントです。"},
                    {"role": "user", "content": prompt_with_text}
                ]
                
                # リクエストの詳細をログに出力
                print(f"Azure OpenAI APIにリクエスト送信: {len(prompt_with_text)}文字")
                
                # 開始時間を記録
                start_time = time.time()
                
                # Azure OpenAI APIを呼び出す（新しいバージョンのSDKに対応）
                response = await self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=2000,
                    top_p=0.95,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stop=None
                )
                
                # 終了時間を記録
                end_time = time.time()
                elapsed_time = end_time - start_time
                
                # レスポンスからテキストを抽出
                result_text = response.choices[0].message.content
                
                # レスポンスの詳細をログに記録
                print(f"Azure OpenAI APIからのレスポンス: {len(result_text)}文字, 処理時間: {elapsed_time:.2f}秒")
                print(f"レスポンス先頭部分: {result_text[:200]}...")
                
                # 制御文字を削除
                result_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', result_text)
                
                # JSONとして解析できるか確認
                try:
                    # JSONとして解析
                    json_data = json.loads(result_text)
                    print("レスポンスをJSONとして正常に解析できました")
                    return json.dumps(json_data, ensure_ascii=False)
                    
                except json.JSONDecodeError as e:
                    # JSONとして解析できない場合は、エラーログを出力して修正を試みる
                    print(f"APIからの応答がJSONとして解析できませんでした: {str(e)}")
                    
                    # JSONブロックを抽出する試み
                    json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1).strip()
                        print(f"JSONブロックを抽出しました: {json_str[:100]}...")
                        try:
                            json_data = json.loads(json_str)
                            print("JSONブロックを正常に解析できました")
                            return json.dumps(json_data, ensure_ascii=False)
                        except json.JSONDecodeError:
                            print("JSONブロック内のJSONとして解析できませんでした。")
                    
                    # 最初の有効なJSONオブジェクトを抽出する試み
                    try:
                        json_obj_match = re.search(r'(\{.*\})', result_text, re.DOTALL)
                        if json_obj_match:
                            json_str = json_obj_match.group(1).strip()
                            print(f"JSONオブジェクトを抽出しました: {json_str[:100]}...")
                            json_data = json.loads(json_str)
                            # 必要なフィールドが含まれているか確認
                            if "has_issues" in json_data:
                                print("有効なJSONオブジェクトを抽出しました")
                                return json.dumps(json_data, ensure_ascii=False)
                    except Exception as e:
                        print(f"JSONオブジェクトの抽出に失敗しました: {str(e)}")
                    
                    # デフォルトのJSONを返す
                    print("デフォルトのJSONを返します")
                    return """{"has_issues": false, "issues": "評価結果の解析に失敗しました。"}"""
                
                print(f"===== OpenAI API リクエスト終了 =====\n")
                
            except Exception as e:
                # エラーログを出力
                print(f"Azure OpenAI API呼び出しエラー: {str(e)}")
                trace = traceback.format_exc()
                print(f"API呼び出しの詳細なエラー情報:\n{trace}")
                
                # リトライカウンタをインクリメント
                retry_count += 1
                
                if retry_count < max_retries:
                    # リトライ前に少し待機（ジッターを追加）
                    delay = 2 * (1 + random.random())
                    print(f"リトライ {retry_count}/{max_retries} を {delay:.2f}秒後に実行します")
                    await asyncio.sleep(delay)
                else:
                    # 最大リトライ回数に達した場合はエラーを返す
                    print(f"最大リトライ回数 ({max_retries}) に達しました")
                    return """{"has_issues": false, "issues": "評価中にAPIエラーが発生したため評価できませんでした。"}"""
    
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