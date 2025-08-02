# **【最終版】マルチAIディープリサーチツール改善リファクタリング計画**

この計画は、アプリケーションのコア機能を大幅に強化し、ユーザー体験を向上させるためのものです。特に、RAG（検索拡張生成）とLLMの広範な内部知識を融合させ、司会役AIによる高度なファシリテーションを実現することで、議論の質を最大化することを目的とします。

### **フェーズ1: 環境設定と依存ライブラリの導入**

計画通り、RAG（Retrieval-Augmented Generation）パイプラインを構築するために必要なライブラリをインストールします。

1. requirements.txtの更新:  
   以下のライブラリをrequirements.txtに追加します。  
   \# requirements.txt に以下を追記  
   faiss-cpu  
   langchain  
   langchain-openai  
   langchain\_community  
   tiktoken

2. ライブラリのインストール:  
   ターミナルでpip install \-r requirements.txtを実行します。

### **フェーズ2: 高度な検索機能を持つRAGパイプラインの実装**

計画通り、長文資料を効率的に扱うため、VectorStoreManagerにMMR（Maximal Marginal Relevance）検索機能を実装します。これにより、資料から「議題に関連し、かつ多様な視点を持つ」情報を効率的に抽出します。  
**ファイル:** core/vector\_store\_manager.py (修正)

import faiss  
import numpy as np  
from langchain\_community.vectorstores import FAISS  
from langchain\_openai import OpenAIEmbeddings  
from langchain.text\_splitter import RecursiveCharacterTextSplitter  
from typing import List, Optional

from .document\_processor import DocumentProcessor  
from .config\_manager import ConfigManager

class VectorStoreManager:  
    """  
    ドキュメントのテキストをベクトル化し、FAISSによる高度な検索機能を提供するクラス。  
    """  
    def \_\_init\_\_(self, openai\_api\_key: str):  
        self.embeddings \= OpenAIEmbeddings(model="text-embedding-3-small", openai\_api\_key=openai\_api\_key)  
        self.vector\_store: Optional\[FAISS\] \= None  
        self.text\_splitter \= RecursiveCharacterTextSplitter(chunk\_size=1000, chunk\_overlap=200)

    def create\_from\_file(self, file\_path: str):  
        try:  
            processor \= DocumentProcessor(file\_path)  
            text \= processor.extract\_text()  
            if not text:  
                self.vector\_store \= None  
                return  
            chunks \= self.text\_splitter.split\_text(text)  
            self.vector\_store \= FAISS.from\_texts(texts=chunks, embedding=self.embeddings)  
            print("ベクトルストアの構築が完了しました。")  
        except Exception as e:  
            print(f"ベクトルストアの構築中にエラーが発生しました: {e}")  
            self.vector\_store \= None

    def get\_relevant\_documents(self, query: str, k: int \= 5, use\_mmr: bool \= False) \-\> List\[str\]:  
        """  
        クエリに関連するドキュメントのチャンクを取得する。  
        MMR (Maximal Marginal Relevance) を使用して多様性を確保するオプションを追加。  
        """  
        if not self.vector\_store:  
            return \[\]  
          
        if use\_mmr:  
            \# MMR検索で、関連性と多様性を両立させる  
            docs \= self.vector\_store.max\_marginal\_relevance\_search(query, k=k, fetch\_k=20)  
        else:  
            \# 通常の類似度検索  
            docs \= self.vector\_store.similarity\_search(query, k=k)  
              
        return \[doc.page\_content for doc in docs\]

### **フェーズ3: AIの思考拡張と高度な会議進行ロジックの実装**

ここが今回のアップグレードの核心です。AIに「資料の読解」と「自身の知識の活用」を明確に指示し、司会役がそれを高度にまとめる仕組みを構築します。

#### **ステップ3.1: PersonaEnhancerの大幅な機能強化**

ペルソナ強化の役割を再定義します。単に役割を与えるだけでなく、**思考の方向性そのものをデザイン**します。

**ファイル:** core/persona\_enhancer.py (修正)

from openai import OpenAI  
from typing import Dict, Optional

