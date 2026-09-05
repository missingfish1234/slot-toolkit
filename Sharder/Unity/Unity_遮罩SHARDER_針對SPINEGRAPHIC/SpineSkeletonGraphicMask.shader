Shader "Custom/Spine/SkeletonGraphic Alpha Mask"
{
    Properties
    {
        [HideInInspector] _UseMaskMatrix ("Use Mask Matrix", Float) = 0
        [PerRendererData] _MainTex ("Spine Texture", 2D) = "white" {}

        _MaskTex ("Mask Texture", 2D) = "white" {}
        _MaskRect ("Mask Rect In Local Space", Vector) = (0, 0, 100, 100)
        _MaskSoftness ("Mask Softness", Range(0, 1)) = 0
        _MaskChannel ("Mask Channel 0=A 1=R 2=G 3=B", Float) = 0
        _InvertMask ("Invert Mask", Float) = 0

        [Toggle] _UseRectClamp ("Use Rect Clamp", Float) = 1

        _Color ("Tint", Color) = (1,1,1,1)

        [HideInInspector] _StencilComp ("Stencil Comparison", Float) = 8
        [HideInInspector] _Stencil ("Stencil ID", Float) = 0
        [HideInInspector] _StencilOp ("Stencil Operation", Float) = 0
        [HideInInspector] _StencilWriteMask ("Stencil Write Mask", Float) = 255
        [HideInInspector] _StencilReadMask ("Stencil Read Mask", Float) = 255
        [HideInInspector] _ColorMask ("Color Mask", Float) = 15

        [HideInInspector] _UseUIAlphaClip ("Use Alpha Clip", Float) = 0
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
        ColorMask [_ColorMask]

        // Spine SkeletonGraphic 常用 PMA 混合
        Blend One OneMinusSrcAlpha

        Pass
        {
            Name "Default"

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 2.0

            #include "UnityCG.cginc"
            #include "UnityUI.cginc"

            #pragma multi_compile_local _ UNITY_UI_CLIP_RECT
            #pragma multi_compile_local _ UNITY_UI_ALPHACLIP

            sampler2D _MainTex;
            sampler2D _MaskTex;

            fixed4 _Color;
            float4 _ClipRect;

            float4 _MaskRect;
            float4x4 _MaskTransform;
            float _UseMaskMatrix;
            float _MaskSoftness;
            float _MaskChannel;
            float _InvertMask;
            float _UseRectClamp;
            float _UseUIAlphaClip;

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
                float2 localPosition : TEXCOORD1;
                float4 worldPosition : TEXCOORD2;
            };

            v2f vert(appdata_t v)
            {
                v2f o;

                o.worldPosition = v.vertex;
                o.localPosition = v.vertex.xy;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.texcoord;
                o.color = v.color * _Color;

                return o;
            }

            float GetMaskChannel(fixed4 maskColor)
            {
                if (_MaskChannel < 0.5)
                    return maskColor.a;
                else if (_MaskChannel < 1.5)
                    return maskColor.r;
                else if (_MaskChannel < 2.5)
                    return maskColor.g;
                else
                    return maskColor.b;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                fixed4 color = tex2D(_MainTex, i.uv) * i.color;

                float2 rectMin = _MaskRect.xy;
                float2 rectSize = max(_MaskRect.zw, float2(0.0001, 0.0001));

                float2 maskPosition = _UseMaskMatrix > 0.5 ? mul(_MaskTransform, float4(i.localPosition, 0, 1)).xy : i.localPosition;
                float2 maskUV = (maskPosition - rectMin) / rectSize;

                float inside =
                    step(0.0, maskUV.x) *
                    step(0.0, maskUV.y) *
                    step(maskUV.x, 1.0) *
                    step(maskUV.y, 1.0);

                fixed4 maskColor = tex2D(_MaskTex, maskUV);
                float maskAlpha = GetMaskChannel(maskColor);

                if (_UseRectClamp > 0.5)
                    maskAlpha *= inside;

                if (_MaskSoftness > 0.0001)
                {
                    float2 edgeDistance = min(maskUV, 1.0 - maskUV);
                    float edge = min(edgeDistance.x, edgeDistance.y);
                    float soft = smoothstep(0.0, _MaskSoftness, edge);
                    maskAlpha *= soft;
                }

                if (_InvertMask > 0.5)
                    maskAlpha = 1.0 - maskAlpha;

                color.a *= maskAlpha;
                color.rgb *= maskAlpha;

                #ifdef UNITY_UI_CLIP_RECT
                color.a *= UnityGet2DClipping(i.worldPosition.xy, _ClipRect);
                #endif

                #ifdef UNITY_UI_ALPHACLIP
                clip(color.a - 0.001);
                #endif

                return color;
            }
            ENDCG
        }
    }

    FallBack "UI/Default"
}
