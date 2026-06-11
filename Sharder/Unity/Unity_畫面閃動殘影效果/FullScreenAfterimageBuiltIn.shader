Shader "Hidden/FullScreenAfterimageOctoBuiltIn"
{
    Properties
    {
        _MainTex ("Current Frame", 2D) = "white" {}
        _HistoryTex ("History Frame", 2D) = "black" {}

        _BlendStrength ("Blend Strength", Range(0,1)) = 0.5
        _HistoryFade ("History Fade", Range(0,1)) = 0.92

        _Expand1 ("Expand 1", Range(1.0, 1.3)) = 1.01
        _Expand2 ("Expand 2", Range(1.0, 1.4)) = 1.03
        _Expand3 ("Expand 3", Range(1.0, 1.5)) = 1.06

        _Layer1Weight ("Layer1 Weight", Range(0,2)) = 0.8
        _Layer2Weight ("Layer2 Weight", Range(0,2)) = 0.55
        _Layer3Weight ("Layer3 Weight", Range(0,2)) = 0.35

        _RGBSplit ("RGB Split", Range(0,0.03)) = 0.004
        _RadialPush ("Radial Push", Range(0,0.08)) = 0.015

        _Tint1 ("Tint 1", Color) = (0.7, 1.0, 1.2, 1)
        _Tint2 ("Tint 2", Color) = (1.2, 0.6, 1.1, 1)
        _Tint3 ("Tint 3", Color) = (1.0, 1.0, 0.7, 1)

        _BrightBoost ("Bright Boost", Range(0,4)) = 1.2
        _WhiteFlash ("White Flash", Range(0,2)) = 0.15
        _Contrast ("Contrast", Range(0.5, 2.0)) = 1.15
    }

    SubShader
    {
        Cull Off
        ZWrite Off
        ZTest Always

        Pass
        {
            CGPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            sampler2D _HistoryTex;

            float _BlendStrength;
            float _HistoryFade;

            float _Expand1;
            float _Expand2;
            float _Expand3;

            float _Layer1Weight;
            float _Layer2Weight;
            float _Layer3Weight;

            float _RGBSplit;
            float _RadialPush;

            float4 _Tint1;
            float4 _Tint2;
            float4 _Tint3;

            float _BrightBoost;
            float _WhiteFlash;
            float _Contrast;

            float3 ApplyContrast(float3 c, float contrast)
            {
                return (c - 0.5) * contrast + 0.5;
            }

            float3 SampleRGBSplit(sampler2D tex, float2 uv, float2 dir, float split)
            {
                float2 o = dir * split;
                float r = tex2D(tex, uv + o).r;
                float g = tex2D(tex, uv).g;
                float b = tex2D(tex, uv - o).b;
                return float3(r, g, b);
            }

            float3 SampleHistoryLayer(float2 uv, float expand, float2 dir, float split, float4 tint)
            {
                float2 center = float2(0.5, 0.5);

                float2 pushedUV = uv + dir * _RadialPush;
                float2 historyUV = (pushedUV - center) / expand + center;

                float3 col = SampleRGBSplit(_HistoryTex, historyUV, dir, split);
                col *= tint.rgb;
                return col;
            }

            fixed4 frag(v2f_img i) : SV_Target
            {
                float2 uv = i.uv;
                float2 center = float2(0.5, 0.5);

                float2 dir = uv - center;
                float lenDir = max(length(dir), 0.0001);
                dir /= lenDir;

                float4 currentCol = tex2D(_MainTex, uv);

                float3 h1 = SampleHistoryLayer(uv, _Expand1, dir, _RGBSplit * 1.0, _Tint1) * _Layer1Weight;
                float3 h2 = SampleHistoryLayer(uv, _Expand2, dir, _RGBSplit * 1.8, _Tint2) * _Layer2Weight;
                float3 h3 = SampleHistoryLayer(uv, _Expand3, dir, _RGBSplit * 2.6, _Tint3) * _Layer3Weight;

                float3 history = (h1 + h2 + h3) * _HistoryFade;

                float luminance = dot(currentCol.rgb, float3(0.299, 0.587, 0.114));
                float brightMask = saturate(pow(luminance, 1.35) * _BrightBoost);

                float3 result = currentCol.rgb + history * _BlendStrength;
                result += history * brightMask * 0.85;

                result = ApplyContrast(result, _Contrast);

                result = lerp(result, float3(1,1,1), saturate(brightMask * _WhiteFlash));

                return float4(result, currentCol.a);
            }
            ENDCG
        }
    }
    Fallback Off
}