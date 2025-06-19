"""
Fletバージョン確認（修正版）
"""

import flet as ft
import pkg_resources

def main(page: ft.Page):
    # Fletバージョン情報表示（pkg_resourcesを使用）
    try:
        flet_version = pkg_resources.get_distribution("flet").version
        page.add(ft.Text(f"Fletバージョン: {flet_version}"))
    except Exception as e:
        page.add(ft.Text(f"Fletバージョン取得エラー: {str(e)}", color="red"))
    
    # アイコン参照テスト
    page.add(ft.Text("アイコン参照テスト:", size=20))
    
    # 方法1: 文字列として直接指定
    page.add(ft.Text("方法1: 文字列指定"))
    
    try:
        row1 = ft.Row([
            ft.IconButton(icon="add", tooltip="追加"),
            ft.IconButton(icon="delete", tooltip="削除"),
            ft.IconButton(icon="save", tooltip="保存")
        ])
        page.add(row1)
        page.add(ft.Text("成功: 文字列としてアイコンを指定できます", color="green"))
    except Exception as e:
        page.add(ft.Text(f"エラー: {str(e)}", color="red"))
    
    # 使用可能なボタンタイプ表示
    page.add(ft.Text("使用可能なボタンタイプ:", size=20))
    
    try:
        row2 = ft.Row([
            ft.ElevatedButton(text="ElevatedButton"),
            ft.TextButton(text="TextButton"),
            ft.OutlinedButton(text="OutlinedButton")
        ])
        page.add(row2)
    except Exception as e:
        page.add(ft.Text(f"エラー: {str(e)}", color="red"))

ft.app(target=main)
