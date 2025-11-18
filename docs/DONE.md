# DONE (Completed Tasks Log)
- Source of truth: このファイル / 対応PR / CIログ

## 2025-10
- 2025-10-25 JST | @gaobankirino561-dev | docs/DONE.md | 台帳の初期化（過去分を反映する枠組みを作成）
- 2025-10-22 JST | @gaobankirino561-dev | CI runs | 一部ワークフローの緑化を確認、次フェーズ移行用の引き継ぎ資料作成
- 2025-10-19 JST | @gaobankirino561-dev | docs/ROADMAP.md | フェーズ進行とCIゲート基準を明文化（net>0, win≥45%, dd≤20%, trades≥30）
- 2025-10-19 JST | @gaobankirino561-dev | ops/standards | PRゲート運用方針の確立（決定論・文書化・自動チェック、Get-PrNumber堅牢版、失敗時の原因分類ルール）

## 2025-07
- 2025-07-22 JST | @gaobankirino561-dev | backtest_full_bot.py | バックテスト完全自動運用を開始（エントリー決済判断・CSVログ・Discord通知・GPTキャッシュ）

## 2025-06
- 2025-06-23 JST | @gaobankirino561-dev | openai-python v1.10.0 | `client.chat.completions.create(...)` 方式へ移行（旧`openai.ChatCompletion.create`を排除）
- 2025-06-23 JST | @gaobankirino561-dev | backtest_full_bot.py | 初期版実装（GPT-4oでエントリー判定・CSV出力・Discord通知・キャッシュ）※当初は決済未実装
- 2025-06-21 JST | @gaobankirino561-dev | policy | 旧式API呼び出しの使用禁止を公式化（`openai.api_key = ...` / `openai.ChatCompletion.create(...)` / `OpenAI(..., proxies=...)`）
- 2025-06-18 JST | @gaobankirino561-dev | strategy | デイトレ戦略へ更新（M15+H1+H4）。A/B決済戦略を定義し、分間隔のトレンド崩れ監視の方針を決定
- 2025-06-18 JST | @gaobankirino561-dev | kpi/notify | バックテスト終了時の統計（総損益・勝率・取引数・平均損益・最大連勝連敗）算出とDiscord通知方針の定義
- 2025-06-18 JST | @gaobankirino561-dev | risk | 資金破綻時もテスト継続し、必要最低資金を推定する方針を決定（バックテストは資金万円想定）
- 2025-06-18 JST | @gaobankirino561-dev | notify | エントリー決済通知へ「GPTの判断理由」を含める方針、OpenAI月額上限の設定方針を決定
- 2025-06-17 JST | @gaobankirino561-dev | autobot_gpt.py | GPT-4o採用を決定し、新BOTファイルを作成
- 2025-06-16 JST | @gaobankirino561-dev | env/mt5 | Python + MT5 の環境構築を完了（以後の進行を一任）
- 2025-06-16 JST | @gaobankirino561-dev | Discord | 通知Webhookを設定（エントリー決済等の報告チャネルを確立）

YYYY-MM-DD JST | owner=@あなた | artifact=phaseC-smoke | summary=papertrade統合(guards+CI)スモーク雛形 | metrics=net=1200, win=55.0, dd=12.5, trades=40
2025-11-03 JST | owner=@あなた | artifact=phaseC-demo | summary=papertradeデモをCIゲート化(決定論ベースライン固定) | metrics=net=1234, win=50, dd=10, trades=2
2025-11-03 JST | owner=@あなた | artifact=phaseC-integration-gate | summary=統合スモークをbaseline+thresholdでPRゲート化 | metrics=net=, win=, dd=, trades=
2025-11-03 JST | owner=@あなた | artifact=phaseC-integration-gate | summary=統合スモークをbaseline+thresholdでPRゲート化 | metrics=net=3500.0, win=75.0, dd=0.0, trades=4.0
2025-11-03 JST | owner=@あなた | artifact=phaseC-autobot-improved | summary=PRゲート(決定論)のYAMLしきい値化＋GPT手動レーン整備 | metrics=net=3500.0, win=75.0, dd=0.0, trades=4.0
2025-11-03 JST | owner=@あなた | artifact=phaseC-health-gate | summary=Gate健全性の原因分類と観測性強化(decisions.jsonl/summary) | metrics=n/a
2025-11-03 JST | owner=@あなた | artifact=phaseC-gate-verified | summary=PRゲート(autobot)のOK/FAILを実地確認、GPT手動レーンを実行 | metrics=net=3500.0, win=75.0, dd=0.0, trades=4.0
2025-11-03 JST | owner=@あなた | artifact=phaseC-gpt-lane | summary=papertrade-autobot-gpt を feat/phaseC-papertrade でdispatch成功（404恒久解消） | metrics=net=0.0, win=0.0, dd=0.0, trades=0.0
2025-11-03 JST | owner=@あなた | artifact=phaseC-gpt-run | summary=Secrets投入＋予算ガードでGPT手動レーン実行 | metrics=net=0.0, win=0.0, dd=0.0, trades=0.0
2025-11-03 JST | owner=@あなた | artifact=phaseC-gpt-verify | summary=Secrets投入→artifact取得→Gate確認 | metrics=net=0.0, win=0.0, dd=0.0, trades=0.0
2025-11-03 JST | owner=@���Ȃ� | artifact=phaseD-live | summary=papertrade-live KILL�e�X�g�i��������1���Eenv�z���m�F�j���� | metrics=net=-2.0, win=0.0%, trades=1, dd=0%
