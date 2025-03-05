from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import json
import logging
import time
import asyncio
import os

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

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("bullet-points-api")

app = FastAPI()

# リクエストロギングミドルウェア（シンプル化）
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # リクエスト開始時のログは最小限に
    if request.url.path == "/process-bullet-points":
        logger.info(f"箇条書きデータのリクエストを受信: {request.method} {request.url.path}")
    
    # リクエスト処理
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # 処理完了時のログも最小限に
    if request.url.path == "/process-bullet-points":
        logger.info(f"箇条書きデータの処理完了: ステータスコード {response.status_code}, 処理時間: {process_time:.2f}秒")
    
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

# 評価範囲ごとの評価観点を定義する関数と、プロンプト読み込み関数は削除
# これらの関数はevaluation_service.pyに移動し、そこからインポートします

# サービスのインスタンス化
openai_service = AzureOpenAIService()
evaluation_service = EvaluationService(openai_service)

@app.post("/process-bullet-points", response_model=EvaluationResponse)
async def process_bullet_points(request: BulletPointsRequest):
    try:
        # 最小限のログ出力
        summaries_count = len(request.summaries)
        total_messages = sum(len(summary.messages) for summary in request.summaries)
        total_bodies = sum(sum(len(message.bodies) for message in summary.messages) for summary in request.summaries)
        
        logger.info(f"処理内容: サマリー {summaries_count}件, メッセージ {total_messages}件, ボディ {total_bodies}件")
        
        # タイトルの有無をログに出力
        if request.title:
            logger.info(f"タイトル: {request.title}")
        
        # 評価サービスを使用して評価を実行
        all_results = await evaluation_service.evaluate_document(request)
        
        # has_issues=trueの結果のみをフィルタリング
        filtered_results = []
        for result in all_results:
            # criteria_resultsの中に1つでもhas_issues=trueがあれば含める
            has_issues_criteria = [cr for cr in result.criteria_results if cr.has_issues]
            if has_issues_criteria:
                # has_issues=trueの評価結果のみを含める
                result.criteria_results = has_issues_criteria
                
                # ALL_SUMMARIESスコープの場合、タイトルに紐づける
                if result.scope == EvaluationScope.ALL_SUMMARIES and request.title:
                    logger.info(f"ALL_SUMMARIESスコープの評価結果をタイトルに紐づけます: {request.title}")
                    result.target_text = request.title
                
                filtered_results.append(result)
        
        logger.info(f"評価結果: 全{len(all_results)}件中、問題あり{len(filtered_results)}件")
        
        # レスポンスの作成
        return {
            "status": "success",
            "message": "箇条書きデータの評価が完了しました",
            "results": filtered_results
        }
    except Exception as e:
        logger.error(f"処理エラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"処理中にエラーが発生しました: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Word箇条書き処理APIへようこそ"} 