class PersonaEnhancer:  
    def \_\_init\_\_(self, api\_key: str):  
        self.client \= OpenAI(api\_key=api\_key)

    def enhance\_persona(self, base\_persona: str, topic: str, document\_context: Optional\[str\]) \-\> str:  
        """  
        基本ペルソナ、議題、資料コンテキストを基に、AIの思考を拡張するメタプロンプトを生成する。  
        """  
        system\_prompt \= """あなたは、AIアシスタントの役割（ペルソナ）を、最高のパフォーマンスが発揮できるようデザインする「AIアーキテクト」です。  
単なる役割設定ではなく、思考の深さ、広さ、そして独自性を引き出すための行動指針と制約事項を具体的に設計してください。  
出力は、AIアシスタントへの直接の指示（プロンプト）として使える形式で記述してください。"""

        user\_prompt \= f"""  
\# 基本ペルソナ  
{base\_persona}

\# 議論の主要テーマ  
{topic}  
"""  
        if document\_context:  
            user\_prompt \+= f"""  
\# 参考資料の要点  
{document\_context}  
"""  
        user\_prompt \+= """  
\# AIへの行動指令設計  
以下の思考フレームワークに基づき、このAIに与えるべき詳細なペルソナと行動指令を設計してください。

1\.  \*\*知識の源泉:\*\*  
    \* 提供された参考資料の要点を深く理解し、議論の基盤とすること。  
    \* \*\*最重要:\*\* 資料の内容に限定されず、自身の持つ広範な知識（歴史的背景、海外の類似事例、定性的・定量的なデータ、学術的知見、文化的文脈など）を積極的に統合し、独自の視点を提示すること。資料はあくまで出発点であり、あなたの価値はそこからどれだけ思考を飛躍させられるかにある。

2\.  \*\*思考のスタンス:\*\*  
    \* 議題に対して多角的・複眼的な視点を維持すること。例えば、経済的、技術的、倫理的、社会的インパクトなど、複数の側面から分析を行うこと。  
    \* 短期的な視点と長期的な視点の両方から意見を述べること。

3\.  \*\*発言のスタイル:\*\*  
    \* 具体的で、根拠のある発言を心がけること。「～だと思う」だけでなく、「なぜなら～というデータがあるから」「歴史的に見て～という前例がある」のように、説得力のある議論を展開すること。  
    \* 他の参加者の意見を尊重しつつ、安易に同調せず、建設的な批判や対案を恐れずに提示すること。

上記を踏まえて、このAIのための最高の「強化ペルソナ設定」を作成してください:  
"""

        try:  
            response \= self.client.chat.completions.create(  
                model="gpt-4o",  \# 最高性能のモデルでペルソナを設計  
                messages=\[  
                    {"role": "system", "content": system\_prompt},  
                    {"role": "user", "content": user\_prompt}  
                \],  
                temperature=0.7,  
            )  
            return response.choices\[0\].message.content  
        except Exception as e:  
            print(f"ペルソナ強化中にエラー: {e}")  
            return base\_persona

#### **ステップ3.2: MeetingManagerの修正（司会役の強化）**

MeetingManagerに、**最終要約（サマリー）の役割を「議論の統合と次のアクションの提案」へと昇華させる**ロジックを追加します。

**ファイル:** core/meeting\_manager.py (修正)

\# ... (他のimport)  
from .vector\_store\_manager import VectorStoreManager  
from .persona\_enhancer import PersonaEnhancer  
from typing import Optional, List, Dict

class MeetingManager:  
    \# \_\_init\_\_, \_prepare\_meeting, \_run\_discussion\_turn は前回の計画通り

    def \_run\_summary\_turn(self):  
        """  
        司会役が、議論全体を構造的に分析し、統合的なレポートを生成する。  
        """  
        moderator \= self.participants\[-1\]  
        client \= self.client\_factory.get\_client(moderator\["model\_info"\])  
          
        \# ★★★ 高度な要約のための専用プロンプト ★★★  
        summary\_prompt \= self.prompts.get("final\_summary")  
        if not summary\_prompt:  
            summary\_prompt \= """あなたは、この会議の優れたファシリテーター兼議事録担当です。  
これまでの議論全体を俯瞰し、以下の構成で構造化された「インテリジェンス・レポート」を作成してください。

\# インテリジェンス・レポート構成

\#\# 1\. 総括 (Executive Summary)  
\* 会議の目的と、それに対してどのような結論に至ったかを2-3行で要約してください。

\#\# 2\. 主要な論点と発見  
\* 議論の中で明らかになった最も重要な論点、発見、インサイトを箇条書きで3～5点挙げてください。

\#\# 3\. 参加者の意見の集約  
\* \*\*合意点:\*\* 参加者の意見が一致した点は何でしたか？  
\* \*\*対立点・多様な視点:\*\* 意見が分かれた点や、注目すべき異なる視点は何でしたか？それぞれの意見を簡潔にまとめてください。

\#\# 4\. 未解決の課題と今後の検討事項  
\* この議論では結論が出なかった点、あるいは新たに見つかった課題は何ですか？  
\* 今後、さらに深掘りして調査・検討すべき問いを具体的に3つ提示してください。

\#\# 5\. 提言 (Actionable Recommendations)  
\* この議論の結果を踏まえ、次に取るべき具体的なアクションや戦略を提案してください。

以上の構成に従い、議論の価値を最大化するレポートを生成してください。  
"""

        conversation\_log \= self.\_format\_conversation\_history()  
        prompt \= summary\_prompt.format(  
            topic=self.settings.topic,  
            conversation\_history=conversation\_log  
        )

        try:  
            \# ... (API呼び出しとメッセージ更新のロジックは既存のものを活用)  
            response\_text \= client.generate\_response(prompt)  
            self.on\_message(moderator\["name"\], response\_text, is\_summary=True)  
        except Exception as e:  
            self.on\_error(f"{moderator\['name'\]}の要約生成中にエラーが発生しました: {e}")  
        finally:  
            self.on\_complete()

