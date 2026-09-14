# Maya Unity HDRP Preview

Maya 2024〜2027を起動対象にしています。PySide6 / PySide2を自動選択し、
Unityの既存PreviewHostに接続します。Maya 2027本体での実機確認は未実施です。

## 起動

1. DCC Launcherで「ツールフォルダー追加」から、このリポジトリの `Maya` を選択。
2. `Unity HDRP Preview` にチェックし、起動JSONを保存してMayaを起動。
3. Maya上部の `DCC Launcher → Unity HDRP Preview` をクリック。
4. `参照` でビルド済みPreviewHost.exeを指定して `Unityを起動`。
5. Unityが表示されたらMayaでポリゴンメッシュを選択し、`Live Sync 起動`。

左ボタンでViewportを操作し、Mouse Up時に選択メッシュを一度だけ取得します。
初回やキーボード操作後は `選択メッシュを送信` で同期できます。
停止・ウィンドウを閉じる操作で受信ソケットとイベントフィルターを解除します。
Unityは独立したプロセスとして残り、Unityのウィンドウから終了できます。
EXEパスはユーザーごとのQSettingsに保存され、リポジトリには含まれません。

## 責務

- `tool.json`: ツール名・対応Maya・Pythonパス・起動関数。
- `scripts/maya_unity_preview/ui.py`: GUI、起動停止、Unityプロセス起動。
- `live_sync.py`: Viewportの左ボタン押下・解放のみ検知。
- `mesh.py`: Maya APIで選択メッシュのワールド座標と三角形を取得。
- `transport.py`: TCP受信・送信。Maya/Qtに依存しない。
- Mayaメニュー生成はこのリポジトリではなく、bat側の `dcc_maya_menu.py`。

## 通信と制限

Maya→Unity: localhost:50001 / UTF-8 JSON + 改行 / `MESH_DATA`。
Unity→Maya: localhost:50002 / little-endian int32の幅・高さ・バイト数 + RGBA32。
画像は上下反転のみ。追加ガンマ補正なし。
Mayaの座標はそのまま送信し、Unity側でZと三角形の向きを反転、倍率は1.0。
メッシュ監視タイマーは使用しません。ネットワーク処理は別スレッドです。
送信中の追加同期は積み上げずスキップし、画面に案内します。
一度送ったオブジェクトの削除、マテリアル、UV、カメラの同期は既存プロトコルの対象外です。
既存PreviewHostと同じくUnity側が法線を再計算します。
ポート50002を使う旧Script Editor版は停止してから起動してください。

Unity C#・MCP設定は変更していません。既存のビルド済みHostを利用します。
Unity側コードを変更した場合は別途Hostの再ビルドが必要です。

## 検証

通信の分割受信・異常ヘッダー・切断・ポート解放を自動テストで確認。
Maya 2024 mayapyでワールド座標の取得、Qt GUI、RGBA表示、受信再開、
Live Syncの登録解除を確認しています。
実際のMayaメニューバー配置とViewport操作からUnityへの往復表示は実機確認が必要です。
