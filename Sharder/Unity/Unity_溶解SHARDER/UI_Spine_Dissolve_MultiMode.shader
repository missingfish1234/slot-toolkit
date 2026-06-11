Shader "ArkGame/UI-Spine/Dissolve Multi Mode"
{
    Properties
    {
        [PerRendererData] _MainTex ("主貼圖 Main Texture", 2D) = "white" {}
        _Color ("整體顏色 Tint", Color) = (1,1,1,1)

        [Header(Dissolve Core)]
        _DissolveAmount ("溶解進度 Dissolve Amount", Range(0,1)) = 0
        [Enum(Noise,0, Linear,1, Radial,2, Ring,3, Spiral,4, Stripe,5)]
        _DissolveMode ("溶解方式 Dissolve Mode", Float) = 0
        [Toggle] _InvertDissolve ("反轉溶解 Invert", Float) = 0

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
        _EdgeWidth ("邊緣寬度 Edge Width", Range(0,0.5)) = 0.08
        _EdgeSoftness ("邊緣柔和 Edge Softness", Range(0.001,0.3)) = 0.05
        _EdgeColor ("邊緣顏色 Edge Color", Color) = (1,0.45,0.05,1)
        _EdgeIntensity ("邊緣亮度 Edge Intensity", Range(0,8)) = 2.5
        [Toggle] _EdgeAdditive ("邊緣加亮 Additive Edge", Float) = 1

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
            float _DissolveMode;
            float _InvertDissolve;

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
            fixed4 _EdgeColor;
            float _EdgeIntensity;
            float _EdgeAdditive;

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

            float RingMask(float2 uv)
            {
                float2 p = uv - _Origin.xy;
                float d = length(p) * 1.41421356;
                float ring = abs(d - _DissolveAmount);
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

            float GetPattern(float2 uv)
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
                    pattern = RingMask(uv);
                }
                else if (_DissolveMode < 4.5)
                {
                    pattern = SpiralMask(uv);
                }
                else
                {
                    pattern = StripeMask(uv);
                }

                if (_DissolveMode > 0.5 && _DissolveMode < 3.5)
                {
                    pattern = lerp(pattern, noise, _NoiseStrength);
                }
                else if (_DissolveMode >= 3.5)
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

                float pattern = GetPattern(IN.uv);
                float amount = saturate(_DissolveAmount);

                float keep = smoothstep(amount, amount + _EdgeSoftness, pattern);

                if (_DissolveMode > 2.5 && _DissolveMode < 3.5)
                {
                    float ring = RingMask(IN.uv);
                    keep = saturate(max(ring, smoothstep(amount, amount + _EdgeSoftness, pattern)));
                }

                float edgeInner = smoothstep(amount, amount + _EdgeSoftness, pattern);
                float edgeOuter = 1.0 - smoothstep(amount + _EdgeWidth, amount + _EdgeWidth + _EdgeSoftness, pattern);
                float edge = saturate(edgeInner * edgeOuter);

                if (_DissolveAmount <= 0.001)
                {
                    keep = 1.0;
                    edge = 0.0;
                }

                if (_DissolveAmount >= 0.999)
                {
                    keep = 0.0;
                    edge = 0.0;
                }

                col.a *= pow(keep, _AlphaPower);

                fixed3 edgeRGB = _EdgeColor.rgb * _EdgeIntensity * edge * _EdgeColor.a;

                if (_EdgeAdditive > 0.5)
                {
                    col.rgb += edgeRGB;
                }
                else
                {
                    col.rgb = lerp(col.rgb, _EdgeColor.rgb * _EdgeIntensity, edge);
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