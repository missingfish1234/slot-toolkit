Shader "Ark/UI/Dark Center Self Contour Glow Distortion"
{
    Properties
    {
        [Toggle(_LIGHTWEIGHT)] _Lightweight ("Lightweight (4-direction contour)", Float) = 0
        [PerRendererData] _MainTex ("Source Texture (RGBA)", 2D) = "white" {}
        _Color ("UI Tint", Color) = (1,1,1,1)

        [Header(Dark Center)]
        _CenterColor ("Center Color", Color) = (0.003,0.006,0.015,1)
        _CenterSourceMix ("Keep Original RGB", Range(0,1)) = 0.03
        _CenterOpacity ("Center Opacity", Range(0,1)) = 1

        [Header(Self Contour)]
        [HDR] _EdgeColor ("Glow Color (HDR)", Color) = (0,3,8,1)
        _EdgeWidth ("Detection Width (Pixels)", Range(0.5,12)) = 2.5
        _EdgeSharpness ("Alpha Edge Sharpness", Range(0.25,10)) = 3
        _AlphaContourAmount ("Outer Silhouette Amount", Range(0,2)) = 0.25
        _DetailContourAmount ("Self Detail Amount", Range(0,4)) = 1.5
        _DetailThreshold ("Detail Noise Threshold", Range(0,1)) = 0.035
        _DetailSoftness ("Detail Transition", Range(0.001,1)) = 0.12
        _BrightLineAmount ("Original Bright Line Amount", Range(0,4)) = 0.8
        _BrightLineThreshold ("Bright Line Threshold", Range(0,1)) = 0.3
        _BrightLineSoftness ("Bright Line Transition", Range(0.001,1)) = 0.2
        _EdgeIntensity ("Edge Intensity", Range(0,10)) = 2.25

        [Header(Outer Glow)]
        _GlowWidth ("Glow Width (Pixels)", Range(1,40)) = 10
        _GlowIntensity ("Glow Intensity", Range(0,10)) = 1.2
        _GlowOpacity ("Glow Opacity", Range(0,1)) = 0.75
        _DetailGlowAmount ("Self Detail Glow Amount", Range(0,4)) = 1.0

        [Header(Distortion)]
        _NoiseTex ("Noise Texture (Repeat)", 2D) = "gray" {}
        _NoiseScale ("Noise Scale", Range(0.1,30)) = 7
        _NoiseSpeedX ("Noise Speed X", Range(-5,5)) = 0.22
        _NoiseSpeedY ("Noise Speed Y", Range(-5,5)) = -0.31
        _DistortStrength ("UV Distortion Strength", Range(0,0.05)) = 0.003
        _WaveStrength ("Horizontal Wave Strength", Range(0,0.03)) = 0.001
        _WaveFrequency ("Horizontal Wave Frequency", Range(1,120)) = 42
        _WaveSpeed ("Horizontal Wave Speed", Range(-20,20)) = 4
        _EdgeNoiseAmount ("Edge Flicker Amount", Range(0,1)) = 0.2
        _PulseSpeed ("Glow Pulse Speed", Range(0,12)) = 2.2
        _PulseAmount ("Glow Pulse Amount", Range(0,1)) = 0.1

        [Header(Alpha)]
        _AlphaThreshold ("Alpha Threshold", Range(0,0.5)) = 0.01

        [Header(Debug)]
        [Enum(Final,0,AlphaContour,1,SelfDetail,2,BrightSource,3,CombinedContour,4)]
        _DebugView ("Debug View", Float) = 0

        [HideInInspector] _StencilComp ("Stencil Comparison", Float) = 8
        [HideInInspector] _Stencil ("Stencil ID", Float) = 0
        [HideInInspector] _StencilOp ("Stencil Operation", Float) = 0
        [HideInInspector] _StencilWriteMask ("Stencil Write Mask", Float) = 255
        [HideInInspector] _StencilReadMask ("Stencil Read Mask", Float) = 255
        [HideInInspector] _ColorMask ("Color Mask", Float) = 15
        [Toggle(UNITY_UI_ALPHACLIP)] _UseUIAlphaClip ("Use UI Alpha Clip", Float) = 0
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
        Blend SrcAlpha OneMinusSrcAlpha
        ColorMask [_ColorMask]

        Pass
        {
            Name "SelfContourGlow"

            CGPROGRAM
            #pragma target 3.0
            #pragma shader_feature_local _LIGHTWEIGHT
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_local _ UNITY_UI_CLIP_RECT
            #pragma multi_compile_local _ UNITY_UI_ALPHACLIP

            #include "UnityCG.cginc"
            #include "UnityUI.cginc"

            struct appdata_t
            {
                float4 vertex   : POSITION;
                fixed4 color    : COLOR;
                float2 texcoord : TEXCOORD0;
            };

            struct v2f
            {
                float4 vertex        : SV_POSITION;
                fixed4 color         : COLOR;
                float2 uv            : TEXCOORD0;
                float4 worldPosition : TEXCOORD1;
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            float4 _MainTex_TexelSize;
            sampler2D _NoiseTex;

            fixed4 _Color;
            fixed4 _CenterColor;
            float _CenterSourceMix;
            float _CenterOpacity;

            fixed4 _EdgeColor;
            float _EdgeWidth;
            float _EdgeSharpness;
            float _AlphaContourAmount;
            float _DetailContourAmount;
            float _DetailThreshold;
            float _DetailSoftness;
            float _BrightLineAmount;
            float _BrightLineThreshold;
            float _BrightLineSoftness;
            float _EdgeIntensity;

            float _GlowWidth;
            float _GlowIntensity;
            float _GlowOpacity;
            float _DetailGlowAmount;

            float _NoiseScale;
            float _NoiseSpeedX;
            float _NoiseSpeedY;
            float _DistortStrength;
            float _WaveStrength;
            float _WaveFrequency;
            float _WaveSpeed;
            float _EdgeNoiseAmount;
            float _PulseSpeed;
            float _PulseAmount;

            float _AlphaThreshold;
            float _DebugView;
            float4 _ClipRect;

            v2f vert(appdata_t v)
            {
                v2f o;
                o.worldPosition = v.vertex;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.texcoord, _MainTex);
                o.color = v.color * _Color;
                return o;
            }

            fixed4 SampleMain(float2 uv)
            {
                return tex2D(_MainTex, uv);
            }

            float Brightness(fixed4 c)
            {
                return max(c.r, max(c.g, c.b)) * c.a;
            }

            float ColorDifference(fixed4 center, fixed4 sampleColor)
            {
                float valid = max(center.a, sampleColor.a);
                float alphaDiff = abs(center.a - sampleColor.a);
                float rgbDiff = length(center.rgb - sampleColor.rgb) * valid;
                return max(rgbDiff, alphaDiff);
            }

            fixed4 frag(v2f i) : SV_Target
            {
                const float DIAG = 0.70710678;
                float t = _Time.y;

                float2 noiseUV1 = i.uv * _NoiseScale
                                + float2(t * _NoiseSpeedX, t * _NoiseSpeedY);
                float2 noiseUV2 = i.uv * (_NoiseScale * 1.731)
                                + float2(-t * _NoiseSpeedY, t * _NoiseSpeedX);

                float noiseA = tex2D(_NoiseTex, noiseUV1).r;
                float noiseB = tex2D(_NoiseTex, noiseUV2).g;
                float2 noiseVector = float2(noiseA, noiseB) * 2.0 - 1.0;

                float2 uv = i.uv + noiseVector * _DistortStrength;
                uv.x += sin((i.uv.y + noiseA * 0.15) * _WaveFrequency
                          + t * _WaveSpeed) * _WaveStrength;

                fixed4 c = SampleMain(uv);
                float a0 = c.a;
                float b0 = Brightness(c);

                float2 ep = _MainTex_TexelSize.xy * _EdgeWidth;

                fixed4 e0 = SampleMain(uv + float2( ep.x, 0));
                fixed4 e1 = SampleMain(uv + float2(-ep.x, 0));
                fixed4 e2 = SampleMain(uv + float2(0,  ep.y));
                fixed4 e3 = SampleMain(uv + float2(0, -ep.y));
                #ifdef _LIGHTWEIGHT
                fixed4 e4 = e0, e5 = e1, e6 = e2, e7 = e3;
                #else
                fixed4 e4 = SampleMain(uv + float2( ep.x * DIAG,  ep.y * DIAG));
                fixed4 e5 = SampleMain(uv + float2(-ep.x * DIAG,  ep.y * DIAG));
                fixed4 e6 = SampleMain(uv + float2( ep.x * DIAG, -ep.y * DIAG));
                fixed4 e7 = SampleMain(uv + float2(-ep.x * DIAG, -ep.y * DIAG));
                #endif

                float minAlpha = min(min(min(e0.a, e1.a), min(e2.a, e3.a)),
                                     min(min(e4.a, e5.a), min(e6.a, e7.a)));
                float maxAlpha = max(max(max(e0.a, e1.a), max(e2.a, e3.a)),
                                     max(max(e4.a, e5.a), max(e6.a, e7.a)));

                float innerAlphaEdge = saturate((a0 - minAlpha) * _EdgeSharpness);
                float outerAlphaEdge = saturate((maxAlpha - a0) * _EdgeSharpness);
                float alphaContour = max(innerAlphaEdge, outerAlphaEdge);

                float detailDifference = 0;
                detailDifference = max(detailDifference, ColorDifference(c, e0));
                detailDifference = max(detailDifference, ColorDifference(c, e1));
                detailDifference = max(detailDifference, ColorDifference(c, e2));
                detailDifference = max(detailDifference, ColorDifference(c, e3));
                detailDifference = max(detailDifference, ColorDifference(c, e4));
                detailDifference = max(detailDifference, ColorDifference(c, e5));
                detailDifference = max(detailDifference, ColorDifference(c, e6));
                detailDifference = max(detailDifference, ColorDifference(c, e7));

                float selfDetail = smoothstep(_DetailThreshold,
                                              _DetailThreshold + _DetailSoftness,
                                              detailDifference);

                // The source's own bright strokes can directly become emissive.
                float brightSource = smoothstep(_BrightLineThreshold,
                                                _BrightLineThreshold + _BrightLineSoftness,
                                                b0);

                float contour = saturate(alphaContour * _AlphaContourAmount
                                       + selfDetail * _DetailContourAmount
                                       + brightSource * _BrightLineAmount);

                // Wider neighborhood: spreads glow around both the external
                // silhouette and internal color/luminance boundaries.
                float2 gp = _MainTex_TexelSize.xy * _GlowWidth;

                fixed4 g0 = SampleMain(uv + float2( gp.x, 0));
                fixed4 g1 = SampleMain(uv + float2(-gp.x, 0));
                fixed4 g2 = SampleMain(uv + float2(0,  gp.y));
                fixed4 g3 = SampleMain(uv + float2(0, -gp.y));
                #ifdef _LIGHTWEIGHT
                fixed4 g4 = g0, g5 = g1, g6 = g2, g7 = g3;
                #else
                fixed4 g4 = SampleMain(uv + float2( gp.x * DIAG,  gp.y * DIAG));
                fixed4 g5 = SampleMain(uv + float2(-gp.x * DIAG,  gp.y * DIAG));
                fixed4 g6 = SampleMain(uv + float2( gp.x * DIAG, -gp.y * DIAG));
                fixed4 g7 = SampleMain(uv + float2(-gp.x * DIAG, -gp.y * DIAG));
                #endif

                float maxGlowAlpha = max(max(max(g0.a, g1.a), max(g2.a, g3.a)),
                                         max(max(g4.a, g5.a), max(g6.a, g7.a)));
                float alphaGlow = saturate(maxGlowAlpha - a0);

                float maxWideBrightness = max(max(max(Brightness(g0), Brightness(g1)),
                                                  max(Brightness(g2), Brightness(g3))),
                                              max(max(Brightness(g4), Brightness(g5)),
                                                  max(Brightness(g6), Brightness(g7))));

                float brightDetailGlow = saturate(maxWideBrightness - b0 * 0.45);

                float wideDifference = 0;
                wideDifference = max(wideDifference, ColorDifference(c, g0));
                wideDifference = max(wideDifference, ColorDifference(c, g1));
                wideDifference = max(wideDifference, ColorDifference(c, g2));
                wideDifference = max(wideDifference, ColorDifference(c, g3));
                wideDifference = max(wideDifference, ColorDifference(c, g4));
                wideDifference = max(wideDifference, ColorDifference(c, g5));
                wideDifference = max(wideDifference, ColorDifference(c, g6));
                wideDifference = max(wideDifference, ColorDifference(c, g7));

                float wideDetail = smoothstep(_DetailThreshold,
                                              _DetailThreshold + _DetailSoftness * 1.75,
                                              wideDifference);

                float outerGlow = saturate(alphaGlow * _AlphaContourAmount
                                         + max(brightDetailGlow, wideDetail)
                                           * _DetailGlowAmount);

                float pulse = 1.0 + sin(t * _PulseSpeed) * _PulseAmount;
                float edgeFlicker = lerp(1.0,
                                         saturate(0.35 + noiseA * 1.15),
                                         _EdgeNoiseAmount);
                float glowFlicker = lerp(1.0,
                                         saturate(0.45 + noiseB * 1.05),
                                         _EdgeNoiseAmount);

                contour *= edgeFlicker * pulse;
                outerGlow *= glowFlicker * pulse;

                if (_DebugView > 0.5 && _DebugView < 1.5)
                    return fixed4(alphaContour.xxx, 1);
                if (_DebugView > 1.5 && _DebugView < 2.5)
                    return fixed4(selfDetail.xxx, 1);
                if (_DebugView > 2.5 && _DebugView < 3.5)
                    return fixed4(brightSource.xxx, 1);
                if (_DebugView > 3.5)
                    return fixed4(contour.xxx, 1);

                float baseAlpha = saturate((a0 - _AlphaThreshold)
                                        / max(0.0001, 1.0 - _AlphaThreshold));

                float3 centerRGB = lerp(_CenterColor.rgb,
                                        c.rgb,
                                        _CenterSourceMix);

                float3 rgb = centerRGB * baseAlpha;
                rgb += _EdgeColor.rgb * contour * _EdgeIntensity;
                rgb += _EdgeColor.rgb * outerGlow * _GlowIntensity;

                float alpha = max(baseAlpha * _CenterOpacity,
                                  max(contour * _EdgeColor.a,
                                      outerGlow * _GlowOpacity));

                rgb *= i.color.rgb;
                alpha *= i.color.a;

                #ifdef UNITY_UI_CLIP_RECT
                alpha *= UnityGet2DClipping(i.worldPosition.xy, _ClipRect);
                #endif

                #ifdef UNITY_UI_ALPHACLIP
                clip(alpha - 0.001);
                #endif

                return fixed4(rgb, saturate(alpha));
            }
            ENDCG
        }
    }

    FallBack "UI/Default"
}
