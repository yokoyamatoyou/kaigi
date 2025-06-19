"""
インポートエラー診断ツール

Pythonのインポート問題を診断するための簡易スクリプト
"""

import os
import sys

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_imports():
    """各モジュールのインポートをテスト"""
    print("=== インポートテスト開始 ===")
    
    try:
        print("BaseAIClientのインポートを試みます...")
        from core.api_clients.base_client import BaseAIClient
        print(f"✅ 成功: {BaseAIClient}")
    except Exception as e:
        print(f"❌ 失敗: {e}")
    
    try:
        print("\napi_clientsパッケージからのインポートを試みます...")
        from core.api_clients import BaseAIClient, OpenAIClient, ClaudeClient, GeminiClient
        print(f"✅ 成功: BaseAIClient = {BaseAIClient}")
        print(f"✅ 成功: OpenAIClient = {OpenAIClient}")
        print(f"✅ 成功: ClaudeClient = {ClaudeClient}")
        print(f"✅ 成功: GeminiClient = {GeminiClient}")
    except Exception as e:
        print(f"❌ 失敗: {e}")
    
    try:
        print("\nClientFactoryのインポートを試みます...")
        from core.client_factory import ClientFactory
        print(f"✅ 成功: {ClientFactory}")
    except Exception as e:
        print(f"❌ 失敗: {e}")
    
    print("\n=== Pythonパス ===")
    for p in sys.path:
        print(f"  {p}")

def check_file_existence():
    """重要なファイルの存在を確認"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"\n=== ファイル確認 ===")
    print(f"ベースディレクトリ: {base_dir}")
    
    files_to_check = [
        "core/__init__.py",
        "core/api_clients/__init__.py",
        "core/api_clients/base_client.py",
        "core/client_factory.py"
    ]
    
    for file_path in files_to_check:
        full_path = os.path.join(base_dir, file_path)
        exists = os.path.exists(full_path)
        print(f"{'✅' if exists else '❌'} {file_path} {'存在します' if exists else '存在しません'}")
        
        if exists:
            # ファイルサイズを確認
            size = os.path.getsize(full_path)
            print(f"  - サイズ: {size} バイト")

if __name__ == "__main__":
    print(f"現在の作業ディレクトリ: {os.getcwd()}")
    check_file_existence()
    check_imports()
    
    print("\n診断が完了しました。問題が解決しない場合は、エラーメッセージを確認してください。")
