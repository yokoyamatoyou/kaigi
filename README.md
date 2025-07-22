# マルチAIディープリサーチツール

複数のAIモデルがペルソナを持って会議形式で議論し、司会AIが結果をまとめるデスクトップアプリケーションです。

![アプリケーションスクリーンショット](assets/screenshot.png)

## 特徴

- **マルチAI会議**: OpenAI GPT、Anthropic Claude、Google Geminiが参加する会議をシミュレート
- **ペルソナ設定**: 各AIに専門分野や役割を設定して多角的な議論を実現
- **ドキュメント対応**: DOCX/PDFファイルをアップロードして内容を議論に反映
- **司会AI**: 会議の進行と最終要約を専用AIが担当
- **リアルタイム表示**: 会議の進行をリアルタイムで確認
- **結果保存**: 会話ログと要約結果をファイルに保存

## 必要な環境

- Python 3.8 以上
- 各AIサービスのAPIキー
  - OpenAI API キー
  - Anthropic Claude API キー
  - Google Gemini API キー

## インストール

1. リポジトリをクローンまたはダウンロード
```bash
git clone [repository-url]
cd multi_ai_research_tool_flet
```

2. 必要なパッケージをインストール
```bash
pip install -r requirements.txt
```

3. 環境変数を設定
   - `.env_example` を `.env` にコピー
   - 各APIキーを設定

```bash
cp .env_example .env
```

`.env` ファイルを編集：
```
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```
## 環境変数

env_example.shで定義されている主な環境変数:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `DEFAULT_TEMPERATURE`
- `DEFAULT_MAX_TOKENS`
- `DEFAULT_ROUNDS_PER_AI`
- `LOG_LEVEL`


## 使用方法

### 1. アプリケーションの起動

```bash
python main.py
```

### 2. AIモデルの設定

1. **参加モデルの追加**
   - モデル名（例：`gpt-3.5-turbo`, `claude-3-sonnet-20240229`, `gemini-pro`）を入力
   - 「＋」ボタンで追加
   - 各モデルにペルソナ（役割・専門分野）を設定
   - 温度（創造性）を調整

2. **司会モデルの選択**
   - 参加モデルの中から司会を担当するモデルを選択

3. **発言回数の設定**
   - 各AIの発言回数を設定（デフォルト：3回）

### 3. 議論の開始

1. **質問・指示の入力**
   - 議論してもらいたい内容を入力

2. **資料ファイルのアップロード**（オプション）
   - DOCXまたはPDFファイルを選択
   - 自動的に要約されて議論の参考資料として使用

3. **会議開始**
   - 「会議開始」ボタンをクリック
   - リアルタイムで議論の進行を確認

### 4. 結果の確認・保存

1. **会話内容の確認**
   - 各AIの発言をリアルタイムで表示

2. **最終要約の確認**
   - 司会AIによる包括的な要約を表示

3. **保存**
   - 会話ログと要約結果をテキストファイルで保存

## モデル例

### 参加モデルの例

- **GPT-4**: `gpt-4` - 総合的な分析と創造的思考
- **Claude**: `claude-3-sonnet-20240229` - 論理的な推論と詳細分析
- **Gemini**: `gemini-pro` - データ分析と技術的視点

### ペルソナの例

- **戦略コンサルタント**: ビジネス戦略と市場分析の専門家
- **技術者**: システム設計と技術実装の専門家
- **研究者**: データ分析と学術的アプローチの専門家
- **マーケター**: 顧客視点と市場動向の専門家

## トラブルシューティング

### APIキーエラー
- 環境変数が正しく設定されているか確認
- APIキーの有効性を確認（課金状況など）

### ファイルアップロードエラー
- ファイルサイズが10MB以下であることを確認
- DOCX/PDF形式であることを確認

### 会議中のエラー
- ネットワーク接続を確認
- APIの利用制限に達していないか確認

## 技術仕様

- **GUIフレームワーク**: Flet
- **対応ファイル形式**: DOCX, PDF
- **最大ファイルサイズ**: 10MB
- **最大参加モデル数**: 5つ
- **対応AIプロバイダー**: OpenAI, Anthropic, Google

## ディレクトリ構造

```
multi_ai_research_tool_flet/
│
├── main.py                 # メインアプリケーション
├── requirements.txt        # 依存パッケージ
├── .env_example           # 環境変数テンプレート
├── README.md              # このファイル
│
├── core/                  # コアロジック
│   ├── __init__.py
│   ├── models.py          # データモデル
│   ├── config_manager.py  # 設定管理
│   ├── utils.py           # ユーティリティ
│   ├── document_processor.py  # ドキュメント処理
│   ├── meeting_manager.py     # 会議管理
│   ├── client_factory.py      # クライアントファクトリー
│   │
│   └── api_clients/       # AIクライアント
│       ├── __init__.py
│       ├── base_client.py     # 基底クライアント
│       ├── openai_client.py   # OpenAIクライアント
│       ├── claude_client.py   # Claudeクライアント
│       └── gemini_client.py   # Geminiクライアント
│
└── assets/               # 画像・アイコン
```

## Development

Install the dependencies and test tools:

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

Run the test suite with:

```bash
pytest
```

Optional environment variables can be set as shown in `env_example.sh`:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `DEFAULT_TEMPERATURE`
- `DEFAULT_MAX_TOKENS`
- `DEFAULT_ROUNDS_PER_AI`
- `LOG_LEVEL`

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 貢献

バグ報告や機能提案は、GitHubのIssueでお知らせください。

## バージョン履歴

- **v1.0.0** - 初回リリース
  - 基本的な会議機能
  - DOCX/PDF対応
  - 3つのAIプロバイダー対応
