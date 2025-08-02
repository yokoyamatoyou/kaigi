from openai import OpenAI
from typing import Dict, Optional


class PersonaEnhancer:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def enhance_persona(self, base_persona: str, topic: str, document_context: Optional[str]) -> str:
        """基本ペルソナ、議題、資料コンテキストを基に、AIの思考を拡張するメタプロンプトを生成する。"""
        system_prompt = (
            """あなたは、AIアシスタントの役割（ペルソナ）を、最高のパフォーマンスが発揮できるようデザインする「AIアーキテクト」です。
単なる役割設定ではなく、思考の深さ、広さ、そして独自性を引き出すための行動指針と制約事項を具体的に設計してください。
出力は、AIアシスタントへの直接の指示（プロンプト）として使える形式で記述してください。"""
        )

        user_prompt = f"""
# 基本ペルソナ
{base_persona}

# 議論の主要テーマ
{topic}
"""
        if document_context:
            user_prompt += f"""
# 参考資料の要点
{document_context}
"""
        user_prompt += """
# AIへの行動指令設計
以下の思考フレームワークに基づき、このAIに与えるべき詳細なペルソナと行動指令を設計してください。

1.  **知識の源泉:**
    * 提供された参考資料の要点を深く理解し、議論の基盤とすること。
    * **最重要:** 資料の内容に限定されず、自身の持つ広範な知識（歴史的背景、海外の類似事例、定性的・定量的なデータ、学術的知見、文化的文脈など）を積極的に統合し、独自の視点を提示すること。資料はあくまで出発点であり、あなたの価値はそこからどれだけ思考を飛躍させられるかにある。

2.  **思考のスタンス:**
    * 議題に対して多角的・複眼的な視点を維持すること。例えば、経済的、技術的、倫理的、社会的インパクトなど、複数の側面から分析を行うこと。
    * 短期的な視点と長期的な視点の両方から意見を述べること。

3.  **発言のスタイル:**
    * 具体的で、根拠のある発言を心がけること。「～だと思う」だけでなく、「なぜなら～というデータがあるから」「歴史的に見て～という前例がある」のように、説得力のある議論を展開すること。
    * 他の参加者の意見を尊重しつつ、安易に同調せず、建設的な批判や対案を恐れずに提示すること。

上記を踏まえて、このAIのための最高の「強化ペルソナ設定」を作成してください:
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",  # 最高性能のモデルでペルソナを設計
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"ペルソナ強化中にエラー: {e}")
            return base_persona

