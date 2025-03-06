import sys
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import json
import time
import asyncio
import traceback

# 環境変数を設定して標準出力のバッファリングを無効化
os.environ["PYTHONUNBUFFERED"] = "1"

# 標準出力のバッファリングを無効化
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
print("標準出力のバッファリングを無効化しました")

# 起動時にメッセージを表示
print("\n===== バックエンドサーバーを起動しています =====")
print(f"Python バージョン: {sys.version}")
print(f"現在の作業ディレクトリ: {os.getcwd()}")

from .models import (
    EvaluationScope,
    EvaluationCriteria,
    BulletPointsRequest,
    EvaluationResponse,
    EvaluationResult,
    CriteriaResult
)
from .services.openai_service import AzureOpenAIService
from .services.evaluation_service import EvaluationService, get_criteria_for_scope, load_prompt

# 直接標準出力を使用
print("モジュールうううのインポートが完了しました")

app = FastAPI()

# リクエストロギングミドルウェア（シンプル化）
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # リクエスト開始時のログは最小限に
    if request.url.path == "/process-bullet-points":
        print(f"\n===== 箇条書きデータのリクエストを受信: {request.method} {request.url.path} =====")
        sys.stdout.flush()  # 標準出力をフラッシュ
    
    # リクエスト処理
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # 処理完了時のログも最小限に
    if request.url.path == "/process-bullet-points":
        print(f"===== 箇条書きデータの処理完了: ステータスコード {response.status_code}, 処理時間: {process_time:.2f}秒 =====\n")
        sys.stdout.flush()  # 標準出力をフラッシュ
    
    return response

# CORSミドルウェアを追加
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://localhost:3000", "https://localhost", 
                  "http://127.0.0.1:8000", "http://localhost:8000", 
                  "http://127.0.0.1:8080", "http://localhost:8080"],  # 開発環境用の設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# サービスのインスタンス化
openai_service = AzureOpenAIService()
evaluation_service = EvaluationService(openai_service)

# 起動時にテスト出力
print("サーバー起動完了: http://127.0.0.1:8000/")
print("APIエンドポイント: http://127.0.0.1:8000/process-bullet-points")
sys.stdout.flush()  # 標準出力をフラッシュ

