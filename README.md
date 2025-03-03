# Word 箇条書き処理アドイン

このプロジェクトは、Microsoft Word 内の箇条書きを読み取り、階層構造を解析して FastAPI バックエンドに送信する Office アドインです。

## プロジェクト構成

- `frontend/`: Word アドイン（TypeScript）
- `backend/`: FastAPI バックエンド（Python）

## 機能

- Word 文書内の箇条書きを読み取ります
- 箇条書きの階層構造を解析します（第一階層: summary、第二階層: message、第三階層: body）
- 解析したデータを JSON 形式で FastAPI バックエンドに送信します
- 処理結果をアドイン内に表示します

## 前提条件

- Node.js と npm
- Python 3.7 以上
- Microsoft Word

## セットアップ手順

### バックエンド（FastAPI）

1. 必要なパッケージをインストールします：

```bash
cd backend
pip install -r requirements.txt
```

2. FastAPI サーバーを起動します：

```bash
cd backend
python run.py
```

サーバーは `http://localhost:8000` で起動します。

### フロントエンド（Word アドイン）

1. 必要なパッケージをインストールします：

```bash
cd frontend
npm install
```

2. 開発サーバーを起動します：

```bash
cd frontend
npm run dev-server
```

3. Word アドインをサイドロードします：

```bash
cd frontend
npm run start
```

## 使い方

1. Word を起動し、箇条書きを含むドキュメントを開きます
2. アドインのタスクペインで「箇条書きを処理」ボタンをクリックします
3. アドインが箇条書きを読み取り、階層構造を解析してバックエンドに送信します
4. 処理結果がタスクペインに表示されます

## 箇条書きの階層構造

アドインは以下の階層構造で箇条書きを解析します：

- 第一階層（レベル 0）: summary
- 第二階層（レベル 1）: message
- 第三階層（レベル 2）: body

例：
```
• 会議の概要（summary）
  • 議題1（message）
    • 詳細内容1（body）
    • 詳細内容2（body）
  • 議題2（message）
    • 詳細内容3（body）
```

## API エンドポイント

- `POST /process-bullet-points`: 箇条書きデータを処理します
- `GET /`: API の状態を確認します

## ライセンス

MIT 