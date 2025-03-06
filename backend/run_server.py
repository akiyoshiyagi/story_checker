import os
import sys
import uvicorn

# 環境変数を設定して標準出力のバッファリングを無効化
os.environ["PYTHONUNBUFFERED"] = "1"

# 標準出力のバッファリングを無効化
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

print("\n===== バックエンドサーバーを起動します =====")
print("標準出力のバッファリングを無効化しました")
print("Uvicornをデバッグモードで起動します")

if __name__ == "__main__":
    # Uvicornをデバッグモードで起動
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="debug",
        access_log=True,
        use_colors=True
    ) 