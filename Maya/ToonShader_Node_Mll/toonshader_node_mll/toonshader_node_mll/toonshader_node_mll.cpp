// toonshader_node_mll.cpp : トゥーンシェーダーの実装
//
// 公式サンプル devkit/plug-ins/vp2BlinnShader を土台にしている。
// 全体の流れ：
//   [プラグイン読み込み] initializePlugin
//        → ノード(ToonShaderNode)と、描画担当(ToonShaderOverride)を Maya に登録
//   [マテリアルを割り当てると] Maya が ToonShaderOverride を作る
//        → コンストラクタでシェーダーファイルを読み込む
//   [アトリビュートが変わると]
//        updateDG()     : ノードからアトリビュートの値を読んで、変数にしまっておく
//        updateDevice() : しまっておいた値をシェーダーに渡す（テクスチャの読み込みもここ）
//   [毎フレームの描画] draw()
//        → パス0：アウトライン（表面を捨てて裏面だけ描く ＝ 逆カリング）
//        → パス1：トゥーン（普通に表面を描く）

#include "toonshader_node_mll.h"

#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MFloatVector.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MImage.h>

// スウォッチ（Hypershade のサムネイル）用
#include <maya/MHWShaderSwatchGenerator.h>
#include <maya/MRenderUtilities.h>

// Viewport 2.0 用
#include <maya/MDrawRegistry.h>
#include <maya/MPxShaderOverride.h>
#include <maya/MDrawContext.h>
#include <maya/MStateManager.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MShaderManager.h>
#include <maya/MTextureManager.h>

// ============================================================================
// ノードの静的メンバーの実体
// ============================================================================
const MTypeId ToonShaderNode::id(0x0007F100);
const MString ToonShaderNode::typeName("toonShader");
const MString ToonShaderNode::drawDbClassification("drawdb/shader/surface/toonShader");
MString ToonShaderNode::shaderDirectory;

MObject ToonShaderNode::aColor;
MObject ToonShaderNode::aOutlineWidth;
MObject ToonShaderNode::aOutlineColor;
MObject ToonShaderNode::aShadowThreshold;
MObject ToonShaderNode::aShadowSmoothness;
MObject ToonShaderNode::aShadowColor;

// ============================================================================
// ノード本体
// ============================================================================
ToonShaderNode::ToonShaderNode() {}
ToonShaderNode::~ToonShaderNode() {}

void* ToonShaderNode::creator()
{
	return new ToonShaderNode();
}

MStatus ToonShaderNode::initialize()
{
	MFnNumericAttribute nAttr;

	// 色のアトリビュートを作る共通処理
	// setAffectsAppearance(true) : 値が変わったらビューポートを描き直す
	auto makeColor = [&](const char* longName, const char* shortName, float r, float g, float b) -> MObject
	{
		MObject attr = nAttr.createColor(longName, shortName);
		nAttr.setDefault(r, g, b);
		nAttr.setStorable(true);
		nAttr.setKeyable(true);
		nAttr.setAffectsAppearance(true);
		return attr;
	};

	// 数値(float)のアトリビュートを作る共通処理
	auto makeFloat = [&](const char* longName, const char* shortName, float def, float minV, float maxV) -> MObject
	{
		MObject attr = nAttr.create(longName, shortName, MFnNumericData::kFloat, def);
		nAttr.setMin(minV);
		nAttr.setMax(maxV);
		nAttr.setStorable(true);
		nAttr.setKeyable(true);
		nAttr.setAffectsAppearance(true);
		return attr;
	};

	// ---- カラー ----
	// file ノードの outColor をつなぐとテクスチャ、つながなければこの色になる
	aColor = makeColor("color", "c", 1.0f, 1.0f, 1.0f);

	// ---- アウトライン ----
	aOutlineWidth = nAttr.create("outlineWidth", "olw", MFnNumericData::kFloat, 0.02f);
	nAttr.setMin(0.0f);
	nAttr.setSoftMax(0.2f);   // スライダーの上限（手入力ならもっと大きくできる）
	nAttr.setStorable(true);
	nAttr.setKeyable(true);
	nAttr.setAffectsAppearance(true);

	aOutlineColor = makeColor("outlineColor", "olc", 0.0f, 0.0f, 0.0f);

	// ---- 影 ----
	aShadowThreshold  = makeFloat("shadowThreshold",  "sth", 0.5f, 0.0f, 1.0f);
	aShadowSmoothness = makeFloat("shadowSmoothness", "ssm", 0.0f, 0.0f, 1.0f);
	aShadowColor      = makeColor("shadowColor", "shc", 0.6f, 0.6f, 0.7f);

	// ノードに登録する
	addAttribute(aColor);
	addAttribute(aOutlineWidth);
	addAttribute(aOutlineColor);
	addAttribute(aShadowThreshold);
	addAttribute(aShadowSmoothness);
	addAttribute(aShadowColor);

	// outColor は MPxHardwareShader が最初から持っている出力アトリビュート。
	// 「入力が変わったら outColor も変わる」と教えておくと、Maya が更新を伝えてくれる。
	attributeAffects(aColor,            outColor);
	attributeAffects(aOutlineWidth,     outColor);
	attributeAffects(aOutlineColor,     outColor);
	attributeAffects(aShadowThreshold,  outColor);
	attributeAffects(aShadowSmoothness, outColor);
	attributeAffects(aShadowColor,      outColor);

	return MS::kSuccess;
}

