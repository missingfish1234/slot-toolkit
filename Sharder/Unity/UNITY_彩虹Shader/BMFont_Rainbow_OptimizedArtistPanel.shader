Shader "Custom/BMFont_Rainbow_OptimizedArtistPanel"
{
    Properties
    {
        // === 基本設定 ===
        [PerRendererData] _MainTex ("BMFont 字型圖集 (RGBA)", 2D) = "white" {}
        _UseSrcRGB      ("乘上原圖 RGB (0..1)", Range(0,1)) = 1

        [Toggle(_PARTICLEMODE_ON)] _ParticleMode ("Particle Mode：忽略 UV1/UV2（用在粒子避免條紋）", Float) = 0

        [HideInInspector] _StencilComp ("Stencil Comparison", Float) = 8
        [HideInInspector] _Stencil ("Stencil ID", Float) = 0
        [HideInInspector] _StencilOp ("Stencil Operation", Float) = 0
        [HideInInspector] _StencilWriteMask ("Stencil Write Mask", Float) = 255
        [HideInInspector] _StencilReadMask ("Stencil Read Mask", Float) = 255
        [HideInInspector] _ColorMask ("Color Mask", Float) = 15
        [HideInInspector] _UseUIAlphaClip ("Use Alpha Clip", Float) = 0

        // ==============================================
        //             ★ 彩虹填色 (第一層) ★
        // ==============================================
        [Toggle(_FILL_ON)] _FillEnable ("啟用彩虹填色", Float) = 1
        
        _FillFlowMode   ("L1 填色模式 (0=線性,1=放射,2=螺旋,3=色帶)", Range(0,3)) = 0
        _FillAngle      ("L1 旋轉角度 (0..360)", Range(0,360)) = 0
        _FillSpeed      ("L1 捲動速度", Range(-5,5)) = 0.6
        _FillDensityAnim("L1 密度倍率 (1=標準, 越小越密)", Range(0.01,5)) = 1   

        // ==============================================
        //             ★ 彩虹雙層流動 (Layer 2) ★
        // ==============================================
        [Toggle(_FILL_L2_ON)] _FillL2Enable ("[L2] 啟用彩虹第二層", Float) = 0
        _FillL2Mix      ("[L2] 彩虹第二層混合 (0..1)", Range(0,1)) = 0.5
        _FillL2Angle    ("[L2] 彩虹第二層角度", Range(0,360)) = 90
        _FillL2Speed    ("[L2] 彩虹第二層速度", Range(-5,5)) = -0.6
        _FillL2Density  ("[L2] 彩虹第二層密度", Range(0.1, 5)) = 1.0

        // ==============================================
        //             ★ 彩虹共用參數 ★
        // ==============================================
        _FillPixelsPerCycle ("基礎循環寬度 (像素)", Range(0.25,4096)) = 200   
        _FillRefHeight      ("參考高度 (px)", Float) = 1080
        _FillRadialCenter   ("放射中心偏移 (X/Y)", Vector) = (0,0,0,0)
        _FillRadialTurns    ("放射/螺旋：手臂數量 (整數)", Range(0.1,20)) = 1.0
        _FillSpiralScale    ("螺旋：捲曲緊密度", Range(-100,100)) = 10.0
        _FillRadialBands    ("放射色帶：密度", Range(0.1,20)) = 3.0
        _FillHue        ("色相偏移 (0..1)", Range(0,1)) = 0
        _FillSaturation ("飽和度", Range(0,1)) = 1
        _FillIntensity  ("明度/強度", Range(0,3)) = 1
        _FillBlueBrightness ("藍色亮度倍率", Range(1,3)) = 1
        _FillBlueLift ("藍色補光", Range(0,1)) = 0
        _FillBlueRange ("藍色影響範圍", Range(0.02,0.35)) = 0.16
        _ParticleFillCoverage ("粒子軟邊填色", Range(0,1)) = 0
        _FillBlendMode  ("彩虹混合模式 (0=覆蓋,1=疊加,2=濾色,3=加亮)", Range(0,3)) = 0
        _FillBlendStrength ("彩虹疊加強度", Range(0,1)) = 1
        _FillFlashEnable ("啟用彩虹閃爍", Float) = 0
        _FillFlashColor ("彩虹閃爍顏色", Color) = (1,1,1,1)
        _FillFlashFrequency ("彩虹閃爍頻率 (次/秒)", Range(0.1,20)) = 2
        _FillFlashStrength ("彩虹閃爍強度", Range(0,1)) = 0.5
        _FillSoftWhite  ("柔和白光 (相加)", Range(0,1)) = 0
        
        // 其他細節
        _FillDetailBoost ("細節強化 (銳利度)", Range(0,1)) = 0
        _FillEdgeAA     ("邊緣抗鋸齒", Range(0,2)) = 1
        _FillAlphaCut   ("透明度剪裁", Range(0,1)) = 0.05
        _FillFollowObjectScale ("跟隨物件縮放 (0=關, 1=開)", Float) = 1

        // --- Fill Noise ---
        [Toggle(_FILL_NOISE_ON)] _FillNoiseEnable ("啟用彩虹不規則 Noise", Float) = 0
        _FillNoiseScale      ("Noise 尺寸", Range(0.1, 64)) = 6
        _FillNoiseStrength   ("Noise 扰動強度", Range(0, 1)) = 0.12
        _FillNoiseWarp       ("Noise 扭曲感", Range(0, 1)) = 0.18
        _FillNoiseContrast   ("Noise 邊界銳利度", Range(0.25, 4)) = 1.4
        _FillNoiseScrollX    ("Noise 流動 X", Range(-5, 5)) = 0.18
        _FillNoiseScrollY    ("Noise 流動 Y", Range(-5, 5)) = -0.11
        _FillNoiseStyle      ("Noise 風格 (0=標準,1=液態,2=雲霧,3=碎裂,4=火焰電流)", Range(0,4)) = 0
        _FillNoiseStyleMix   ("風格強度", Range(0, 1)) = 0.5
        _FillNoiseBreakup    ("碎裂/斷層量", Range(0, 1)) = 0.35
        _FillNoiseJitter     ("跳動感", Range(0, 1)) = 0.25
        
        _FillGroupMode  ("填色群組 (0=整體,1=每物件)", Range(0,1)) = 0
        _FillObjTiling  ("填色物件座標平鋪", Range(0.0001,500)) = 0.25  
        _FillObjUsePx          ("每物件：啟用每循環像素數", Float) = 1
        _FillObjPixelsPerCycle ("每物件每循環像素數", Range(0.25,4096)) = 64   
        _FillObjScaleComp      ("每物件縮放補償", Range(0,1)) = 1
        _FillObjFreqGain       ("每物件頻率增益", Range(0.01,128)) = 1       
        _FillPerObjCoord ("每物件座標基準 (0=每字同分布LocalUV,1=整串連續GlobalUV2)", Range(0,1)) = 0

        // --- Fill Mask ---
        [Toggle(_FILL_MASK_ON)] _FillMaskEnable ("啟用填色遮罩", Float) = 0
        _FillMaskTex    ("填色遮罩 (R)", 2D) = "white" {}
        _FillMaskFeatherPx("填色遮罩羽化", Range(0,64)) = 2
        _FillMaskInvert ("填色遮罩反相", Float) = 0

        // ==============================================
        //             ★ 鑽石覆蓋 (Layer 1) ★
        // ==============================================
        [Toggle(_DIAMOND_ON)] _DiamondEnable ("啟用鑽石覆蓋效果", Float) = 0
        _DiamondTex       ("鑽石法線貼圖", 2D) = "bump" {}
        _DiamondIntensity ("鑽石高光強度", Range(0, 5)) = 1.0 
        _DiamondBaseDim   ("壓暗底層彩虹", Range(0, 1)) = 0.5
        _DiamondTiling    ("鑽石平鋪 (密度)", Range(0.1, 100)) = 5.0
        _DiamondScrollX   ("鑽石偏移 X", Range(-5, 5)) = 0.05
        _DiamondScrollY   ("鑽石偏移 Y", Range(-5, 5)) = 0.05
        _DiamondSparkleSpeed ("鑽石閃爍速度", Range(0, 10)) = 2.0
        
        // ==============================================
        //             ★ 鑽石覆蓋 (Layer 2) ★
        // ==============================================
        [Toggle(_DIAMOND_L2_ON)] _DiamondL2Enable ("[L2] 啟用鑽石第二層", Float) = 0
        _DiamondL2Mix         ("   [L2] 混合強度 (疊加)", Range(0, 2)) = 0.5
        _DiamondL2Tiling      ("   [L2] 平鋪密度", Range(0.1, 100)) = 3.0
        _DiamondL2ScrollX     ("   [L2] 偏移 X", Range(-5, 5)) = -0.05
        _DiamondL2ScrollY     ("   [L2] 偏移 Y", Range(-5, 5)) = -0.05
        _DiamondL2SparkleSpeed("   [L2] 閃爍速度", Range(0, 10)) = 3.0

        // 鑽石共用參數
        _DiamondNormalFlat("鑽石光滑度", Range(0, 1)) = 0.5
        _DiamondContrast  ("鑽石陰影對比", Range(0.1, 5)) = 1.2 
        _DiamondSoftShininess ("玻璃感高光", Range(1, 100)) = 20.0
        _DiamondHardShininess ("閃耀高光", Range(1, 256)) = 150.0
        _DiamondLightZ    ("光源前向集中度", Range(0.1, 10)) = 0.5
        _DiamondIdle      ("鑽石待機亮度", Range(0, 1)) = 0.3 
        _DiamondLoopSec   ("循環週期", Float) = 0.0
        _DiamondLoopDur   ("啟動時間長度", Float) = 1.0

        // === 內側掃光 ===
        [Toggle(_INNER_SWEEP_ON)] _InnerSweepEnable ("啟用內側掃光", Float) = 0
        _InnerSweepMaskTex ("內側掃光遮罩 (R)", 2D) = "white" {}
        _InnerSweepColor   ("內側掃光顏色", Color) = (1,1,1,1)
        _InnerSweepAngle   ("內側掃光角度", Range(0, 360)) = 45
        _InnerSweepSpeed   ("內側掃光速度", Range(-5, 5)) = 1.0
        _InnerSweepDensity ("內側掃光密度", Range(0.001, 20)) = 0.1
        _InnerSweepWidth   ("內側掃光寬度", Range(0.0, 5.0)) = 0.3
        _InnerSweepFeather ("內側掃光羽化", Range(0.0, 1.0)) = 0.1
        _InnerSweepIntensity("內側掃光強度", Range(0, 5)) = 1.0
        _InnerSweepBlend   ("內側掃光混合模式", Range(0, 1)) = 0

        // === 外側掃光 ===
        [Toggle(_SWEEP_ON)] _SweepEnable ("啟用外側掃光", Float) = 1
        _SweepExcludeFill ("避免掃光覆蓋填色區", Float) = 0 
        _SweepGroupMode   ("外掃光/群組模式 (0=整體,1=每物件)", Range(0,1)) = 0
        _SweepFlowMode    ("外掃光/流動模式 (0=線性,1=放射；2,3保留未啟用)", Range(0,1)) = 0
        _SweepAngle       ("外掃光/角度", Range(0,360)) = 20
        _SweepSpeed       ("外掃光/速度", Range(-5,5)) = 1.0
        _SweepPixelsPerCycle ("外掃光/螢幕模式/每循環像素數", Range(8,4096)) = 240                
        _SweepWidthPx        ("外掃光/螢幕模式/寬度(px)", Range(0, 512)) = 40                         
        _SweepFeatherPx      ("外掃光/螢幕模式/羽化(px)", Range(0, 64)) = 4
        
        _SweepRefHeight      ("外掃光/螢幕模式/參考高度", Float) = 1080
        _SweepUseObject    ("外掃光/線性模式/使用物件座標", Float) = 1
        _SweepObjScaleComp ("外掃光/物件模式/縮放補償", Range(0,1)) = 1
        _SweepObjTiling    ("外掃光/物件模式/平鋪密度", Range(0.0001, 20)) = 0.2          
        _SweepObjWidth     ("外掃光/物件模式/寬度", Range(0, 20)) = 0.08   
        _SweepObjFeather   ("外掃光/物件模式/羽化", Range(0, 100)) = 0.01   
        
        _RadialCenter      ("外掃光/放射模式/中心", Vector) = (0.5,0.5,0,0)
        _RadialTurns       ("外掃光/放射模式/每圈旋轉數", Range(0.1,10)) = 1.0
        _SpiralScale       ("[保留] 外掃光/螺旋半徑比例", Range(-10,10)) = 1.0
        _RadialBands       ("[保留] 外掃光/放射色帶數", Range(0.1,20)) = 3.0
        _FlowRefHeight     ("[保留] 外掃光/流動參考高度", Float) = 1080

        [Toggle(_SWEEP_MASK_ON)] _SweepMaskEnable   ("啟用掃光遮罩", Float) = 0
        _SweepMaskTex      ("掃光遮罩 (R)", 2D) = "white" {}
        _SweepMaskFeatherPx("外掃光/遮罩羽化", Range(0,64)) = 2
        _SweepMaskInvert   ("外掃光/遮罩反相", Float) = 0

        _SweepUseGradient  ("外掃光/使用漸層貼圖", Float) = 0
        _SweepGradient     ("外掃光/漸層貼圖 (RGB)", 2D) = "white" {}
        
        _SweepColor        ("外掃光/顏色", Color) = (1,1,1,1)
        _SweepColorMode    ("外掃光/混合模式", Range(0,3)) = 1
        _SweepColorIntensity("外掃光/顏色強度", Range(0,3)) = 1

        _Alpha             ("整體透明度", Range(0,1)) = 1
        _DebugView         ("除錯顯示", Range(0,1)) = 0
    }

    SubShader
    {
        Tags
        {
            "Queue"="Transparent"
            "IgnoreProjector"="True"
            "RenderType"="Transparent"
            "PreviewType"="Plane"
            "CanUseSpriteAtlas"="True"
        }

        Stencil
        {
            Ref [_Stencil]
            Comp [_StencilComp]
            Pass [_StencilOp]
            ReadMask [_StencilReadMask]
            WriteMask [_StencilWriteMask]
        }

        Cull Off
        ZWrite Off
        Blend SrcAlpha OneMinusSrcAlpha
        ColorMask [_ColorMask]

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0
            
            #pragma shader_feature_local _FILL_ON
            #pragma shader_feature_local _FILL_L2_ON
            #pragma shader_feature_local _FILL_MASK_ON
            #pragma shader_feature_local _FILL_NOISE_ON
            #pragma shader_feature_local _DIAMOND_ON
            #pragma shader_feature_local _DIAMOND_L2_ON
            #pragma shader_feature_local _INNER_SWEEP_ON
            #pragma shader_feature_local _SWEEP_ON
            #pragma shader_feature_local _SWEEP_MASK_ON
            #pragma shader_feature_local _PARTICLEMODE_ON
            #pragma multi_compile_local _ UNITY_UI_CLIP_RECT
            #pragma multi_compile_local _ UNITY_UI_ALPHACLIP

            #include "UnityCG.cginc"
            #include "UnityUI.cginc"

            // === Uniforms ===
            sampler2D _MainTex;
            float4 _MainTex_ST; float4 _MainTex_TexelSize;
            float _UseSrcRGB;
            float4 _ClipRect;

            // Fill
            float _FillFlowMode, _FillAngle, _FillSpeed, _FillPixelsPerCycle, _FillRefHeight;
            float _FillFollowObjectScale, _FillDensityAnim;
            float _FillHue, _FillSaturation, _FillIntensity, _FillSoftWhite, _FillAlphaCut;
            float _FillBlueBrightness, _FillBlueLift, _FillBlueRange, _ParticleFillCoverage;
            float _FillBlendMode, _FillBlendStrength;
            float _FillFlashEnable, _FillFlashFrequency, _FillFlashStrength;
            float4 _FillFlashColor;
            float4 _FillRadialCenter;
            float _FillRadialTurns, _FillSpiralScale, _FillRadialBands, _FillFlowRefHeight;
            float _FillGroupMode, _FillObjTiling;
            float _FillObjUsePx, _FillObjPixelsPerCycle, _FillObjScaleComp, _FillObjFreqGain;
            float _FillPerObjCoord;
            float _FillDetailBoost;
            float _FillEdgeAA;
            float _FillNoiseScale, _FillNoiseStrength, _FillNoiseWarp, _FillNoiseContrast;
            float _FillNoiseScrollX, _FillNoiseScrollY;
            float _FillNoiseStyle, _FillNoiseStyleMix, _FillNoiseBreakup, _FillNoiseJitter;

            // Fill Layer 2
            float _FillL2Angle, _FillL2Speed, _FillL2Density, _FillL2Mix;
            
            // Fill Mask
            float _FillMaskFeatherPx, _FillMaskInvert;
            sampler2D _FillMaskTex;
            
            // Diamond
            sampler2D _DiamondTex;
            float _DiamondIntensity, _DiamondContrast, _DiamondTiling;
            float _DiamondSoftShininess, _DiamondHardShininess; 
            float _DiamondNormalFlat; 
            float _DiamondBaseDim; 
            float _DiamondSparkleSpeed;
            float _DiamondLightZ;
            float _DiamondLoopSec, _DiamondLoopDur;
            float _DiamondScrollX, _DiamondScrollY;
            float _DiamondIdle;

            // Diamond Layer 2
            float _DiamondL2Mix, _DiamondL2Tiling;
            float _DiamondL2ScrollX, _DiamondL2ScrollY, _DiamondL2SparkleSpeed;

            // Inner Sweep
            sampler2D _InnerSweepMaskTex;
            float4 _InnerSweepColor;
            float _InnerSweepAngle, _InnerSweepSpeed, _InnerSweepDensity;
            float _InnerSweepWidth, _InnerSweepFeather, _InnerSweepIntensity, _InnerSweepBlend;

            // Outer Sweep
            float _SweepFlowMode, _SweepAngle, _SweepSpeed;
            float _SweepGroupMode;
            float _SweepExcludeFill; 
            float _SweepPixelsPerCycle, _SweepWidthPx, _SweepFeatherPx, _SweepRefHeight;
            float _SweepUseObject, _SweepObjTiling, _SweepObjWidth, _SweepObjFeather;
            float _SweepObjScaleComp;
            float4 _RadialCenter;
            float _RadialTurns, _SpiralScale, _RadialBands, _FlowRefHeight;
            float _SweepMaskFeatherPx, _SweepMaskInvert;
            sampler2D _SweepMaskTex;
            float _SweepUseGradient; sampler2D _SweepGradient;
            float4 _SweepColor; float _SweepColorMode, _SweepColorIntensity;
            float _Alpha, _DebugView;

            struct appdata {
                float4 vertex    : POSITION;
                float2 uv        : TEXCOORD0;
                float2 uv1       : TEXCOORD1; 
                float2 uv2       : TEXCOORD2;
                fixed4 color     : COLOR; 
            };

            struct v2f {
                float4 pos       : SV_POSITION;
                float2 uv        : TEXCOORD0;
                float4 uvMinSize : TEXCOORD1;
                float2 wxy       : TEXCOORD2; 
                float2 objScaleXY: TEXCOORD3;
                float4 localPos  : TEXCOORD4;
                fixed4 color     : COLOR; 
                float4 screenPos : TEXCOORD5;
            };

            inline float2 dirFromAngle(float deg){ float r=deg*0.01745329f; return float2(cos(r),sin(r)); }
            
            inline half3 hsv2rgb(half3 c){ 
                half4 K=half4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
                half3 p=abs(frac(c.xxx+K.xyz)*6.0-K.www);
                return c.z*lerp(K.xxx, saturate(p-K.xxx), c.y); 
            }

            inline half calcBlueHueMask(half3 rgb, float range)
            {
                half3 c = saturate(rgb);
                half maxc = max(c.r, max(c.g, c.b));
                half minc = min(c.r, min(c.g, c.b));
                half chroma = max(maxc - minc, 1e-5);
                half hue = 0.0;

                if (maxc == c.r) hue = frac(((c.g - c.b) / chroma) / 6.0);
                else if (maxc == c.g) hue = ((c.b - c.r) / chroma + 2.0) / 6.0;
                else hue = ((c.r - c.g) / chroma + 4.0) / 6.0;

                half d = abs(hue - 0.60);
                d = min(d, 1.0 - d);
                half hueMask = 1.0 - smoothstep(range * 0.45, range, d);
                half colorMask = saturate(chroma * 4.0);
                return hueMask * colorMask;
            }

            inline half sampleMaskSmooth(sampler2D tex, float2 uv, float featherPx, float invert, float4 texelSize)
            {
                half m = tex2D(tex, uv).r;
                if (invert > 0.5) m = 1.0 - m;
                float fw = max(featherPx, 1e-5) * length(texelSize.xy) * 4.0;
                return saturate(smoothstep(0.0 - fw, 1.0 + fw, m));
            }

            inline float hash21(float2 p)
            {
                p = frac(p * float2(123.34, 345.45));
                p += dot(p, p + 34.345);
                return frac(p.x * p.y);
            }

            inline float noise21(float2 p)
            {
                float2 i = floor(p);
                float2 f = frac(p);
                float a = hash21(i);
                float b = hash21(i + float2(1,0));
                float c = hash21(i + float2(0,1));
                float d = hash21(i + float2(1,1));
                float2 u = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
            }

            inline float fbm4(float2 p)
            {
                float v = 0.0;
                float a = 0.5;
                v += noise21(p) * a; p = p * 2.02 + 17.13; a *= 0.5;
                v += noise21(p) * a; p = p * 2.03 + 11.71; a *= 0.5;
                v += noise21(p) * a; p = p * 2.01 +  8.31; a *= 0.5;
                v += noise21(p) * a;
                return v / 0.9375;
            }

            inline float2 calcFillNoiseUV(float2 screenUV, float4 uvMinSize, float groupMode, float perObjCoord)
            {
                float2 localUV01  = uvMinSize.xy;
                float2 globalUV01 = uvMinSize.zw;
                float2 perObjUV01 = (perObjCoord < 0.5) ? localUV01 : globalUV01;
                float uv12Mag = max(abs(localUV01.x) + abs(localUV01.y), abs(globalUV01.x) + abs(globalUV01.y));
                float hasUV12 = step(1e-4, uv12Mag);
                float useForcedUV = step(50.0, uvMinSize.z);
                float usePerObj = max(useForcedUV, step(0.5, groupMode)) * hasUV12;
                float2 u01 = lerp(screenUV, perObjUV01, usePerObj);
                return lerp(u01, localUV01, useForcedUV);
            }

            inline float applyFillNoise(float ph, float2 noiseUV)
            {
                float2 t1 = _Time.y * float2(_FillNoiseScrollX, _FillNoiseScrollY);
                float2 t2 = _Time.y * float2(-_FillNoiseScrollY, _FillNoiseScrollX) * 0.73;
                float t = _Time.y;

                float baseN = fbm4(noiseUV * _FillNoiseScale + t1);
                float warpN = fbm4(noiseUV * (_FillNoiseScale * 1.87) + float2(7.13, 19.41) + t2);
                float detailN = fbm4(noiseUV * (_FillNoiseScale * 3.41) + float2(13.7, 2.9) - t1 * 1.37);

                float signedBase = (baseN - 0.5) * 2.0;
                float shaped = sign(signedBase) * pow(abs(signedBase), max(_FillNoiseContrast, 1e-4));
                float warp = (warpN - 0.5) * 2.0;
                float detail = (detailN - 0.5) * 2.0;

                float style = floor(_FillNoiseStyle + 0.5);
                float styleMix = saturate(_FillNoiseStyleMix);
                float breakup = saturate(_FillNoiseBreakup);
                float jitterAmt = saturate(_FillNoiseJitter);

                float phaseOffset = shaped * _FillNoiseStrength + warp * (_FillNoiseWarp * 0.35);

                if (style > 0.5 && style < 1.5)
                {
                    // 液態：多一層流體感位移，邊界會像液體被拉扯
                    float liquid = fbm4((noiseUV + warp * 0.18) * (_FillNoiseScale * 1.2) + t1 * 1.35 + detail * 0.15);
                    float liquidSigned = (liquid - 0.5) * 2.0;
                    phaseOffset += lerp(0.0, liquidSigned * (_FillNoiseStrength * 0.85) + warp * (_FillNoiseWarp * 0.6), styleMix);
                }
                else if (style > 1.5 && style < 2.5)
                {
                    // 雲霧：大塊團狀分布，比較柔和、比較像雲在飄
                    float cloud = fbm4(noiseUV * (_FillNoiseScale * 0.62) + t1 * 0.58 + float2(5.3, 11.2));
                    float cloud2 = fbm4(noiseUV * (_FillNoiseScale * 1.08) - t2 * 0.42 + float2(19.1, 3.7));
                    float cloudy = ((cloud * 0.68 + cloud2 * 0.32) - 0.5) * 2.0;
                    cloudy = sign(cloudy) * pow(abs(cloudy), 0.75);
                    phaseOffset += lerp(0.0, cloudy * (_FillNoiseStrength * 1.15), styleMix);
                    phaseOffset += warp * (_FillNoiseWarp * 0.18 * styleMix);
                }
                else if (style > 2.5 && style < 3.5)
                {
                    // 碎裂：用門檻切斷部分區塊，讓色帶有斷裂、破碎、碎片跳段感
                    float cellA = fbm4(noiseUV * (_FillNoiseScale * 1.55) + t1 * 0.75 + float2(17.4, 9.2));
                    float cellB = fbm4(noiseUV * (_FillNoiseScale * 4.6) - t2 * 0.55 + float2(1.7, 23.6));
                    float gate = saturate((cellA - (0.48 + breakup * 0.28)) / max(0.02, 0.18 - breakup * 0.12));
                    float shard = ((cellB - 0.5) * 2.0) * (0.35 + gate * 0.65);
                    phaseOffset += lerp(0.0, shard * (_FillNoiseStrength * 1.45), styleMix);
                    phaseOffset += sign(shaped) * gate * breakup * _FillNoiseStrength * 0.75 * styleMix;
                }
                else if (style > 3.5)
                {
                    // 火焰/電流：上竄、抖動、細碎跳動，比較動態強烈
                    float flicker = sin(t * (7.5 + jitterAmt * 18.0) + noiseUV.y * 9.0 + detail * 2.3);
                    float flame = fbm4(float2(noiseUV.x * (_FillNoiseScale * 0.85) + warp * 0.22,
                                              noiseUV.y * (_FillNoiseScale * 1.65) - t * (0.8 + jitterAmt * 1.8)));
                    float arcs = fbm4(noiseUV * (_FillNoiseScale * 3.8) + float2(31.1, 4.8) + t2 * 1.6);
                    float flameSigned = ((flame - 0.5) * 1.7 + flicker * 0.35);
                    float arcSigned = sign((arcs - 0.5) * 2.0) * pow(abs((arcs - 0.5) * 2.0), 0.55);
                    phaseOffset += lerp(0.0, flameSigned * (_FillNoiseStrength * 1.1) + arcSigned * jitterAmt * 0.22, styleMix);
                    phaseOffset += warp * (_FillNoiseWarp * (0.22 + jitterAmt * 0.5) * styleMix);
                }

                ph += phaseOffset;
                return ph;
            }
            
            inline float2 centerPx(){ return _RadialCenter.xy * _ScreenParams.xy; }
            inline float angle01_from_px(float2 posPx){
                float2 d = posPx - centerPx();
                float ang = atan2(d.y, d.x); return frac((ang / 6.2831853) + 0.5);
            }

            v2f vert(appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv  = TRANSFORM_TEX(v.uv, _MainTex);
                #if defined(_PARTICLEMODE_ON)
                o.uvMinSize = float4(0,0,1,1); // 粒子：不要吃到 ParticleSystem 的 UV1/UV2（常是 flipbook/自訂資料）
                #else
                o.uvMinSize = float4(v.uv1.xy, v.uv2.xy);
                #endif

                o.screenPos = ComputeScreenPos(o.pos);
                o.localPos = v.vertex;
                float4 wpos = mul(unity_ObjectToWorld, v.vertex);
                o.wxy = wpos.xy;
                float2 col0 = float2(unity_ObjectToWorld._m00, unity_ObjectToWorld._m01);
                float2 col1 = float2(unity_ObjectToWorld._m10, unity_ObjectToWorld._m11);
                o.objScaleXY = float2(length(col0), length(col1));
                o.color = v.color;
                return o;
            }

            half sweepBand_screen_linear(float2 posPx, float angleDeg, float ppc, float wPx, float fPx, float t)
            {
                float2 dir = dirFromAngle(angleDeg);
                float ph = frac( dot(posPx, dir) / max(ppc, 1e-4) + t );
                float d  = abs(ph - 0.5);
                float w  = wPx / max(ppc, 1e-4);
                float ff = fPx / max(ppc, 1e-4);
                w = max(w, 0); ff = max(ff, 1e-5);
                return saturate(1.0 - smoothstep(w, w + ff, d));
            }
           
            half sweepBand_object_linear(float2 wxy, float2 scaleXY, float angleDeg, float tiling, float widthWU, float featherWU, float t, float scaleComp)
            {
                float2 dir = dirFromAngle(angleDeg);
                float sEff = length(float2(scaleXY.x*dir.x, scaleXY.y*dir.y)); 
                sEff = max(sEff, 1e-5);
                float scaleMultiplier = lerp(1.0, sEff, scaleComp);
                float proj = dot(wxy, dir);
                float ph = frac(proj * tiling + t);
                float d  = abs(ph - 0.5);
                float wn = max(widthWU,   1e-5) * tiling * scaleMultiplier;
                float fn = max(featherWU, 1e-5) * tiling * scaleMultiplier;
                wn = max(wn, 0); fn = max(fn, 1e-5);
                return saturate(1.0 - smoothstep(wn, wn + fn, d));
            }

            // ★★★ 核心修正函數：修復放射中心與螺旋邏輯 ★★★
            float calcLayerHue(float flowMode, float2 posPx, float2 screenUV, float2 uv, float4 uvMinSize, float2 objScaleXY, 
                   float angle, float speed, float density, 
                   float2 mainTexTexelSize, float4 screenParams,
                   float groupMode, float followObjScale, float objFreqGain,
                   float objPixelsPerCycle, float objTiling, float objUsePx, float objScaleComp,
                   float sweepRefHeight, float sweepPixelsPerCycle, float fillRefHeight, float fillPixelsPerCycle,
                   float radialTurns, float spiralScale, float radialBands, float4 radialCenter, float perObjCoord)
{
    float baseTime = frac(_Time.y * speed);
    float phCycles = 0.0;

    // UV1/UV2: 由 C# MeshEffect 提供
    float2 localUV01  = uvMinSize.xy;   // 每字 0..1 (TEXCOORD1.xy)
    float2 globalUV01 = uvMinSize.zw;   // 整串 0..1 (TEXCOORD2.xy)
    float2 perObjUV01 = (perObjCoord < 0.5) ? localUV01 : globalUV01;

    float uv12Mag = max(abs(localUV01.x) + abs(localUV01.y), abs(globalUV01.x) + abs(globalUV01.y));
    // 用 float flag 取代 bool（避免部分平台對動態 bool 分支行為不一致）
    float hasUV12 = step(1e-4, uv12Mag);

    // 舊版相容：用 uvMinSize.z > 50 當作強制 LocalUV 訊號
    float useForcedUV = step(50.0, uvMinSize.z);


    float2 dir = dirFromAngle(angle);
    float2 centerOffset = radialCenter.xy;

    // --------------------
    // Mode 0: Linear
    // --------------------
    if (flowMode < 0.5)
    {
        // (A) 每物件：用 LocalUV01 / GlobalUV01 形成「每字同分布」或「整串連續」
        float perObjCond = max(useForcedUV, step(0.5, groupMode)) * hasUV12;
        if (perObjCond > 0.5)
        {
            float2 u01 = lerp(perObjUV01, localUV01, useForcedUV);
            float  til = max(objTiling, 1e-4);

            // 用虛擬像素尺度，避免平台/解析度差異造成密度漂移
            float2 u = (u01 * til) - (0.5 * til);
            float  dist = dot(u, dir) * 1000.0;

            // 若你要「每物件循環像素」就用 objPixelsPerCycle；否則仍以 fillPixelsPerCycle 當尺度
            float ppc = (objUsePx > 0.5) ? max(objPixelsPerCycle, 1.0) : max(fillPixelsPerCycle, 1.0);

            // density 越大 → 越密（ppc 越小）
            ppc = ppc / max(density, 1e-4);
            // 頻率增益：越大越密
            ppc = ppc / max(objFreqGain, 1e-4);

            phCycles = dist / max(ppc, 1e-4) + baseTime;
        }
        // (B) 整體：用螢幕像素座標（整串同步）
        else
        {
            float dist = dot(posPx, dir);

            float ppc = max(fillPixelsPerCycle, 1.0);

            // RefHeight Safe：fillRefHeight <= 1 表示不做跨解析度縮放
            if (fillRefHeight > 1.0)
                ppc *= (screenParams.y / max(fillRefHeight, 1.0));

            ppc = ppc / max(density, 1e-4);
            ppc = ppc / max(objFreqGain, 1e-4);

            phCycles = dist / max(ppc, 1e-4) + baseTime;
        }
    }
    // --------------------
    // Mode 1: Radial Angle
    // --------------------
    else if (flowMode < 1.5)
    {
        float2 u01 = lerp(screenUV, perObjUV01, max(useForcedUV, step(0.5, groupMode)));
        float2 targetUV = (u01 - 0.5) - centerOffset;

        // 螢幕座標做長寬比修正，避免圓變橢圓
        if (max(useForcedUV, step(0.5, groupMode)) < 0.5)
            targetUV.x *= (screenParams.x / screenParams.y);

        float angle01 = (atan2(targetUV.y, targetUV.x) / 6.2831853) + 0.5;
        float turns = radialTurns * density * objFreqGain;
        phCycles = angle01 * turns + baseTime;
    }
    // --------------------
    // Mode 2: Spiral
    // --------------------
    else if (flowMode < 2.5)
    {
        float2 u01 = lerp(screenUV, perObjUV01, max(useForcedUV, step(0.5, groupMode)));
        float2 targetUV = (u01 - 0.5) - centerOffset;

        if (max(useForcedUV, step(0.5, groupMode)) < 0.5)
            targetUV.x *= (screenParams.x / screenParams.y);

        float angle01 = (atan2(targetUV.y, targetUV.x) / 6.2831853) + 0.5;
        float dist = length(targetUV);
        float effectiveSpiral = spiralScale * density;

        phCycles = angle01 * radialTurns + (dist * effectiveSpiral) + baseTime;
    }
    // --------------------
    // Mode 3: Bands
    // --------------------
    else
    {
        float2 u01 = lerp(screenUV, perObjUV01, max(useForcedUV, step(0.5, groupMode)));
        float2 targetUV = (u01 - 0.5) - centerOffset;

        if (max(useForcedUV, step(0.5, groupMode)) < 0.5)
            targetUV.x *= (screenParams.x / screenParams.y);

        float dist = length(targetUV);
        phCycles = dist * radialBands * density + baseTime;
    }

    return phCycles;
}

half3 calcDiamondSpec(sampler2D normTex, float2 baseUV, float tiling, float scrollX, float scrollY, float sparkleSpeed, 
                                   float normalFlat, float contrast, float lightZ, float softShininess, float hardShininess, float intensity)
            {
                float2 diamondUV = baseUV * tiling;
                diamondUV.x += _Time.y * scrollX; 
                diamondUV.y += _Time.y * scrollY;
                
                half4 normSample = tex2D(normTex, diamondUV);
                half3 normal = UnpackNormal(normSample);
                normal = lerp(normal, half3(0,0,1), normalFlat); 
                normal = normalize(normal);
                
                float t = _Time.y * sparkleSpeed; 
                half3 lightDir = normalize(half3(cos(t)*2.0, sin(t)*2.0, lightZ));
                half NdotL = dot(normal, lightDir);
                half diff = (NdotL * 0.5) + 0.5; 
                diff = pow(diff, contrast);
                
                half3 viewDir = half3(0,0,1);
                half3 halfVec = normalize(lightDir + viewDir);
                half NdotH = saturate(dot(normal, halfVec));
                half softSpec = pow(NdotH, softShininess) * 0.4;
                half hardSpec = pow(NdotH, hardShininess) * 1.0;
                
                return (softSpec + hardSpec) * intensity * diff;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                fixed4 src = tex2D(_MainTex, i.uv);
                fixed  a   = src.a;
                #ifdef UNITY_UI_CLIP_RECT
                a *= UnityGet2DClipping(i.localPos.xy, _ClipRect);
                #endif
                float2 screenUV = i.screenPos.xy / i.screenPos.w;   // 0..1
                float2 posPx    = screenUV * _ScreenParams.xy;      // pixels
                fixed3 rgb = lerp(fixed3(1,1,1), src.rgb, _UseSrcRGB);
                
                half band = 0.0;
                float tSweep = _Time.y * _SweepSpeed;
                
                float aw      = max(fwidth(a), 1e-4);
                float edgeAA  = (a - _FillAlphaCut) / (aw * max(_FillEdgeAA, 1e-4));
                half fillMask = saturate(edgeAA);
                half fillMaskGate = 1.0;

                // === Fill (Rainbow) ===
                #ifdef _FILL_ON
                {
                    float ph1 = calcLayerHue(_FillFlowMode, posPx, screenUV, i.uv, i.uvMinSize, i.objScaleXY,
                                  _FillAngle, _FillSpeed, _FillDensityAnim,
                        _MainTex_TexelSize.xy, _ScreenParams, _FillGroupMode, _FillFollowObjectScale, _FillObjFreqGain,
                        _FillObjPixelsPerCycle, _FillObjTiling, _FillObjUsePx, _FillObjScaleComp,
                        _SweepRefHeight, _SweepPixelsPerCycle, _FillRefHeight, _FillPixelsPerCycle,
                        _FillRadialTurns, _FillSpiralScale, _FillRadialBands, _FillRadialCenter, _FillPerObjCoord);

                    #ifdef _FILL_NOISE_ON
                    {
                        float2 fillNoiseUV = calcFillNoiseUV(screenUV, i.uvMinSize, _FillGroupMode, _FillPerObjCoord);
                        ph1 = applyFillNoise(ph1, fillNoiseUV);
                    }
                    #endif
                    
                    float hue1 = frac(_FillHue + ph1);
                    half3 col1 = hsv2rgb(half3(hue1, _FillSaturation, 1.0));

                    #ifdef _FILL_L2_ON
                    {
                        float ph2 = calcLayerHue(_FillFlowMode, posPx, screenUV, i.uv, i.uvMinSize, i.objScaleXY,
                            _FillL2Angle, _FillL2Speed, _FillDensityAnim * _FillL2Density,
                             _MainTex_TexelSize.xy, _ScreenParams, _FillGroupMode, _FillFollowObjectScale, _FillObjFreqGain,
                            _FillObjPixelsPerCycle, _FillObjTiling, _FillObjUsePx, _FillObjScaleComp,
                            _SweepRefHeight, _SweepPixelsPerCycle, _FillRefHeight, _FillPixelsPerCycle,
                           _FillRadialTurns, _FillSpiralScale, _FillRadialBands, _FillRadialCenter, _FillPerObjCoord);
                        #ifdef _FILL_NOISE_ON
                        {
                            float2 fillNoiseUV = calcFillNoiseUV(screenUV, i.uvMinSize, _FillGroupMode, _FillPerObjCoord);
                            ph2 = applyFillNoise(ph2, fillNoiseUV + float2(3.17, 5.83));
                        }
                        #endif
                        float hue2 = frac(_FillHue + ph2);
                        half3 col2 = hsv2rgb(half3(hue2, _FillSaturation, 1.0));
                        col1 = lerp(col1, col2, _FillL2Mix);
                    }
                    #endif

                    half3 fillCol = col1 * _FillIntensity;
                    // 細節強化：保留原本色相，但讓彩虹對比更明確。0=原始，1=更銳利/更飽滿。
                    half3 boostedFillCol = saturate((fillCol - 0.5) * 1.35 + 0.5) * _FillIntensity;
                    fillCol = lerp(fillCol, boostedFillCol, saturate(_FillDetailBoost));
                    fillCol = lerp(fillCol, half3(1,1,1), _FillSoftWhite);

                    if (_FillBlueBrightness > 1.0001 || _FillBlueLift > 0.0001)
                    {
                        half blueMask = calcBlueHueMask(fillCol, _FillBlueRange);
                        fillCol = lerp(fillCol, min(fillCol * _FillBlueBrightness, 2.0), blueMask);
                        half3 blueLiftCol = max(fillCol, half3(0.12, 0.62, 1.0) * max(max(fillCol.r, max(fillCol.g, fillCol.b)), 1.0));
                        fillCol = lerp(fillCol, min(blueLiftCol, 2.0), blueMask * saturate(_FillBlueLift));
                    }
                    
                    #ifdef _FILL_MASK_ON
                    {
                        half maskVal = sampleMaskSmooth(_FillMaskTex, i.uv, _FillMaskFeatherPx, _FillMaskInvert, _MainTex_TexelSize);
                        fillMaskGate = maskVal;
                        fillMask *= maskVal; 
                    }
                    #endif

                    // === DIAMOND OVERLAY ===
                    #ifdef _DIAMOND_ON
                    {
                        fillCol = lerp(fillCol, fillCol * 0.3, _DiamondBaseDim);
                        half3 spec1 = calcDiamondSpec(_DiamondTex, i.uv, _DiamondTiling, _DiamondScrollX, _DiamondScrollY, _DiamondSparkleSpeed,
                                                       _DiamondNormalFlat, _DiamondContrast, _DiamondLightZ, _DiamondSoftShininess, _DiamondHardShininess, _DiamondIntensity);
                        half3 specTotal = spec1;
                        
                        #ifdef _DIAMOND_L2_ON
                        {
                             half3 spec2 = calcDiamondSpec(_DiamondTex, i.uv, _DiamondL2Tiling, _DiamondL2ScrollX, _DiamondL2ScrollY, _DiamondL2SparkleSpeed,
                                                       _DiamondNormalFlat, _DiamondContrast, _DiamondLightZ, _DiamondSoftShininess, 
                                                       _DiamondHardShininess, _DiamondIntensity);
                            specTotal += spec2 * _DiamondL2Mix;
                        }
                        #endif

                        if (_DiamondLoopSec > 0.01) {
                            float tLoop = fmod(_Time.y, _DiamondLoopSec);
                            float feather = 0.2;
                            float timeMask = smoothstep(0.0, feather, tLoop) * smoothstep(_DiamondLoopDur, _DiamondLoopDur - feather, tLoop);
                            float currentScale = lerp(_DiamondIdle, 1.0, timeMask);
                            specTotal *= currentScale;
                        } 
                        
                        fillCol += specTotal;
                        fillCol = min(fillCol, 2.0); 
                    }
                    #endif

                    if (_FillFlashEnable > 0.5)
                    {
                        float flashPhase = sin(_Time.y * max(_FillFlashFrequency, 0.001) * 6.2831853) * 0.5 + 0.5;
                        half flash = smoothstep(0.35, 1.0, flashPhase) * saturate(_FillFlashStrength) * _FillFlashColor.a;
                        fillCol = lerp(fillCol, _FillFlashColor.rgb * max(_FillIntensity, 1.0), flash);
                    }
                    
                    half3 blendCol = fillCol;
                    if (_FillBlendMode >= 0.5)
                    {
                        half3 baseRgb = rgb;
                        half3 safeFillCol = saturate(fillCol);
                        if (_FillBlendMode < 1.5)
                        {
                            blendCol = lerp(2.0 * baseRgb * safeFillCol,
                                            1.0 - 2.0 * (1.0 - baseRgb) * (1.0 - safeFillCol),
                                            step(0.5, baseRgb));
                        }
                        else if (_FillBlendMode < 2.5)
                        {
                            blendCol = 1.0 - (1.0 - baseRgb) * (1.0 - safeFillCol);
                        }
                        else
                        {
                            blendCol = saturate(baseRgb + fillCol * 0.5);
                        }
                    }
                    half particleCoverage = a * fillMaskGate * saturate(_ParticleFillCoverage);
                    half fillBlendMask = max(fillMask, particleCoverage);
                    rgb = lerp(rgb, blendCol, fillBlendMask * saturate(_FillBlendStrength));
                }
                #endif
                
                // === Inner Sweep ===
                #ifdef _INNER_SWEEP_ON
                {
                    float2 dirIn = dirFromAngle(_InnerSweepAngle);
                    float tIn = _Time.y * _InnerSweepSpeed;

                    float proj = dot(i.uv, dirIn);
                    float ph = frac(proj * _InnerSweepDensity + tIn);

                    float d = abs(ph - 0.5);
                    float w = _InnerSweepWidth * 0.5; 
                    float f = max(_InnerSweepFeather, 0.001);
                    half inBand = saturate(1.0 - smoothstep(w, w + f, d));
                    
                    inBand *= a;
                    inBand *= tex2D(_InnerSweepMaskTex, i.uv).r;

                    half3 inCol = _InnerSweepColor.rgb;
                    half finalInt = inBand * _InnerSweepIntensity;

                    if (_InnerSweepBlend < 0.5) {
                        rgb += inCol * finalInt;
                    } else {
                        rgb = lerp(rgb, inCol, saturate(finalInt));
                    }
                }
                #endif

                // === Outer Sweep ===
                #ifdef _SWEEP_ON
                {
                    band = 0.0;
                    if (_SweepFlowMode < 0.5) // Linear
                    {
                        if (_SweepGroupMode < 0.5) // Unified
                        {
                            if (_SweepUseObject > 0.5) band = sweepBand_object_linear(i.wxy, i.objScaleXY, _SweepAngle, _SweepObjTiling, _SweepObjWidth, _SweepObjFeather, tSweep, _SweepObjScaleComp);
                            else {
                                float ppc_in = max(_SweepPixelsPerCycle, 1e-3) * (_ScreenParams.y / max(_SweepRefHeight, 1.0));
                                band = sweepBand_screen_linear(posPx, _SweepAngle, ppc_in, _SweepWidthPx, _SweepFeatherPx, tSweep);
                            }
                        }
                        else // Per Object
                        {
                            // C# 腳本同步支援：使用 float flag，避免部分行動平台對動態 bool 分支不穩定。
                            float useForcedUV = step(50.0, i.uvMinSize.z);
                            float uv12Mag = max(abs(i.uvMinSize.x) + abs(i.uvMinSize.y), abs(i.uvMinSize.z) + abs(i.uvMinSize.w));
                            float hasUV12 = step(1e-6, uv12Mag);

                            if (max(useForcedUV, hasUV12) > 0.5)
                            {
                                // [C# Mode] TEXCOORD1.xy 是每字 LocalUV 0..1；TEXCOORD2.xy 可保留給整串 GlobalUV。
                                float2 localPos = i.uvMinSize.xy - 0.5;
                                band = sweepBand_object_linear(localPos, float2(1,1), _SweepAngle, 1.0, _SweepObjWidth, _SweepObjFeather, tSweep, 0.0);
                            }
                            else
                            {
                                if (_SweepUseObject > 0.5)
                                {
                                    band = sweepBand_object_linear(i.wxy, i.objScaleXY, _SweepAngle, _SweepObjTiling, _SweepObjWidth, _SweepObjFeather, tSweep, _SweepObjScaleComp);
                                }
                                else
                                {
                                    float ppcFallback = max(_SweepPixelsPerCycle, 1e-3) * (_ScreenParams.y / max(_SweepRefHeight, 1.0));
                                    band = sweepBand_screen_linear(posPx, _SweepAngle, ppcFallback, _SweepWidthPx, _SweepFeatherPx, tSweep);
                                }
                            }
                        }
                    }
                    else if (_SweepFlowMode < 1.5) { // RadialAngle
                        float ppc_in = max(_SweepPixelsPerCycle, 1e-3) * (_ScreenParams.y / max(_SweepRefHeight, 1.0));
                        float ph = frac( angle01_from_px(posPx) * _RadialTurns + tSweep ); float d  = abs(ph - 0.5);
                        float w  = max(_SweepWidthPx,   1e-4) / ppc_in; float ff = max(_SweepFeatherPx, 1e-4) / ppc_in;
                        float sum = min(w + ff, 0.499); w = min(w, sum); ff = max(sum - w, 1e-5);
                        band = saturate(1.0 - smoothstep(w, w+ff, d));
                    }
                    
                    band *= a;
                    #ifdef _SWEEP_MASK_ON
                    {
                         band *= sampleMaskSmooth(_SweepMaskTex, i.uv, _SweepMaskFeatherPx, _SweepMaskInvert, _MainTex_TexelSize);
                    }
                    #endif
                    
                    // 修正：未開 Fill Mask 時，不再因預設 1.0 導致外掃光被整個排除。
                    if (_SweepExcludeFill > 0.5)
                    {
                        half fillMaskTexVal = fillMask;
                        #ifdef _FILL_MASK_ON
                        {
                            fillMaskTexVal = sampleMaskSmooth(_FillMaskTex, i.uv, _FillMaskFeatherPx, _FillMaskInvert, _MainTex_TexelSize);
                        }
                        #endif
                        band *= (1.0 - saturate(fillMaskTexVal));
                    }
                    
                    half3 sweepCol = (_SweepUseGradient>0.5) ? tex2D(_SweepGradient, float2(frac(tSweep), 0.5)).rgb : _SweepColor.rgb;
                    sweepCol *= _SweepColorIntensity;
                    if (_SweepColorMode < 0.5) rgb = saturate(rgb + sweepCol * band);
                    else if (_SweepColorMode < 1.5) rgb = 1.0 - (1.0 - rgb) * (1.0 - saturate(band * sweepCol));
                    else rgb = lerp(rgb, sweepCol, saturate(band));
                }
                #endif

                rgb *= i.color.rgb;
                fixed outA = a * i.color.a * _Alpha;
                if (_DebugView > 0.5) return fixed4(a, 0, 0, 1);
                #ifdef UNITY_UI_ALPHACLIP
                clip(outA - 0.001);
                #endif
                return fixed4(rgb, outA);
            }
            ENDCG
        }
    }
    CustomEditor "BMFontRainbowArtistShaderGUI"
    FallBack Off
}
