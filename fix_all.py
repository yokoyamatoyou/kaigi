import re
import os
import sys

def fix_all_flet_issues(file_path):
    """
    Fletのすべての既知の問題を修正するスクリプト
    - アイコン参照 (ft.icons.XXX → "xxx")
    - MaterialState参照 (ft.MaterialState.DEFAULT → 直接指定)
    - その他の非推奨機能
    
    Args:
        file_path: 修正対象のPythonファイルパス
    """
    print(f"ファイル '{file_path}' の全Flet問題を修正しています...")
    
    # ファイルが存在するか確認
    if not os.path.exists(file_path):
        print(f"エラー: ファイル '{file_path}' が見つかりません")
        return False
    
    # ファイルを読み込む
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"エラー: ファイルの読み込み中にエラーが発生しました: {e}")
        return False
    
    # バックアップを作成
    backup_path = f"{file_path}.full_backup"
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"バックアップを '{backup_path}' に保存しました")
    except Exception as e:
        print(f"警告: バックアップの作成中にエラーが発生しました: {e}")
    
    # 1. アイコン参照の修正 (ft.icons.XXX → "xxx")
    icon_pattern = r'ft\.icons\.([A-Z_]+)'
    
    def convert_icon(match):
        icon_name = match.group(1)
        # 大文字のアンダースコア区切りを小文字に変換
        converted = icon_name.lower()
        return f'"{converted}"'
    
    content = re.sub(icon_pattern, convert_icon, content)
    
    # 2. MaterialState参照の修正
    # パターン1: bgcolor={ft.MaterialState.DEFAULT: ft.colors.PRIMARY}
    ms_pattern1 = r'bgcolor=\{ft\.MaterialState\.DEFAULT:\s*ft\.colors\.([A-Z_]+)\}'
    def convert_ms1(match):
        color_name = match.group(1)
        return f'bgcolor=ft.colors.{color_name}'
    
    content = re.sub(ms_pattern1, convert_ms1, content)
    
    # パターン2: color={ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY}
    ms_pattern2 = r'color=\{ft\.MaterialState\.DEFAULT:\s*ft\.colors\.([A-Z_]+)\}'
    def convert_ms2(match):
        color_name = match.group(1)
        return f'color=ft.colors.{color_name}'
    
    content = re.sub(ms_pattern2, convert_ms2, content)
    
    # 3. その他の問題修正（必要に応じて追加）
    
    # ファイルに書き込む
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"ファイルの修正が完了しました")
        return True
    except Exception as e:
        print(f"エラー: ファイルの保存中にエラーが発生しました: {e}")
        return False

if __name__ == "__main__":
    # コマンドライン引数からファイルパスを取得
    if len(sys.argv) < 2:
        print("使用方法: python fix_all.py <ファイルパス>")
        file_path = "main.py"  # デフォルト値
        print(f"引数がないため、デフォルト値 '{file_path}' を使用します")
    else:
        file_path = sys.argv[1]
    
    fix_all_flet_issues(file_path)
    print("\n修正が完了しました。以下のコマンドでアプリケーションを起動してください:")
    print("python main.py")