MStatus ToonShaderNode::compute(const MPlug& plug, MDataBlock& block)
{
	if ((plug != outColor) && (plug.parent() != outColor))
		return MS::kUnknownParameter;

	// ソフトウェアレンダー用：color をそのまま出すだけ
	MFloatVector color = block.inputValue(aColor).asFloatVector();
	MDataHandle outHandle = block.outputValue(outColor);
	outHandle.asFloatVector() = color;
	outHandle.setClean();
	return MS::kSuccess;
}

const MRenderProfile& ToonShaderNode::profile()
{
	static MRenderProfile sProfile;
	if (sProfile.numberOfRenderers() == 0)
		sProfile.addRenderer(MRenderProfile::kMayaSoftware);
	return sProfile;
}

MStatus ToonShaderNode::renderSwatchImage(MImage& image)
{
	if (MHWRender::MRenderer::theRenderer())
	{
		unsigned int w, h;
		image.getSize(w, h);
		return MHWRender::MRenderUtilities::renderMaterialViewerGeometry(
			w > 128 ? "meshShaderball" : "meshSphere",
			thisMObject(), image,
			MHWRender::MRenderUtilities::kPerspectiveCamera,
			MHWRender::MRenderUtilities::kSwatchLight);
	}
	return MS::kSuccess;
}

// ============================================================================
// カリング（どちらの面を捨てるか）の設定
// プラグイン全体で1つずつあればいいので static にしておく
// ============================================================================
static const MHWRender::MRasterizerState* sCullFrontState = nullptr; // 表面を捨てる（アウトライン用）
static const MHWRender::MRasterizerState* sCullBackState  = nullptr; // 裏面を捨てる（普通の描画）

static void acquireRasterizerStates()
{
	if (!sCullFrontState)
	{
		MHWRender::MRasterizerStateDesc desc;
		desc.cullMode = MHWRender::MRasterizerState::kCullFront;
		sCullFrontState = MHWRender::MStateManager::acquireRasterizerState(desc);
	}
	if (!sCullBackState)
	{
		MHWRender::MRasterizerStateDesc desc;
		desc.cullMode = MHWRender::MRasterizerState::kCullBack;
		sCullBackState = MHWRender::MStateManager::acquireRasterizerState(desc);
	}
}

static void releaseRasterizerStates()
{
	if (sCullFrontState) { MHWRender::MStateManager::releaseRasterizerState(sCullFrontState); sCullFrontState = nullptr; }
	if (sCullBackState)  { MHWRender::MStateManager::releaseRasterizerState(sCullBackState);  sCullBackState  = nullptr; }
}

// ============================================================================
// Viewport 2.0 の描画担当
// ============================================================================
class ToonShaderOverride : public MHWRender::MPxShaderOverride
{
public:
	static MHWRender::MPxShaderOverride* creator(const MObject& obj)
	{
		return new ToonShaderOverride(obj);
	}

	~ToonShaderOverride() override
	{
		MHWRender::MRenderer* renderer = MHWRender::MRenderer::theRenderer();
		if (!renderer) return;

		if (fShader)
		{
			const MHWRender::MShaderManager* shaderMgr = renderer->getShaderManager();
			if (shaderMgr) shaderMgr->releaseShader(fShader);
			fShader = nullptr;
		}
		releaseTexture();
	}

	// ------------------------------------------------------------------
	// 1. 初期化：このシェーダーが「頂点のどの情報(位置/法線/UV)を使うか」を Maya に伝える
	// ------------------------------------------------------------------
	MString initialize(const MInitContext& initContext, MSharedPtr<MUserData>& userData) override
	{
		if (fShader)
		{
			addShaderSignature(*fShader);       // DirectX11 で必要
			setGeometryRequirements(*fShader);  // シェーダーファイルの POSITION / NORMAL / TEXCOORD0 を見て自動で設定
		}
		return MString("ToonShaderOverride");
	}

