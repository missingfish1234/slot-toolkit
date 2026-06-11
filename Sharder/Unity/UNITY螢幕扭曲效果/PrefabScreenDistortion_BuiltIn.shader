Shader "Custom/Prefab/Screen Distortion BuiltIn"
{
    Properties
    {
        _Strength ("扭曲強度", Range(-1, 1)) = 0.25
        _Radius ("影響半徑", Range(0.01, 1)) = 0.25
        _Feather ("邊緣柔化", Range(0.001, 0.5)) = 0.08

        [KeywordEnum(Fisheye, Ring, Vortex)] _Mode ("模式", Float) = 0

        _RingRadius ("環形半徑", Range(0, 1)) = 0.45
        _RingWidth ("環形寬度", Range(0.01, 0.5)) = 0.12
        _VortexStrength ("旋轉扭曲", Range(-3, 3)) = 0.8

        _Opacity ("透明度", Range(0, 1)) = 1
        _Chromatic ("色散強度", Range(0, 0.02)) = 0.002
        _Center ("螢幕中心 XY", Vector) = (0.5, 0.5, 0, 0)
    }

    SubShader
    {
        Tags
        {
            "Queue"="Transparent+10"
            "RenderType"="Transparent"
            "IgnoreProjector"="True"
        }

        GrabPass
        {
            "_ScreenDistortionGrabTex"
        }

        Pass
        {
            Cull Off
            ZWrite Off
            ZTest LEqual
            Blend SrcAlpha OneMinusSrcAlpha

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma shader_feature_local _MODE_FISHEYE _MODE_RING _MODE_VORTEX

            #include "UnityCG.cginc"

            sampler2D _ScreenDistortionGrabTex;
            float4 _ScreenDistortionGrabTex_TexelSize;

            float _Strength;
            float _Radius;
            float _Feather;
            float _RingRadius;
            float _RingWidth;
            float _VortexStrength;
            float _Opacity;
            float _Chromatic;
            float4 _Center;

            struct appdata
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float4 vertex : SV_POSITION;
                float4 grabPos : TEXCOORD0;
            };

            v2f vert(appdata v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.grabPos = ComputeGrabScreenPos(o.vertex);
                return o;
            }

            float2 Rotate2D(float2 p, float a)
            {
                float s = sin(a);
                float c = cos(a);

                return float2(
                    p.x * c - p.y * s,
                    p.x * s + p.y * c
                );
            }

            fixed4 frag(v2f i) : SV_Target
            {
                float2 screenUV = i.grabPos.xy / i.grabPos.w;

                float2 center = _Center.xy;
                float2 dir = screenUV - center;

                float aspect = _ScreenParams.x / _ScreenParams.y;

                float2 p = dir;
                p.x *= aspect;

                float r = length(p);
                float radius = max(_Radius, 0.0001);

                float mask = 1.0 - smoothstep(radius - _Feather, radius, r);
                float local = saturate(r / radius);

                float2 warpedP = p;

                #if defined(_MODE_RING)

                    float ring = 1.0 - smoothstep(
                        _RingWidth,
                        _RingWidth * 2.0,
                        abs(local - _RingRadius)
                    );

                    float push = _Strength * ring * mask;
                    warpedP += normalize(p + 0.00001) * push * 0.18;

                #elif defined(_MODE_VORTEX)

                    float vortex = (1.0 - local) * mask * _VortexStrength;
                    warpedP = Rotate2D(p, vortex);
                    warpedP *= 1.0 - _Strength * mask * 0.25;

                #else

                    float bulge = _Strength * mask * pow(1.0 - local, 2.0);
                    warpedP *= 1.0 - bulge;

                #endif

                float2 warpedDir = warpedP;
                warpedDir.x /= aspect;

                float2 sampleUV = center + warpedDir;

                float2 chromaDir = normalize(dir + 0.00001) * _Chromatic * mask;

                fixed rCol = tex2D(_ScreenDistortionGrabTex, sampleUV + chromaDir).r;
                fixed gCol = tex2D(_ScreenDistortionGrabTex, sampleUV).g;
                fixed bCol = tex2D(_ScreenDistortionGrabTex, sampleUV - chromaDir).b;

                return fixed4(rCol, gCol, bCol, mask * _Opacity);
            }
            ENDCG
        }
    }
}