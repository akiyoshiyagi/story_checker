import uvicorn
import logging

if __name__ == "__main__":
    # ロギングレベルを警告以上に設定して、情報ログを抑制
    logging.basicConfig(level=logging.WARNING)
    
    # サーバーを起動（ログレベルを警告に設定）
    uvicorn.run(
        "app.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True, 
        log_level="warning"
    ) 