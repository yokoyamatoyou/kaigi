
import re

# ファイルパスを設定
file_path = "C:/Users/Ne/OneDrive - 株式会社ｔｏｙｏｕ/multi_ai_research_tool_flet/main.py"

print(f"ファイル '{file_path}' を修正しています...")

# ファイルを読み込む
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# バックアップを作成
backup_path = file_path + ".backup"
with open(backup_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"バックアップを '{backup_path}' に保存しました")

# MaterialStateの参照を修正
pattern1 = r'bgcolor=\{ft\.MaterialState\.DEFAULT: ft\.colors\.([A-Z_]+)\}'
replacement1 = r'bgcolor=ft.colors.\1'

pattern2 = r'color=\{ft\.MaterialState\.DEFAULT: ft\.colors\.([A-Z_]+)\}'
replacement2 = r'color=ft.colors.\1'

# 置換実行
content = re.sub(pattern1, replacement1, content)
content = re.sub(pattern2, replacement2, content)

# 修正内容を保存
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("MaterialState参照の修正が完了しました")
print("「python main.py」でアプリケーションを起動してください")