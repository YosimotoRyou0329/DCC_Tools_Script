# Maya Unity HDRP Preview

Maya 2024〜2027を起動対象にしています。PySide6 / PySide2を自動選択し、
Unityの既存PreviewHostに接続します。Maya 2027本体での実機確認は未実施です。

## 起動

1. DCC Launcherで「ツールフォルダー追加」から、このリポジトリの `Maya` を選択。
2. `Unity HDRP Preview` にチェックし、起動JSONを保存してMayaを起動。
3. Maya上部の `DCC Launcher → Unity HDRP Preview` をクリック（ドッキング可能なパネル）。
4. `Unityを起動`。PreviewHostは自動で指定されます（下記）。別のexeを使う場合だけ `設定` で指定。
5. アウトライナーから同期したいオブジェクトを「同期リスト」へドロップ（または `選択を追加`）。

Unityが起動して接続できると、同期リストのメッシュを送り、以後は変更を自動で同期します。
Unityを手動で起動した場合も1秒以内に検知します。送信ボタンは不要です。
パネルはチャネルボックス／レイヤエディタのタブとして開きます（無ければアトリビュートエディタ、
モデリングツールキット、アウトライナーの順）。タブをドラッグすれば、モデリングツールキットや
アウトライナーなど好きな場所へ移したりタブにしたりできます。閉じても同期は続きます
（同期エンジン `engine.py` はMaya終了まで常駐）。

## PreviewHostの自動指定

ランチャーのbatフォルダー（`dcc_maya_menu.py` のある場所）から2階層上の `maya_unity` を探します。

```
out/
  launcher/DCCLauncher/   ランチャー（bat）
  maya_unity/             MS2027.exe（解凍後） / Open.bat + data.mpk.NNN（未解凍）
```

- exe（`<名前>_Data` フォルダーがあるexe）があればそれを指定。
- まだ解凍していなければ `Open.bat` を指定。`Unityを起動` を押すと裏で `Open.bat` を実行し、
  解凍でき次第exeに切り替えてそのまま起動します（解凍中はステータスに表示）。
- 指定したexeが消えた場合（Clause.batで再圧縮した等）は、同じフォルダーの `Open.bat` に戻ります。
- `maya_unity` が見つかれば、前に保存した別の場所のexeより優先します。`maya_unity` がない時だけ `設定` で指定したexeを使います。環境変数 `DCC_LAUNCHER_ROOT` でランチャーの場所を上書きできます。

## 同期リスト

- リストに入れたトランスフォーム / グループの下にある全メッシュ、またはメッシュ自体が対象。
- リストはシーンの `fileInfo`（`mayaUnityPreviewSyncList`）にUUIDで保存。名前変更でも外れません。
- リストから外したメッシュはUnityから削除。リストが空なら何も送りません。
- リストに追加・削除すると自動でUnityへ反映します（再送信ボタンは不要）。項目のダブルクリックでMayaで選択。

## 自動同期

Maya APIのコールバックで変更を検知し、120ms以内の変更をまとめて送ります（ポーリングなし）。

| 操作 | 送るもの |
|---|---|
| 移動・回転・スケール（親の移動も含む） | そのメッシュ（ドラッグ中も更新） |
| 頂点編集・アトリビュート変更 | そのメッシュ |
| マニピュレータを離した時 / Undo / Redo / タイム変更 | 送信済みメッシュを再確認 |
| マテリアル（シェーディンググループ）の割り当て変更 | そのメッシュ |
| メッシュの作成 / 削除 | 追加 / `MESH_REMOVE` |
| メッシュの名前変更 | 旧名を `MESH_REMOVE` して新名で送信 |
| 新規シーン / シーンを開く | 全て `MESH_REMOVE`、開いたシーンのリストを読み込んで送信 |

送信中に来た変更は積み上げず、送信完了後に最新の状態を送ります。

## マテリアル（Mayaはいつも通り、シェーダーはUnityのexeで設定）

Mayaではモデリングとテクスチャ貼りまでをいつも通り行います（このツールはMayaのマテリアルを編集しません）。

- 同期すると、Mayaのマテリアル名ごとにexe内でMaterialを自動生成（初回は **HDRP/Lit**）。
  Mayaの色・ベースカラーテクスチャ・ノーマルマップ（bump2d / Tangent Space）を自動で反映。
- exeの **Inspector** で、マテリアル（スロット）ごとにシェーダーを選び、全プロパティを編集。
  複数マテリアルのオブジェクトはスロットごとに設定。変更した値は `*` 付きで表示、`Reset` で初期状態へ。
- 設定はマテリアル名ごとに `<Mayaプロジェクト>/unityPreview/materials/<名前>.json` へ自動保存。
  形やUVを直しても、別のシーンでも、同じプロジェクト・同じマテリアル名なら同じシェーダーで表示されます。
- テクスチャファイルを上書き保存（Substanceの再書き出し等）すると、Maya・Unityとも自動で再読込（PNG / JPG）。

送信内容: `{"type":"SESSION","materialFolder":"<project>/unityPreview/materials"}`（接続時・シーンを開いた時）、
`{"type":"MATERIAL_DEF","name":"MT_Body","baseColor":[1,1,1,1],"textures":[{"prop":"@base","path":"..."},{"prop":"@normal","path":"..."}]}`
（変化した時だけ、メッシュより先に送信）。

## Unityの窓（PiP）

- Unityの窓は端をドラッグしてサイズ変更できます（ツールが窓枠を付けます）。
- `PiP（常に手前）`: 常に手前・画面右下の小窓にします。位置とサイズは記憶されます。
- Unityを終了せずに隠す / 表示するには、ホットキーに次を割り当てます（パネルのボタンはありません）:
  `import maya_unity_preview; maya_unity_preview.toggle_unity_window()`
- Unityの窓は画面比率固定。サイズ変更は四隅のドラッグのみ（比率を保ったまま）。
  最大化などで比率が合わない時は黒帯を表示。
- Unity側のUI: 左上 `Hierarchy`・`View`、右上 `Inspector`。GUIは窓の大きさに合わせて縮小。
  `View`: 画面比率（16:9 / 16:10 / 4:3 / 21:9 / 1:1）、`Reset ratio`、窓の幅プリセット。
  `Tab` で全UIの表示・非表示。
- Mayaを終了する時、隠していたUnityは再表示されます。

## 責務

- `tool.json`: ツール名・対応Maya・Pythonパス・起動関数。
- `scripts/maya_unity_preview/__init__.py`: `show()`（パネル） / `controller()`（常駐エンジン）。
- `host_locator.py`: ランチャー横の `maya_unity` からexe / Open.batを探す・Open.batで解凍。Maya/Qtに依存しない。
- `engine.py`: Unity起動・接続監視、同期、同期リスト操作、Unityの窓操作。
- `ui.py`: ドッキング可能なパネル（表示と操作のみ）。
- `scene_watch.py`: Mayaのコールバックで変更されたメッシュを集める。
- `sync_list.py`: 同期リスト（シーン保存・対象判定）。
- `material.py`: Mayaマテリアル → MATERIAL_DEF（読み取りのみ）。
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

- `python -m unittest tests.test_mesh_payload tests.test_transport tests.test_host_locator`（Maya不要）
- `mayapy tests/maya_smoke.py`: 同期リストの絞り込み・SESSION / MATERIAL_DEF・移動の同期・リストから外した時の削除（要Maya）
- PiP・窓操作（Win32）とMayaのViewport操作からの往復は実機確認が必要です。
