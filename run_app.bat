@echo off
REM �o�b�`�t�@�C�������݂���f�B���N�g���Ɉړ�
cd /d "%~dp0"

REM Python�̉��z�����g�p���Ă���ꍇ�́A�����ŃA�N�e�B�x�[�g����
REM ��: .\venv\Scripts\activate.bat
REM (���������z�����g���Ă���Ȃ�A���̍s��REM�������ăp�X���C��)

REM Flet�A�v���P�[�V�����̋N��
echo Starting Multi AI Research Tool...
REM "python main.py" �Œ��ڎ��s���邩�A"flet run main.py" ���g�p���܂��B
REM Flet�v���W�F�N�g�̕W���I�ȋN�����@�� "flet run" �ł��B
REM assets_dir �̎w�肪 main.py �� ft.app �Ăяo���Ɋ܂܂�Ă��邩�m�F���Ă��������B

REM ���@1: flet run ���g�p (����)
flet run main.py

REM ���@2: python main.py ���g�p (ft.app �� view=ft.WEB_BROWSER �Ȃǂ��܂܂�Ă��Ȃ��ꍇ)
REM python main.py

REM �G���[�����������ꍇ�ɃE�B���h�E�������ɕ��Ȃ��悤�ɂ��邽�� (�f�o�b�O�p)
REM �{�ԉ^�p���͉��̍s���R�����g�A�E�g�܂��͍폜���Ă��悢
pause