	// ------------------------------------------------------------------
	// 2-a. 更新：ノードからアトリビュートの値を読んで、メンバー変数にしまう
	//       （ここでは Maya のノードを触ってOK。GPU は触らない）
	// ------------------------------------------------------------------
	void updateDG(MObject object) override
	{
		if (object.isNull()) return;

		MFnDependencyNode node(object);
		readColor(node, ToonShaderNode::aColor,        fColor);
		readColor(node, ToonShaderNode::aOutlineColor, fOutlineColor);
		readColor(node, ToonShaderNode::aShadowColor,  fShadowColor);
		fOutlineWidth     = node.findPlug(ToonShaderNode::aOutlineWidth,     true).asFloat();
		fShadowThreshold  = node.findPlug(ToonShaderNode::aShadowThreshold,  true).asFloat();
		fShadowSmoothness = node.findPlug(ToonShaderNode::aShadowSmoothness, true).asFloat();

		// color に file ノードがつながっていたら、そのノードと画像パスを覚えておく
		fTextureNode = MObject::kNullObj;
		fTexturePath.clear();
		MPlug colorPlug = node.findPlug(ToonShaderNode::aColor, true);
		MPlugArray sources;
		if (colorPlug.connectedTo(sources, true, false) && sources.length() > 0)
		{
			MObject srcNode = sources[0].node();
			if (srcNode.hasFn(MFn::kFileTexture))
			{
				fTextureNode = srcNode;
				fTexturePath = MFnDependencyNode(srcNode).findPlug("fileTextureName", true).asString();
				// テクスチャを使うときは、色は白（テクスチャの色そのまま）にする
				fColor[0] = fColor[1] = fColor[2] = 1.0f;
			}
		}
	}

	// ------------------------------------------------------------------
	// 2-b. 更新：しまっておいた値をシェーダーに渡す（ここでは GPU を触ってOK）
	// ------------------------------------------------------------------
	void updateDevice() override
	{
		if (!fShader) return;

		// テクスチャの画像が変わったときだけ読み直す
		if (fTexturePath != fLoadedTexturePath)
		{
			releaseTexture();
			if (!fTextureNode.isNull())
			{
				MHWRender::MTextureManager* texMgr = MHWRender::MRenderer::theRenderer()->getTextureManager();
				if (texMgr) fTexture = texMgr->acquireTexture(fTextureNode);
			}
			fLoadedTexturePath = fTexturePath;
		}

		// シェーダーファイルの変数名（g～）に値を入れる
		fShader->setParameter("gBaseColor",        fColor);
		fShader->setParameter("gOutlineWidth",     fOutlineWidth);
		fShader->setParameter("gOutlineColor",     fOutlineColor);
		fShader->setParameter("gShadowThreshold",  fShadowThreshold);
		fShader->setParameter("gShadowSmoothness", fShadowSmoothness);
		fShader->setParameter("gShadowColor",      fShadowColor);

		fShader->setParameter("gUseTexture", fTexture != nullptr);
		if (fTexture)
		{
			MHWRender::MTextureAssignment texAssign;
			texAssign.texture = fTexture;
			fShader->setParameter("gColorTexture", texAssign);
		}
	}

	// ------------------------------------------------------------------
	// 3. 描画
	// ------------------------------------------------------------------
	// シェーダーが読み込めていなければ描かない（Maya のデフォルトで描かれる）
	bool handlesDraw(MHWRender::MDrawContext& context) override
	{
		return fShader != nullptr && MPxShaderOverride::handlesDraw(context);
	}

	bool draw(MHWRender::MDrawContext& context, const MHWRender::MRenderItemList& renderItemList) const override
	{
		if (!fShader) return false;

		MHWRender::MStateManager* stateMgr = context.getStateManager();
		const MHWRender::MRasterizerState* prevState = stateMgr ? stateMgr->getRasterizerState() : nullptr;

		// マテリアルごとにパラメータが違うので、batch 最適化は使わず draw の中で bind する
		fShader->bind(context);

		// シェーダーファイルの technique "Main" には pass が2つある
		//   pass 0 : Outline（法線方向に押し出して、裏面だけ描く）
		//   pass 1 : Toon   （普通に表面を描く）
		const unsigned int passCount = fShader->getPassCount(context);
		for (unsigned int i = 0; i < passCount; ++i)
		{
			fShader->activatePass(context, i);

			// activatePass の後にカリングを上書きする
			if (stateMgr)
				stateMgr->setRasterizerState(i == 0 ? sCullFrontState : sCullBackState);

			drawGeometry(context);
		}

		fShader->unbind(context);

		// 他のオブジェクトの描画に影響しないよう、カリングを元に戻す
		if (stateMgr && prevState)
			stateMgr->setRasterizerState(prevState);

		return true;
	}

	// DirectX11 と OpenGL(Core Profile) に対応
	MHWRender::DrawAPI supportedDrawAPIs() const override
	{
		return MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile;
	}

