# Maya Unity HDRP Preview

Maya 2024〜2027を起動対象にしています。PySide6 / PySide2を自動選択し、
Unityの既存PreviewHostに接続します。Maya 2027本体での実機確認は未実施です。

## 起動

1. DCC Launcherで「ツールフォルダー追加」から、このリポジトリの `Maya` を選択。
2. `Unity HDRP Preview` にチェックし、起動JSONを保存してMayaを起動。
3. Maya上部の `DCC Launcher → Unity HDRP Preview` をクリック。
4. `参照` でビルド済みPreviewHost.exeを指定して `Unityを起動`。

Unityが起動して接続できると、シーン内の全メッシュを送り、以後は変更を自動で同期します。
Unityを手動で起動した場合も、1秒以内に検知して同じ動作になります。送信ボタンは不要です。
EXEパスや窓の位置はユーザーごとのQSettingsに保存され、リポジトリには含まれません。

## 自動同期

Maya APIのコールバックで変更を検知し、120ms以内の変更をまとめて送ります（ポーリングなし）。

| 操作 | 送るもの |
|---|---|
| 頂点編集・移動・回転・スケール | そのメッシュ |
| マテリアル（シェーディンググループ）の割り当て変更 | そのメッシュ |
| メッシュの作成 / 削除 | 追加 / `MESH_REMOVE` |
| メッシュの名前変更 | 旧名を `MESH_REMOVE` して新名で送信 |
| 新規シーン / シーンを開く | 全て `MESH_REMOVE` して開いたシーンを送信 |

送信中に来た変更は積み上げず、送信完了後に最新の状態を送ります。
親トランスフォームだけの名前変更は、次にそのメッシュが変更された時に反映されます。

## Unityの窓（PiP）

- Unityの窓は端をドラッグしてサイズ変更できます（ツールが窓枠を付けます）。
- `PiP（常に手前の小窓）`: 常に手前・画面右下の小窓にします。位置とサイズは記憶されます。
- `Unityを隠す / 表示`: Unityを終了せずに隠します。ホットキーに割り当てる場合:
  `import maya_unity_preview; maya_unity_preview.toggle_unity_window()`
- Unity上で `Tab`: Hierarchy / Inspector を全て表示・非表示。幅720px未満では最初から非表示。
- ツールを閉じた時、隠していたUnityは再表示されます。

## 責務

- `tool.json`: ツール名・対応Maya・Pythonパス・起動関数。
- `scripts/maya_unity_preview/ui.py`: GUI、Unity起動・接続監視、同期の開始停止。
- `scene_watch.py`: Mayaのコールバックで変更されたメッシュを集める。
- `mesh.py` / `mesh_payload.py`: メッシュ取得 / 送信データ作成（後者はMaya非依存）。
- `transport.py`: TCP送信と接続確認。Maya/Qtに依存しない。
- `unity_window.py`: Win32でUnityの窓を操作（サイズ変更・最前面・表示切替）。
- Mayaメニュー生成はこのリポジトリではなく、bat側の `dcc_maya_menu.py`。

## 通信

Maya→Unity: localhost:50001 / UTF-8 JSON + 改行 / 1接続1メッセージ。

```json
{"type":"MESH_DATA_V2","name":"|body|bodyShape",
 "positions":[x,y,z,...],"normals":[x,y,z,...],"uvs":[u,v,...],
 "submeshes":[{"material":"MT_Mutou_Toon_Skin","triangles":[0,1,2,...]}]}
{"type":"MESH_REMOVE","name":"|body|bodyShape"}
```

- 頂点は (頂点・法線・UV) の組み合わせ単位で分割。ハードエッジとUVの継ぎ目を保持。
- 法線はMayaの値をそのまま送信。UVはカレントUVセット。座標はそのまま、Unity側でZ反転、倍率1.0。
- マテリアル名 = Mayaマテリアルノード名（ネームスペース除去）。
  文字列アトリビュート `unityMaterial` があればその値を優先。
- Unity側は `CS_MayaPreviewMaterialCatalog`（Resources）から同名のMaterialを割り当てる。
  名前なし → 灰色、Unityに無い名前 → マゼンタ。
- Unity→MayaのHDRP画像送信（50002）は廃止。Unity側も既定で送信しません。
- `MESH_DATA_V2` / `MESH_REMOVE` は2026/10/10以降にビルドしたPreviewHostが必要です。

## 検証

- `python -m unittest tests.test_mesh_payload tests.test_transport`（Maya不要）
- `mayapy tests/maya_smoke.py`: 自動同期の開始停止・名前変更時の削除・窓の寿命（要Maya）
- PiP・窓操作（Win32）とMayaのViewport操作からの往復は実機確認が必要です。
