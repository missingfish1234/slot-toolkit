Shader "ArkGame/UI-Spine/Dissolve Multi Mode"
{
    Properties
    {
        [PerRendererData] _MainTex ("主貼圖 Main Texture", 2D) = "white" {}
        _Color ("整體顏色 Tint", Color) = (1,1,1,1)

        [Header(Dissolve Core)]
        _DissolveAmount ("溶解進度 Dissolve Amount", Range(0,1)) = 0
        [Toggle] _AutoDissolve ("Auto Dissolve By Time", Float) = 0
        [HideInInspector] _DissolveStartTime ("Dissolve Start Time", Float) = 0
        _DissolveDelay ("Delay Time", Float) = 0
        _DissolveDuration ("Duration", Float) = 1
        [Toggle] _ReverseAutoDissolve ("Reverse Auto Dissolve", Float) = 0
        [KeywordEnum(Noise, Linear, Radial, Ring, Spiral, Stripe, CenterVertical, Ink)]
        _DissolveMode ("Dissolve Mode", Float) = 0
        [Toggle] _InvertDissolve ("反轉溶解 Invert", Float) = 0

        [Header(Ink Dissolve)]
        _InkSoftness ("Ink Softness", Range(0.01,1)) = 0.35
        _InkNoise ("Ink Noise", Range(0,1)) = 0.65

        [Header(Noise Texture)]
        _NoiseTex ("溶解雜訊 Noise Texture", 2D) = "white" {}

        [Header(Old Noise Control)]
        _NoiseScale ("雜訊縮放 Noise Scale", Range(0.1,20)) = 4
        _NoiseStrength ("雜訊影響 Noise Strength", Range(0,1)) = 0.65
        _NoiseSpeed ("雜訊流動速度 Noise Speed", Vector) = (0,0,0,0)

        [Header(Anti Square Noise Mix)]
        _BigNoiseScale ("大破洞尺寸 Big Hole Scale", Range(0.1,20)) = 2.5
        _DetailNoiseScale ("細節尺寸 Detail Scale", Range(1,80)) = 18
        _DetailNoiseStrength ("細節強度 Detail Strength", Range(0,1)) = 0.35
        _UVRandomRotate ("打散方塊感 UV Rotate Mix", Range(0,1)) = 0.6

        [Header(Direction)]
        _DirectionAngle ("方向角度 Direction Angle", Range(0,360)) = 0
        _Origin ("中心點 Origin XY", Vector) = (0.5,0.5,0,0)

        [Header(Ring Spiral Stripe)]
        _RingWidth ("環形寬度 Ring Width", Range(0.01,1)) = 0.35
        _SpiralTurns ("螺旋圈數 Spiral Turns", Range(0,12)) = 4
        _StripeCount ("條紋數量 Stripe Count", Range(1,80)) = 12
        _StripeSoftness ("條紋柔邊 Stripe Softness", Range(0.001,0.5)) = 0.08

        [Header(Edge Glow)]
        _EdgeWidth ("外層光暈寬度 Glow Width", Range(0,0.5)) = 0.08
        _EdgeSoftness ("邊緣柔和 Edge Softness", Range(0.001,0.3)) = 0.05
        _EdgeCoverWidth ("黑邊覆蓋寬度 Cover Width", Range(0,0.25)) = 0.025
        _EdgeCoverStrength ("黑邊覆蓋強度 Cover Strength", Range(0,1)) = 1
        _EdgeAlphaBoost ("覆蓋帶不透明補強 Alpha Boost", Range(0,1)) = 1
        _EdgeColor ("邊緣顏色 Edge Color", Color) = (1,0.45,0.05,1)
        _EdgeIntensity ("邊緣亮度 Edge Intensity", Range(0,8)) = 2.5
        [Toggle] _EdgeAdditive ("外層光暈加亮 Additive Glow", Float) = 1
        [Toggle] _RainbowEdgeGlow ("彩光光暈 Rainbow Glow", Float) = 0
        _RainbowEdgeSpeed ("彩光流動速度 Rainbow Speed", Range(0,6)) = 1.5
        _RainbowEdgeScale ("彩光密度 Rainbow Scale", Range(0,12)) = 4

        [Header(Alpha Control)]
        _AlphaCutoff ("透明裁切 Alpha Cutoff", Range(0,1)) = 0.001
        _AlphaPower ("透明強度 Alpha Power", Range(0.1,3)) = 1

        [Header(Blend Mode)]
        [Enum(UnityEngine.Rendering.BlendMode)] _SrcBlend ("Src Blend", Float) = 5
        [Enum(UnityEngine.Rendering.BlendMode)] _DstBlend ("Dst Blend", Float) = 10

        [Header(Unity UI Mask Support)]
        _StencilComp ("Stencil Comparison", Float) = 8
        _Stencil ("Stencil ID", Float) = 0
        _StencilOp ("Stencil Operation", Float) = 0
        _StencilWriteMask ("Stencil Write Mask", Float) = 255
        _StencilReadMask ("Stencil Read Mask", Float) = 255
        _ColorMask ("Color Mask", Float) = 15

        [Toggle(UNITY_UI_ALPHACLIP)] _UseUIAlphaClip ("Use Alpha Clip", Float) = 0
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
        Lighting Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend [_SrcBlend] [_DstBlend]
        ColorMask [_ColorMask]

        Pass
        {
            Name "Dissolve"

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 2.0

            #pragma multi_compile_local _ UNITY_UI_CLIP_RECT
            #pragma multi_compile_local _ UNITY_UI_ALPHACLIP

            #include "UnityCG.cginc"
            #include "UnityUI.cginc"

            sampler2D _MainTex;
            sampler2D _NoiseTex;

            float4 _MainTex_ST;
            float4 _NoiseTex_ST;
            fixed4 _Color;
            fixed4 _TextureSampleAdd;

            float _DissolveAmount;
            float _AutoDissolve;
            float _DissolveStartTime;
            float _DissolveDelay;
            float _DissolveDuration;
            float _ReverseAutoDissolve;
            float _DissolveMode;
            float _InvertDissolve;

            float _InkSoftness;
            float _InkNoise;

            float _NoiseScale;
            float _NoiseStrength;
            float4 _NoiseSpeed;

            float _BigNoiseScale;
            float _DetailNoiseScale;
            float _DetailNoiseStrength;
            float _UVRandomRotate;

            float _DirectionAngle;
            float4 _Origin;

            float _RingWidth;
            float _SpiralTurns;
            float _StripeCount;
            float _StripeSoftness;

            float _EdgeWidth;
            float _EdgeSoftness;
            float _EdgeCoverWidth;
            float _EdgeCoverStrength;
            float _EdgeAlphaBoost;
            fixed4 _EdgeColor;
            float _EdgeIntensity;
            float _EdgeAdditive;
            float _RainbowEdgeGlow;
            float _RainbowEdgeSpeed;
            float _RainbowEdgeScale;

            float _AlphaCutoff;
            float _AlphaPower;

            float4 _ClipRect;

            struct appdata_t
            {
                float4 vertex   : POSITION;
                fixed4 color    : COLOR;
                float2 texcoord : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f
            {
                float4 vertex        : SV_POSITION;
                fixed4 color         : COLOR;
                float2 uv            : TEXCOORD0;
                float4 worldPosition : TEXCOORD1;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata_t v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);

                o.worldPosition = v.vertex;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.texcoord, _MainTex);
                o.color = v.color * _Color;

                return o;
            }

            float Hash21(float2 p)
            {
                p = frac(p * float2(123.34, 456.21));
                p += dot(p, p + 45.32);
                return frac(p.x * p.y);
            }

            float2 RotateUV(float2 uv, float angle)
            {
                float s = sin(angle);
                float c = cos(angle);

                uv -= 0.5;

                float2 r;
                r.x = uv.x * c - uv.y * s;
                r.y = uv.x * s + uv.y * c;

                return r + 0.5;
            }

            float SampleTextureNoise(float2 uv)
            {
                return tex2D(_NoiseTex, TRANSFORM_TEX(uv, _NoiseTex)).r;
            }

            float SampleNoise(float2 uv)
            {
                float bigScale = max(_BigNoiseScale, 0.001);
                float detailScale = max(_DetailNoiseScale, 0.001);
                float oldScale = max(_NoiseScale, 0.001);

                float2 speed = _NoiseSpeed.xy * _Time.y;

                // 主大洞層：控制大破洞，但不再用極低 Noise Scale 硬放大。
                float2 uvBig = uv * bigScale;
                uvBig += speed;

                // 中細節層：旋轉 60 度，打散貼圖本身的方形方向。
                float2 uvMidBase = lerp(uv, RotateUV(uv, 1.0472), _UVRandomRotate);
                float2 uvMid = uvMidBase * detailScale;
                uvMid += speed * float2(-0.73, 0.91);

                // 高細節層：反向旋轉，補細碎破邊。
                float2 uvFineBase = lerp(uv, RotateUV(uv, -0.61), _UVRandomRotate);
                float2 uvFine = uvFineBase * detailScale * 2.37;
                uvFine += speed * float2(0.42, -0.58);

                // 舊參數保留：讓原本 Noise Scale 仍有影響，但不會主導整體。
                float2 uvOld = RotateUV(uv, 0.37) * oldScale;
                uvOld += speed * 0.5;

                float nBig = SampleTextureNoise(uvBig);
                float nMid = SampleTextureNoise(uvMid);
                float nFine = SampleTextureNoise(uvFine);
                float nOld = SampleTextureNoise(uvOld);

                // 程序雜訊：避免貼圖圖樣太明顯。
                float h = Hash21(floor(uvFine * 64.0));

                // 大洞基底。
                float n = nBig;

                // 加入細節：Detail Strength 越高，破洞邊緣越碎，越不容易看到方形。
                float detailMix = saturate(_DetailNoiseStrength);
                float detail = nMid * 0.65 + nFine * 0.25 + h * 0.10;

                n = lerp(n, n * 0.65 + detail * 0.35, detailMix);

                // 舊 Noise Scale 補一點變化，避免舊材質視覺完全改變。
                n = lerp(n, nOld, 0.12);

                return saturate(n);
            }

            float DirectionMask(float2 uv)
            {
                float a = radians(_DirectionAngle);
                float2 dir = normalize(float2(cos(a), sin(a)));
                float d = dot(uv - 0.5, dir);
                return saturate(d + 0.5);
            }

            float RadialMask(float2 uv)
            {
                float2 p = uv - _Origin.xy;
                float d = length(p) * 1.41421356;
                return saturate(d);
            }

            float RingMask(float2 uv, float amount)
            {
                float2 p = uv - _Origin.xy;
                float d = length(p) * 1.41421356;
                float ring = abs(d - amount);
                float m = 1.0 - smoothstep(0.0, _RingWidth, ring);
                return saturate(m);
            }

            float SpiralMask(float2 uv)
            {
                float2 p = uv - _Origin.xy;
                float r = length(p);
                float ang = atan2(p.y, p.x) / 6.2831853 + 0.5;
                float s = frac(ang + r * _SpiralTurns);
                return s;
            }

            float StripeMask(float2 uv)
            {
                float baseDir = DirectionMask(uv);
                float s = frac(baseDir * _StripeCount);
                float stripe = smoothstep(0.0, _StripeSoftness, s) * 
                               (1.0 - smoothstep(1.0 - _StripeSoftness, 1.0, s));
                return lerp(baseDir, stripe, 0.75);
            }

            float CenterVerticalMask(float2 uv)
            {
                return saturate(abs(uv.y - _Origin.y) * 2.0);
            }

            float InkMask(float2 uv, float noise)
            {
                float radial = RadialMask(uv);
                float wash = smoothstep(0.0, max(_InkSoftness, 0.0001), radial);
                float feather = lerp(wash, noise, saturate(_InkNoise));
                return saturate(feather);
            }
            float GetDissolveAmount()
            {
                float manualAmount = saturate(_DissolveAmount);
                float timedAmount = saturate((_Time.y - _DissolveStartTime - _DissolveDelay) / max(_DissolveDuration, 0.0001));
                timedAmount = lerp(timedAmount, 1.0 - timedAmount, step(0.5, _ReverseAutoDissolve));
                return lerp(manualAmount, timedAmount, step(0.5, _AutoDissolve));
            }

            fixed3 GetRainbowEdgeColor(float2 uv, float amount)
            {
                float2 centeredUv = uv - _Origin.xy;
                float anglePhase = atan2(centeredUv.y, centeredUv.x) * 0.15915494;
                float uvPhase = dot(uv, float2(1.0, 1.37));
                float phase = anglePhase + uvPhase * _RainbowEdgeScale + amount + _Time.y * _RainbowEdgeSpeed;
                return 0.5 + 0.5 * cos(6.2831853 * (phase + fixed3(0.0, 0.3333333, 0.6666667)));
            }

            float GetPattern(float2 uv, float amount)
            {
                float noise = SampleNoise(uv);
                float pattern = noise;

                if (_DissolveMode < 0.5)
                {
                    pattern = noise;
                }
                else if (_DissolveMode < 1.5)
                {
                    pattern = DirectionMask(uv);
                }
                else if (_DissolveMode < 2.5)
                {
                    pattern = RadialMask(uv);
                }
                else if (_DissolveMode < 3.5)
                {
                    pattern = RingMask(uv, amount);
                }
                else if (_DissolveMode < 4.5)
                {
                    pattern = SpiralMask(uv);
                }
                else if (_DissolveMode < 5.5)
                {
                    pattern = StripeMask(uv);
                }
                else if (_DissolveMode < 6.5)
                {
                    pattern = CenterVerticalMask(uv);
                }
                else
                {
                    pattern = InkMask(uv, noise);
                }

                if (_DissolveMode > 0.5 && _DissolveMode < 3.5)
                {
                    pattern = lerp(pattern, noise, _NoiseStrength);
                }
                else if (_DissolveMode >= 3.5 && _DissolveMode < 6.5)
                {
                    pattern = lerp(pattern, noise, _NoiseStrength * 0.5);
                }

                if (_InvertDissolve > 0.5)
                {
                    pattern = 1.0 - pattern;
                }

                return saturate(pattern);
            }

            fixed4 frag(v2f IN) : SV_Target
            {
                fixed4 tex = tex2D(_MainTex, IN.uv) + _TextureSampleAdd;
                fixed4 col = tex * IN.color;

                #ifdef UNITY_UI_CLIP_RECT
                col.a *= UnityGet2DClipping(IN.worldPosition.xy, _ClipRect);
                #endif

                float amount = GetDissolveAmount();
                float pattern = GetPattern(IN.uv, amount);

                // signedDistance < 0：已溶解側；> 0：保留側。
                float signedDistance = pattern - amount;
                float edgeSoft = max(_EdgeSoftness, 0.0001);
                float coverWidth = max(_EdgeCoverWidth, 0.0);
                float glowWidth = max(_EdgeWidth, coverWidth);

                // 原本的保留遮罩。切線本身仍會淡出，但下方的實色覆蓋帶會補回邊緣。
                float keep = smoothstep(0.0, edgeSoft, signedDistance);

                if (_DissolveMode > 2.5 && _DissolveMode < 3.5)
                {
                    float ring = RingMask(IN.uv, amount);
                    keep = saturate(max(ring, keep));
                }

                // 實色覆蓋帶跨過切線，專門遮住溶解交界處的黑色 RGB／黑邊。
                float coverEnter = smoothstep(-coverWidth - edgeSoft, -coverWidth, signedDistance);
                float coverExit = 1.0 - smoothstep(coverWidth, coverWidth + edgeSoft, signedDistance);
                float edgeCover = saturate(coverEnter * coverExit);

                // 外層光暈從覆蓋帶開始，向保留側延伸；寬度由 Edge Width 獨立控制。
                float glowEnter = coverEnter;
                float glowExit = 1.0 - smoothstep(glowWidth, glowWidth + edgeSoft, signedDistance);
                float edgeGlow = saturate(glowEnter * glowExit);

                if (amount <= 0.001)
                {
                    keep = 1.0;
                    edgeCover = 0.0;
                    edgeGlow = 0.0;
                }

                if (amount >= 0.999)
                {
                    keep = 0.0;
                    edgeCover = 0.0;
                    edgeGlow = 0.0;
                }

                float sourceAlpha = col.a;
                float dissolveAlpha = sourceAlpha * pow(keep, _AlphaPower);
                float coverAlpha = sourceAlpha * edgeCover * saturate(_EdgeAlphaBoost);
                col.a = max(dissolveAlpha, coverAlpha);

                float coverMask = saturate(edgeCover * _EdgeCoverStrength * _EdgeColor.a);
                float glowMask = saturate(edgeGlow * _EdgeColor.a);
                fixed3 edgeColor = lerp(_EdgeColor.rgb, GetRainbowEdgeColor(IN.uv, amount), step(0.5, _RainbowEdgeGlow));
                fixed3 edgeTarget = edgeColor * _EdgeIntensity;

                // 先用實色取代原圖顏色，確保黑邊真的被遮住，而不是只在黑色上加亮。
                col.rgb = lerp(col.rgb, edgeTarget, coverMask);

                // 再疊加外層光暈。扣除實色核心，避免同一區域被重複加亮。
                float outerGlow = saturate(glowMask - coverMask);
                if (_EdgeAdditive > 0.5)
                {
                    col.rgb += edgeTarget * outerGlow;
                }
                else
                {
                    col.rgb = lerp(col.rgb, edgeTarget, outerGlow);
                }

                clip(col.a - _AlphaCutoff);

                #ifdef UNITY_UI_ALPHACLIP
                clip(col.a - 0.001);
                #endif

                return col;
            }
            ENDCG
        }
    }

    FallBack "UI/Default"
}
