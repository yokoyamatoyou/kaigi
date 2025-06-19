#!/usr/bin/env python3
"""
Fletのアイコン参照を修正するスクリプト
ft.icons.XXX形式のアイコン参照を文字列形式（"xxx"）に変更します
"""

import re
import sys
import os

def fix_flet_icons(file_path):
    """
    Fletのアイコン参照を自動修正する
    
    Args:
        file_path: 修正対象のPythonファイルパス
    """
    print(f"ファイル '{file_path}' を修正しています...")
    
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
    backup_path = f"{file_path}.bak"
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"バックアップを '{backup_path}' に保存しました")
    except Exception as e:
        print(f"警告: バックアップの作成中にエラーが発生しました: {e}")
    
    # 置換パターン: ft.icons.XXX → "xxx"
    pattern = r'ft\.icons\.([A-Z_]+)'
    
    # 置換前の状態を保存
    original_content = content
    
    # 置換関数
    def convert_icon(match):
        icon_name = match.group(1)
        # 大文字のアンダースコア区切りを小文字に変換
        converted = icon_name.lower()
        return f'"{converted}"'
    
    # 置換実行
    modified_content = re.sub(pattern, convert_icon, content)
    
    # 変更があったか確認
    if original_content == modified_content:
        print("変更すべきアイコン参照はありませんでした")
        return True
    
    # 置換結果を確認
    matches = re.findall(pattern, original_content)
    if matches:
        print(f"以下のアイコン参照を修正しました:")
        for i, match in enumerate(set(matches), 1):
            print(f"  {i}. ft.icons.{match} → \"{match.lower()}\"")
    
    # 修正内容を保存
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print(f"ファイルを修正しました")
        return True
    except Exception as e:
        print(f"エラー: ファイルの保存中にエラーが発生しました: {e}")
        return False

def main():
    """メイン関数"""
    # コマンドライン引数からファイルパスを取得
    if len(sys.argv) < 2:
        print("使用方法: python fix_flet_icons.py <ファイルパス>")
        return
    
    file_path = sys.argv[1]
    fix_flet_icons(file_path)

if __name__ == "__main__":
    main()