### **フェーズ4: UI改善と仕上げ**

(変更なし)  
計画通り、保存時にSnackBarで完了通知を表示するようにmain.pyのsave\_results関数を修正します。  
**ファイル:** main.py (修正)

\# ...

def save\_results(e, is\_summary):  
    \# ... (既存の保存ロジック)  
    try:  
        \# ...  
          
        \# ★★★ 保存完了通知 ★★★  
        page.snack\_bar \= ft.SnackBar(  
            ft.Text(f"結果を {filename} に保存しました。"),  
            open=True  
        )  
        page.update()

    except Exception as ex:  
        page.snack\_bar \= ft.SnackBar(  
            ft.Text(f"保存中にエラーが発生しました: {ex}"),  
            open=True  
        )  
        page.update()  
**フェーズ5: 会議コンテキストの永続化と次会議への持ち越し機能**

今回の会議で解決しなかった課題を次回の会議に引き継ぐための、新しいメカニズムを導入します。

#### **ステップ5.1: `ContextManager`の新規作成**

会議の「持ち越し事項」をJSONファイルとして永続化・管理する専門クラスを作成します。

**ファイル:** `core/context_manager.py` (新規作成)

import os

import json

from datetime import datetime

from typing import List, Dict, Optional

class ContextManager:

    """

    会議の持ち越し事項（コンテキスト）を管理するクラス。

    """

    def \_\_init\_\_(self, context\_dir: str \= "saved\_contexts"):

        self.context\_dir \= context\_dir

        if not os.path.exists(self.context\_dir):

            os.makedirs(self.context\_dir)

    def save\_carry\_over(self, topic: str, unresolved\_issues: str):

        """

        未解決の課題をJSONファイルとして保存する。

        """

        if not unresolved\_issues.strip():

            print("持ち越し事項がないため、保存をスキップしました。")

            return

        timestamp \= datetime.now().strftime("%Y%m%d\_%H%M%S")

        filename \= f"context\_{timestamp}.json"

        filepath \= os.path.join(self.context\_dir, filename)

        data \= {

            "topic": topic,

            "unresolved\_issues": unresolved\_issues,

            "created\_at": timestamp

        }

        with open(filepath, "w", encoding="utf-8") as f:

            json.dump(data, f, ensure\_ascii=False, indent=4)

        print(f"持ち越し事項を {filepath} に保存しました。")

    def list\_carry\_overs(self) \-\> List\[Dict\[str, str\]\]:

        """

        保存されている持ち越し事項のリストを取得する。

        """

        contexts \= \[\]

        for filename in sorted(os.listdir(self.context\_dir), reverse=True):

            if filename.endswith(".json"):

                filepath \= os.path.join(self.context\_dir, filename)

                with open(filepath, "r", encoding="utf-8") as f:

                    try:

                        data \= json.load(f)

                        contexts.append({

                            "id": filename,

                            "display\_name": f"\[{data\['created\_at'\]}\] {data\['topic'\]}"

                        })

                    except json.JSONDecodeError:

                        continue

        return contexts

    def load\_carry\_over(self, context\_id: str) \-\> Optional\[str\]:

        """

        指定されたIDの持ち越し事項を読み込む。

        """

        filepath \= os.path.join(self.context\_dir, context\_id)

        if not os.path.exists(filepath):

            return None

        

        with open(filepath, "r", encoding="utf-8") as f:

            data \= json.load(f)

            return data.get("unresolved\_issues")

