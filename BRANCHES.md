# ブランチ運用

作業場所: `D:/DCC/Tools`

- `main`: 元リポジトリの基準ブランチ。
- `integration/maya-tools`: Mayaツールを集約する親ブランチ。
- `feature/maya-unity-preview`: 親から作成した最初のツール用ブランチ。

今後は `integration/maya-tools` からツールごとに `feature/<tool-name>` を作成し、
検証後に親へマージします。mainへのマージは別途行います。
ランチャー本体・Mayaメニュー追加処理はbatのある配布フォルダーで管理します。
