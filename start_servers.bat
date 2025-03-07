@echo off
chcp 65001 > nul
echo ストーリーチェッカーのサーバーを起動しています...

echo バックエンドサーバーを起動しています...
start cmd /k "chcp 65001 > nul && cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo フロントエンドサーバーを起動しています...
start cmd /k "chcp 65001 > nul && cd frontend && npm start"

echo サーバーの起動が完了しました。