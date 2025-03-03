import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# Azure OpenAI API設定
# 注意: 以下の設定は.envファイルから読み込まれますが、
# 現在はopenai_service.pyで直接設定されています
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "8lpRPqPom0AI6hAxloQrlhszYLO4YwR4")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://api-manager.peerworker.ai/v1/azure/general")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o") 