@app.post("/process-bullet-points")
async def process_bullet_points(request: BulletPointsRequest):
    try:
        # リクエストの詳細をログに出力
        print("\n===== 箇条書きデータの処理を開始 =====")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        summaries_count = len(request.summaries)
        total_messages = sum(len(summary.messages) for summary in request.summaries)
        total_bodies = sum(sum(len(message.bodies) for message in summary.messages) for summary in request.summaries)
        
        print(f"処理内容: サマリー {summaries_count}件, メッセージ {total_messages}件, ボディ {total_bodies}件")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # タイトルの有無をログに出力
        if request.title:
            print(f"タイトル: {request.title}")
        else:
            print("タイトルなし")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # サマリーの内容をログに出力
        for i, summary in enumerate(request.summaries):
            print(f"サマリー {i+1}: {summary.content[:50]}...")
            print(f"  メッセージ数: {len(summary.messages)}")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # 評価サービスを使用して評価を実行
        print("\n評価処理を開始します...")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        all_results = await evaluation_service.evaluate_document(request)
        print(f"評価結果の総数: {len(all_results)}件")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # 評価結果の概要を出力
        print("\n評価結果の概要:")
        for i, result in enumerate(all_results):
            issues_count = sum(1 for cr in result.criteria_results if cr.has_issues)
            print(f"結果 {i+1}: スコープ = {result.scope}, 問題数 = {issues_count}/{len(result.criteria_results)}")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # スコア計算
        try:
            print("\nスコア計算を開始します...")
            sys.stdout.flush()  # 標準出力をフラッシュ
            
            score = evaluation_service.calculate_score(all_results)
            print(f"計算されたスコア: {score}点")
            
            # スコアの型と値を確認
            print(f"スコアの型: {type(score)}, 値: {score}")
            if score is None:
                print("警告: スコアがNoneです")
                score = 100  # デフォルト値
            elif not isinstance(score, (int, float)):
                print(f"警告: スコアが数値型ではありません: {type(score)}")
                try:
                    score = int(score)  # 整数に変換を試みる
                    print(f"スコアを整数に変換しました: {score}")
                except (ValueError, TypeError):
                    print(f"スコアを整数に変換できません。デフォルト値を使用します。")
                    score = 100  # デフォルト値
            else:
                # 数値型の場合は整数に変換
                score = int(score)
                print(f"スコアを整数に変換しました: {score}")
                
            sys.stdout.flush()  # 標準出力をフラッシュ
            
        except Exception as e:
            print(f"\nスコア計算中にエラーが発生しました: {str(e)}")
            trace = traceback.format_exc()
            print(f"スコア計算の詳細なエラー情報:\n{trace}")
            score = 100  # デフォルト値を100に統一
            print(f"デフォルトスコアを使用: {score}点")
            sys.stdout.flush()  # 標準出力をフラッシュ
        
        # has_issues=trueの結果のみをフィルタリング
        print("\n評価結果をフィルタリングします...")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        filtered_results = []
        for result in all_results:
            # criteria_resultsの中に1つでもhas_issues=trueがあれば含める
            has_issues_criteria = [cr for cr in result.criteria_results if cr.has_issues]
            if has_issues_criteria:
                # has_issues=trueの評価結果のみを含める
                result.criteria_results = has_issues_criteria
                
                # ALL_SUMMARIESスコープの場合、タイトルに紐づける
                if result.scope == EvaluationScope.ALL_SUMMARIES and request.title:
                    print(f"ALL_SUMMARIESスコープの評価結果をタイトルに紐づけます: {request.title}")
                    result.target_text = request.title
                
                filtered_results.append(result)
                print(f"フィルタリング結果に追加: スコープ = {result.scope}, 対象テキスト = {result.target_text[:30]}...")
            sys.stdout.flush()  # 標準出力をフラッシュ
        
        print(f"評価結果: 全{len(all_results)}件中、問題あり{len(filtered_results)}件")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # スコアが未定義の場合は100点とする
        if score is None:
            print("スコアが未定義です。デフォルト値の100点を使用します。")
            score = 100
            sys.stdout.flush()  # 標準出力をフラッシュ
        
        # レスポンスの作成
        response_data = {
            "status": "success",
            "message": f"箇条書きデータの評価が完了しました。評価スコア: {score}点",
            "results": [
                {
                    "target_text": result.target_text,
                    "scope": result.scope.value if hasattr(result.scope, "value") else result.scope,
                    "criteria_results": [
                        {
                            "criteria": cr.criteria.value if hasattr(cr.criteria, "value") else cr.criteria,
                            "has_issues": cr.has_issues,
                            "issues": cr.issues
                        }
                        for cr in result.criteria_results
                    ]
                }
                for result in filtered_results
            ],
            "score": score  # 計算されたスコアをそのまま使用
        }
        
        # レスポンスデータをログに出力
        print("\nレスポンスデータ:")
        print(f"  status: {response_data['status']}")
        print(f"  message: {response_data['message']}")
        print(f"  results数: {len(response_data['results'])}")
        print(f"  score: {response_data['score']} (型: {type(response_data['score'])})")
        
        # JSONシリアライズのテスト
        try:
            json_data = json.dumps(response_data)
            print(f"JSONシリアライズ結果: {json_data[:200]}...")
        except Exception as e:
            print(f"JSONシリアライズエラー: {str(e)}")
            
        print("===== 箇条書きデータの処理を完了 =====\n")
        sys.stdout.flush()  # 標準出力をフラッシュ
        
        # 直接辞書を返す
        return response_data
    except Exception as e:
        print(f"\n処理エラー: {str(e)}")
        trace = traceback.format_exc()
        print(f"処理の詳細なエラー情報:\n{trace}")
        sys.stdout.flush()  # 標準出力をフラッシュ
        raise HTTPException(status_code=500, detail=f"処理中にエラーが発生しました: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Wordaaaa箇条書き!!処理APIへようこそ"} 