	// アウトラインはバウンディングボックスより少し外にはみ出すので、少し大きめに扱ってもらう
	double boundingBoxExtraScale() const override
	{
		return 1.1;
	}

private:
	ToonShaderOverride(const MObject& obj)
		: MHWRender::MPxShaderOverride(obj)
	{
		acquireRasterizerStates();
		loadShader();
	}

	// 描画APIに合わせて、シェーダーファイルを読み込む
	//   DirectX11            → toonShader.fx    (HLSL)
	//   OpenGL Core Profile  → toonShader.ogsfx (GLSL)
	void loadShader()
	{
		MHWRender::MRenderer* renderer = MHWRender::MRenderer::theRenderer();
		if (!renderer) return;
		const MHWRender::MShaderManager* shaderMgr = renderer->getShaderManager();
		if (!shaderMgr) return;

		const bool isDX11 = (renderer->drawAPI() == MHWRender::kDirectX11);
		const MString file = ToonShaderNode::shaderDirectory + (isDX11 ? "toonShader.fx" : "toonShader.ogsfx");

		fShader = shaderMgr->getEffectsFileShader(file, "Main");
		if (!fShader)
			MGlobal::displayError("toonShader: failed to load shader file: " + file);
	}

	void releaseTexture()
	{
		if (fTexture)
		{
			MHWRender::MRenderer* renderer = MHWRender::MRenderer::theRenderer();
			MHWRender::MTextureManager* texMgr = renderer ? renderer->getTextureManager() : nullptr;
			if (texMgr) texMgr->releaseTexture(fTexture);
			fTexture = nullptr;
		}
		fLoadedTexturePath.clear();
	}

	static void readColor(MFnDependencyNode& node, const MObject& attr, float out[3])
	{
		MPlug plug = node.findPlug(attr, true);
		out[0] = plug.child(0).asFloat();
		out[1] = plug.child(1).asFloat();
		out[2] = plug.child(2).asFloat();
	}

	// シェーダー
	MHWRender::MShaderInstance* fShader = nullptr;

	// テクスチャ
	MHWRender::MTexture* fTexture = nullptr;
	MObject fTextureNode;
	MString fTexturePath;
	MString fLoadedTexturePath;

	// アトリビュートの値（updateDG で読んで、updateDevice で渡す）
	float fColor[3]        = { 1.0f, 1.0f, 1.0f };
	float fOutlineColor[3] = { 0.0f, 0.0f, 0.0f };
	float fShadowColor[3]  = { 0.6f, 0.6f, 0.7f };
	float fOutlineWidth     = 0.02f;
	float fShadowThreshold  = 0.5f;
	float fShadowSmoothness = 0.0f;
};

// ============================================================================
// プラグインの入口・出口
// ============================================================================
static const MString sRegistrantId("toonShaderRegistrantId");

PLUGIN_EXPORT MStatus initializePlugin(MObject obj)
{
	MStatus status;
	MFnPlugin plugin(obj, "Yoshimoto", "0.1", "Any");

	// シェーダーファイルは mll と同じ場所の shaders フォルダに置く
	ToonShaderNode::shaderDirectory = plugin.loadPath() + "/shaders/";

	// 分類文字列
	//   shader/surface/       : Hypershade の「Surface」に表示される
	//   drawdb/shader/surface/toonShader : Viewport 2.0 の Override と結び付ける
	//   swatch/...            : サムネイルの描き方
	const MString swatchName = MHWShaderSwatchGenerator::initialize();
	const MString classification = "shader/surface/utility/:" + ToonShaderNode::drawDbClassification + ":swatch/" + swatchName;

	status = plugin.registerNode(ToonShaderNode::typeName, ToonShaderNode::id,
		ToonShaderNode::creator, ToonShaderNode::initialize,
		MPxNode::kHardwareShader, &classification);
	if (!status) { status.perror("registerNode"); return status; }

	status = MHWRender::MDrawRegistry::registerShaderOverrideCreator(
		ToonShaderNode::drawDbClassification, sRegistrantId, ToonShaderOverride::creator);
	if (!status) { status.perror("registerShaderOverrideCreator"); return status; }

	MGlobal::displayInfo("toonShader loaded. shader dir: " + ToonShaderNode::shaderDirectory);
	return MS::kSuccess;
}

PLUGIN_EXPORT MStatus uninitializePlugin(MObject obj)
{
	MStatus status;
	MFnPlugin plugin(obj);

	status = MHWRender::MDrawRegistry::deregisterShaderOverrideCreator(
		ToonShaderNode::drawDbClassification, sRegistrantId);
	if (!status) { status.perror("deregisterShaderOverrideCreator"); return status; }

	status = plugin.deregisterNode(ToonShaderNode::id);
	if (!status) { status.perror("deregisterNode"); return status; }

	releaseRasterizerStates();
	return MS::kSuccess;
}
