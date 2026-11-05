# CMakeLists.txt : ToonShader_Node_Mll の CMake プロジェクト。
# Mayaプラグイン（.mll）を作るための設定を書く。

# ソースからMayaプラグイン（DLL）を作る
# STATIC：ビルド時に中へ内蔵される（別ファイルとしては残らない）
# SHARED：別ファイルのまま外付けで、実行中に読み込まれる
add_library(ToonShader_Node_Mll SHARED
	"toonshader_node_mll.cpp"
	"toonshader_node_mll.h"
)

# ターゲットのプロパティ（設定項目）を変更する
# set_property(TARGET 名前 PROPERTY 項目 値)         : プロパティを1個設定する(一個でやる前提のためPROPERTYが前提)
# set_target_properties(名前 PROPERTIES 項目 値 ...) : プロパティをまとめて設定する(複数でやる前提のためPROPERTIESが前提)
set_target_properties(ToonShader_Node_Mll PROPERTIES
	CXX_STANDARD 17   # C++のバージョン（Mayaに合わせる）
	SUFFIX ".mll"     # 出力ファイルの拡張子
)

# コンパイル時に必要なインクルードディレクトリを指定する
# PRIVATE：このターゲットのコンパイル時に必要なインクルードディレクトリ
# PUBLIC ：他のターゲットがこのターゲットをリンクする場合に必要なインクルードディレクトリ
# DirectoryのPathは、他のPCだと壊れるため、CMakeの組み込み変数を利用する。 = CMAKE_SOURCE_DIR : 最上位の CMakeLists.txt があるフォルダのPath
target_include_directories(ToonShader_Node_Mll PRIVATE
	"${CMAKE_SOURCE_DIR}/../Autodesk_Maya_2024_2_Update_DEVKIT_Windows/devkitBase/include")

# リンク時に .lib を探すフォルダを指定する
# Autodeskは宣言(.h)は公開しているが、処理(.cpp)は公開していない。
# 処理は .cpp をビルドして機械語にした .dll として Maya 本体(Maya2024/bin)に入っている。
# .lib は .h と .dll をつなぐ橋渡し役で、「どの機能がどの .dll にあるか」の住所が書いてある。
#   .h   : 宣言（名前と使い方）  → コンパイル時に使う（include）
#   .lib : .dll への住所        → リンク時に使う（ビルド時に必要）
#   .dll : 処理の本体           → Mayaで実行するときに使う（Mayaが最初から持っている）
# .dll は機能ごとに分かれていて、.dll 1個につき .lib が1個ペアになっている。
target_link_directories(ToonShader_Node_Mll PRIVATE
	"${CMAKE_SOURCE_DIR}/../Autodesk_Maya_2024_2_Update_DEVKIT_Windows/devkitBase/lib")

# 指定したlibのフォルダーから何を使うかを指定する
target_link_libraries(ToonShader_Node_Mll PRIVATE
	"Foundation"
	"OpenMaya"
	"OpenMayaRender"
	"OpenMayaUI")

# コンパイル時に何のOSでビルドしているかを定義する
# NT = Windows NT（今の Windows の元になった名前。「Windows」という意味で使われている）
# PLUGIN = プラグイン
target_compile_definitions(ToonShader_Node_Mll PRIVATE
	"NT_PLUGIN")

# ---- ここから追加（Claude） ----
# シェーダーファイル(shaders フォルダ)を、ビルドしたあと mll と同じ場所にコピーする
# POST_BUILD : ビルドが終わった後に実行する
# $<TARGET_FILE_DIR:ターゲット名> : 出来上がった mll があるフォルダ
add_custom_command(TARGET ToonShader_Node_Mll POST_BUILD
	COMMAND ${CMAKE_COMMAND} -E copy_directory
		"${CMAKE_CURRENT_SOURCE_DIR}/shaders"
		"$<TARGET_FILE_DIR:ToonShader_Node_Mll>/shaders")
