// toonshader_node_mll.h : トゥーンシェーダーノードの宣言
//
// このプラグインは2つの部品でできている。
//   1. ToonShaderNode     : Maya のノード本体。アトリビュート（色や影の設定）を持つ。
//                           Hypershade に出てくるのはこれ。
//   2. ToonShaderOverride : Viewport 2.0 でどう描くかを担当する（.cpp の中に定義）。
//                           ノードのアトリビュートを読んで、シェーダーファイル(.fx / .ogsfx)に渡す。
//
// 2つは「分類文字列(classification)」で結び付けられる。
// registerNode と registerShaderOverrideCreator に同じ "drawdb/shader/surface/toonShader" を渡すと、
// 「このノードはこの Override で描く」と Maya が判断してくれる。

#pragma once

#include <maya/MPxHardwareShader.h>
#include <maya/MRenderProfile.h>
#include <maya/MTypeId.h>
#include <maya/MString.h>
#include <maya/MObject.h>

class ToonShaderNode : public MPxHardwareShader
{
public:
	ToonShaderNode();
	~ToonShaderNode() override;

	// Maya がノードを作るときに呼ぶ関数（new して返すだけ）
	static void* creator();

	// アトリビュートを作って登録する関数（プラグイン読み込み時に1回だけ呼ばれる）
	static MStatus initialize();

	// ソフトウェアレンダー用の計算。今回は Viewport 2.0 が目的なので、color をそのまま返すだけ。
	MStatus compute(const MPlug& plug, MDataBlock& block) override;

	// 旧ビューポート(VP1)用の設定。VP1 は使わないので「対応なし」を返す（公式サンプルと同じ）。
	const MRenderProfile& profile() override;

	// Hypershade のサムネイル(スウォッチ)を描く
	MStatus renderSwatchImage(MImage& image) override;

	// ノードID。Maya の全ノードで被ってはいけない番号。
	// 0x00000 ～ 0x7FFFF は「社内・個人で自由に使っていい範囲」。
	static const MTypeId id;

	// ノードの名前（createNode や Hypershade で使う名前）
	static const MString typeName;

	// Viewport 2.0 用の分類文字列（Node と Override を結び付ける）
	static const MString drawDbClassification;

	// シェーダーファイル(.fx / .ogsfx)が置いてあるフォルダ。プラグイン読み込み時に設定する。
	static MString shaderDirectory;

	// ---- アトリビュート ----
	static MObject aColor;            // カラー（file ノードをつなぐとテクスチャ、つながなければこの色）
	static MObject aOutlineWidth;     // アウトラインの太さ（ワールド単位）
	static MObject aOutlineColor;     // アウトラインの色
	static MObject aShadowThreshold;  // 影のしきい値（0～1。大きいほど影の範囲が広がる）
	static MObject aShadowSmoothness; // 影の境目の滑らかさ（0 = パキッと、1 = なめらか）
	static MObject aShadowColor;      // 影の色（基本色に掛け算される）
};