#### **ステップ5.2: `MeetingManager`の修正（持ち越し事項の保存と活用）**

`MeetingManager`を修正し、会議終了時に持ち越し事項を保存し、会議開始時にそれを活用できるようにします。

**ファイル:** `core/meeting_manager.py` (修正)

\# ... (他のimport)

from .context\_manager import ContextManager \# 追加

import re \# 追加

class MeetingManager:

    def \_\_init\_\_(self, settings: MeetingSettings, vector\_store\_manager: VectorStoreManager, on\_message, on\_complete, on\_error, carry\_over\_context: Optional\[str\] \= None):

        \# ... (既存の初期化)

        self.carry\_over\_context \= carry\_over\_context \# 追加

        self.context\_manager \= ContextManager() \# 追加

    def \_prepare\_meeting(self):

        \# ... (既存の\_prepare\_meetingロジック)

        

        \# ★★★ 持ち越し事項を初期コンテキストに追加 ★★★

        if self.carry\_over\_context:

            initial\_context \+= f"\\n\\n\# 前回の会議からの持ち越し事項\\n{self.carry\_over\_context}"

        

        \# ... (ペルソナ強化ロジックは、この拡張されたinitial\_contextを使用)

    def \_run\_summary\_turn(self):

        \# ... (既存の要約ロジック)

        try:

            response\_text \= client.generate\_response(prompt)

            self.on\_message(moderator\["name"\], response\_text, is\_summary=True)

            \# ★★★ 持ち越し事項を抽出して保存 ★★★

            match \= re.search(r"\#\# 4\\. 未解決の課題と今後の検討事項\\s\*\\n(.\*?)(?=\\n\#\#|\\Z)", response\_text, re.DOTALL)

            if match:

                unresolved\_issues \= match.group(1).strip()

                self.context\_manager.save\_carry\_over(self.settings.topic, unresolved\_issues)

        except Exception as e:

            self.on\_error(f"{moderator\['name'\]}の要約生成中にエラーが発生しました: {e}")

        finally:

            self.on\_complete()

#### **ステップ5.3: `main.py`のUI修正（持ち越し事項の選択）**

UIにドロップダウンメニューを追加し、過去の会議の持ち越し事項を選択して新しい会議を開始できるようにします。

**ファイル:** `main.py` (修正)

\# ... (他のimport)

from core.context\_manager import ContextManager \# 追加

def main(page: ft.Page):

    \# ...

    context\_manager \= ContextManager()

    \# ★★★ 持ち越し事項選択ドロップダウンを追加 ★★★

    carry\_over\_options \= \[ft.dropdown.Option(key="none", text="なし")\]

    saved\_contexts \= context\_manager.list\_carry\_overs()

    for context in saved\_contexts:

        carry\_over\_options.append(ft.dropdown.Option(key=context\["id"\], text=context\["display\_name"\]))

    

    carry\_over\_dropdown \= ft.Dropdown(

        label="前回の持ち越し事項を読み込む",

        options=carry\_over\_options,

        value="none"

    )

    \# 会議開始ボタンのコールバックを修正

    def start\_meeting(e):

        \# ...

        

        \# ★★★ 選択された持ち越し事項を読み込む ★★★

        carry\_over\_context \= None

        selected\_context\_id \= carry\_over\_dropdown.value

        if selected\_context\_id \!= "none":

            carry\_over\_context \= context\_manager.load\_carry\_over(selected\_context\_id)

        try:

            \# ...

            meeting\_manager \= MeetingManager(

                settings=settings,

                vector\_store\_manager=vector\_store\_manager,

                on\_message=update\_conversation\_view,

                on\_complete=meeting\_complete,

                on\_error=meeting\_error,

                carry\_over\_context=carry\_over\_context \# 追加

            )

            \# ...

    

    \# ... (UIレイアウトに carry\_over\_dropdown を追加する)

    settings\_column \= ft.Column(

        controls=\[

            \# ... (既存の設定コントロール)

            carry\_over\_dropdown, \# ドロップダウンを追加

            start\_button,

        \]

    )

    \# ...

この最終計画によりは単なる「AI会議シミュレーター」から、\*\*「集合知を創出し、次のアクションを導き出すインテリジェンス・エンジン」\*\*へと進化します。