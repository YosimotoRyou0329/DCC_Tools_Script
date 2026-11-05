// toonShader.fx : DirectX11 用トゥーンシェーダー (HLSL)
// Maya の Viewport 2.0 が DirectX11 のときに使われる。
// 中身は toonShader.ogsfx (OpenGL用) と同じ処理。

// ============================================================================
// Maya が自動で値を入れてくれる行列
//   「: World」などはセマンティクスと呼ばれる目印。
//   この目印を付けておくと、描くオブジェクトやカメラに合わせて Maya が勝手に値を入れてくれる。
// ============================================================================
float4x4 gWorld    : World;                  // オブジェクト → ワールド
float4x4 gWorldIT  : WorldInverseTranspose;  // 法線をワールドに変換する用
float4x4 gViewProj : ViewProjection;         // ワールド → 画面
float4x4 gViewInv  : ViewInverse;            // カメラのワールド行列（[3] がカメラの位置）

// ============================================================================
// ノードのアトリビュートから C++ (updateDevice) が値を入れるパラメータ
// ============================================================================
float3 gBaseColor        = { 1.0, 1.0, 1.0 };
bool   gUseTexture       = false;
float  gOutlineWidth     = 0.02;
float3 gOutlineColor     = { 0.0, 0.0, 0.0 };
float  gShadowThreshold  = 0.5;
float  gShadowSmoothness = 0.0;
float3 gShadowColor      = { 0.6, 0.6, 0.7 };

Texture2D gColorTexture;
SamplerState gColorSampler
{
	Filter   = MIN_MAG_MIP_LINEAR;
	AddressU = Wrap;
	AddressV = Wrap;
};

// ============================================================================
// 頂点の入力と、頂点シェーダー → ピクセルシェーダーへ渡すデータ
// ============================================================================
struct VS_INPUT
{
	float3 Position : POSITION;   // 頂点の位置
	float3 Normal   : NORMAL;     // 頂点の法線
	float2 UV       : TEXCOORD0;  // UV (map1)
};

struct VS_OUTPUT
{
	float4 HPosition   : SV_Position; // 画面上の位置
	float3 WorldPos    : TEXCOORD1;
	float3 WorldNormal : TEXCOORD2;
	float2 UV          : TEXCOORD0;
};

// ============================================================================
// pass 0 : アウトライン
//   頂点を法線方向に押し出して、少し膨らんだモデルを作る。
//   C++ 側で「表面を捨てる(Cull Front)」にしているので、膨らんだモデルの裏面だけが描かれ、
//   本体の外側にはみ出した部分がフチ線に見える。
// ============================================================================
VS_OUTPUT VS_Outline(VS_INPUT In)
{
	VS_OUTPUT Out;
	float3 worldPos    = mul(float4(In.Position, 1.0), gWorld).xyz;
	float3 worldNormal = normalize(mul(In.Normal, (float3x3)gWorldIT));

	worldPos += worldNormal * gOutlineWidth;   // 法線方向に押し出す

	Out.HPosition   = mul(float4(worldPos, 1.0), gViewProj);
	Out.WorldPos    = worldPos;
	Out.WorldNormal = worldNormal;
	Out.UV          = In.UV;
	return Out;
}

float4 PS_Outline(VS_OUTPUT In) : SV_Target
{
	return float4(gOutlineColor, 1.0);
}

// ============================================================================
// pass 1 : トゥーンシェーディング
//   カメラを光源とみなして、カメラの方を向いていない面に影を落とす。
// ============================================================================
VS_OUTPUT VS_Toon(VS_INPUT In)
{
	VS_OUTPUT Out;
	float3 worldPos = mul(float4(In.Position, 1.0), gWorld).xyz;

	Out.HPosition   = mul(float4(worldPos, 1.0), gViewProj);
	Out.WorldPos    = worldPos;
	Out.WorldNormal = mul(In.Normal, (float3x3)gWorldIT);
	Out.UV          = In.UV;
	return Out;
}

float4 PS_Toon(VS_OUTPUT In) : SV_Target
{
	float3 N      = normalize(In.WorldNormal);
	float3 camPos = gViewInv[3].xyz;
	float3 L      = normalize(camPos - In.WorldPos);  // 面 → カメラ の向き（＝光の向き）

	// N・L : 面がカメラを向いているほど 1、真横に近いほど 0
	float NdotL = dot(N, L);

	// しきい値を境に 影(0) / 明るい(1) に分ける。
	// smoothness が 0 なら境目がパキッと、1 に近いほど境目の幅が広がってなめらかになる。
	float halfWidth = max(gShadowSmoothness * 0.5, 0.0001);
	float lit = smoothstep(gShadowThreshold - halfWidth, gShadowThreshold + halfWidth, NdotL);

	// 基本色 × テクスチャ
	float3 albedo = gBaseColor;
	if (gUseTexture)
	{
		// DirectX と Maya でテクスチャの上下が逆なので V を反転する
		// （もし上下逆に表示されたら、この行を float2 uv = In.UV; に変える）
		float2 uv = float2(In.UV.x, 1.0 - In.UV.y);
		albedo *= gColorTexture.Sample(gColorSampler, uv).rgb;
	}

	// 影の部分は影の色を掛ける
	float3 color = albedo * lerp(gShadowColor, float3(1.0, 1.0, 1.0), lit);
	return float4(color, 1.0);
}

// ============================================================================
// technique : C++ の getEffectsFileShader(file, "Main") で指定している名前
//   pass の順番 = C++ の draw() のループの順番
// ============================================================================
technique11 Main
{
	pass Outline
	{
		SetVertexShader(CompileShader(vs_5_0, VS_Outline()));
		SetGeometryShader(NULL);
		SetPixelShader(CompileShader(ps_5_0, PS_Outline()));
	}
	pass Toon
	{
		SetVertexShader(CompileShader(vs_5_0, VS_Toon()));
		SetGeometryShader(NULL);
		SetPixelShader(CompileShader(ps_5_0, PS_Toon()));
	}
}
