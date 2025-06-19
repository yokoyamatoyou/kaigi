@echo off
REM バッチファイルが存在するディレクトリに移動
cd /d "%~dp0"

REM Pythonの仮想環境を使用している場合は、ここでアクティベートする
REM 例: .\venv\Scripts\activate.bat
REM (↑もし仮想環境を使っているなら、この行のREMを消してパスを修正)

REM Fletアプリケーションの起動
echo Starting Multi AI Research Tool...
REM "python main.py" で直接実行するか、"flet run main.py" を使用します。
REM Fletプロジェクトの標準的な起動方法は "flet run" です。
REM assets_dir の指定が main.py の ft.app 呼び出しに含まれているか確認してください。

REM 方法1: flet run を使用 (推奨)
flet run main.py

REM 方法2: python main.py を使用 (ft.app に view=ft.WEB_BROWSER などが含まれていない場合)
REM python main.py

REM エラーが発生した場合にウィンドウがすぐに閉じないようにするため (デバッグ用)
REM 本番運用時は下の行をコメントアウトまたは削除してもよい
pause