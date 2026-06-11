using UnityEngine;
using UnityEngine.UI;

#if UNITY_EDITOR
using UnityEditor;
#endif

[ExecuteAlways]
[DisallowMultipleComponent]
public class ArkDissolveController : MonoBehaviour
{
    public enum DissolveMode
    {
        Noise = 0,
        Linear = 1,
        Radial = 2,
        Ring = 3,
        Spiral = 4,
        Stripe = 5
    }

    [Header("目標材質")]
    [Tooltip("若不指定，會自動抓 Graphic 或 Renderer 的材質。")]
    public Material targetMaterial;

    [Tooltip("執行時是否複製材質，避免改到共用材質。")]
    public bool instanceMaterialOnPlay = true;

    [Header("溶解核心")]
    [Range(0f, 1f)]
    public float dissolveAmount = 0f;

    public DissolveMode dissolveMode = DissolveMode.Noise;

    public bool invertDissolve = false;

    [Header("雜訊貼圖")]
    [Tooltip("建議使用灰階 Noise，Texture Type 設 Default，sRGB 關閉。")]
    public Texture2D noiseTexture;

    [Header("舊版雜訊控制")]
    [Tooltip("保留給舊材質相容。新版主要建議用 Big Hole Scale / Detail Scale 控制。")]
    [Range(0.1f, 20f)]
    public float noiseScale = 4f;

    [Tooltip("非 Noise 模式時，用來混入雜訊破壞規則感。")]
    [Range(0f, 1f)]
    public float noiseStrength = 0.65f;

    [Tooltip("雜訊流動速度。X/Y 可做微動或流動。")]
    public Vector2 noiseSpeed = Vector2.zero;

    [Header("打散方塊感 / 大洞控制")]
    [Tooltip("控制主要大破洞尺寸。數值越低，洞越大；數值越高，洞越碎。建議 1.2 ~ 4。")]
    [Range(0.1f, 20f)]
    public float bigNoiseScale = 2.5f;

    [Tooltip("控制破洞邊緣與內部細節。數值越高越細碎。建議 16 ~ 35。")]
    [Range(1f, 80f)]
    public float detailNoiseScale = 18f;

    [Tooltip("細節混合強度。越高越能打散方形感，但太高會讓大洞變碎。建議 0.35 ~ 0.65。")]
    [Range(0f, 1f)]
    public float detailNoiseStrength = 0.35f;

    [Tooltip("旋轉混合 UV 來降低貼圖重複格感。建議 0.5 ~ 0.8。")]
    [Range(0f, 1f)]
    public float uvRandomRotate = 0.6f;

    [Header("方向 / 中心")]
    [Range(0f, 360f)]
    public float directionAngle = 0f;

    [Range(0f, 1f)]
    public float originX = 0.5f;

    [Range(0f, 1f)]
    public float originY = 0.5f;

    [Header("環形 / 螺旋 / 條紋")]
    [Range(0.01f, 1f)]
    public float ringWidth = 0.35f;

    [Range(0f, 12f)]
    public float spiralTurns = 4f;

    [Range(1f, 80f)]
    public float stripeCount = 12f;

    [Range(0.001f, 0.5f)]
    public float stripeSoftness = 0.08f;

    [Header("邊緣光")]
    [Range(0f, 0.5f)]
    public float edgeWidth = 0.08f;

    [Range(0.001f, 0.3f)]
    public float edgeSoftness = 0.05f;

    public Color edgeColor = new Color(1f, 0.45f, 0.05f, 1f);

    [Range(0f, 8f)]
    public float edgeIntensity = 2.5f;

    public bool edgeAdditive = true;

    [Header("透明控制")]
    [Range(0f, 1f)]
    public float alphaCutoff = 0.001f;

    [Range(0.1f, 3f)]
    public float alphaPower = 1f;

    [Header("快速測試")]
    public bool previewAutoPlay = false;

    [Min(0.01f)]
    public float previewDuration = 1.5f;

    public bool pingPong = true;

    private Graphic cachedGraphic;
    private Renderer cachedRenderer;
    private Material runtimeMaterial;
    private Material sourceMaterial;
    private float previewTimer;

    private static readonly int ID_DissolveAmount = Shader.PropertyToID("_DissolveAmount");
    private static readonly int ID_DissolveMode = Shader.PropertyToID("_DissolveMode");
    private static readonly int ID_InvertDissolve = Shader.PropertyToID("_InvertDissolve");

    private static readonly int ID_NoiseTex = Shader.PropertyToID("_NoiseTex");
    private static readonly int ID_NoiseScale = Shader.PropertyToID("_NoiseScale");
    private static readonly int ID_NoiseStrength = Shader.PropertyToID("_NoiseStrength");
    private static readonly int ID_NoiseSpeed = Shader.PropertyToID("_NoiseSpeed");

    private static readonly int ID_BigNoiseScale = Shader.PropertyToID("_BigNoiseScale");
    private static readonly int ID_DetailNoiseScale = Shader.PropertyToID("_DetailNoiseScale");
    private static readonly int ID_DetailNoiseStrength = Shader.PropertyToID("_DetailNoiseStrength");
    private static readonly int ID_UVRandomRotate = Shader.PropertyToID("_UVRandomRotate");

    private static readonly int ID_DirectionAngle = Shader.PropertyToID("_DirectionAngle");
    private static readonly int ID_Origin = Shader.PropertyToID("_Origin");

    private static readonly int ID_RingWidth = Shader.PropertyToID("_RingWidth");
    private static readonly int ID_SpiralTurns = Shader.PropertyToID("_SpiralTurns");
    private static readonly int ID_StripeCount = Shader.PropertyToID("_StripeCount");
    private static readonly int ID_StripeSoftness = Shader.PropertyToID("_StripeSoftness");

    private static readonly int ID_EdgeWidth = Shader.PropertyToID("_EdgeWidth");
    private static readonly int ID_EdgeSoftness = Shader.PropertyToID("_EdgeSoftness");
    private static readonly int ID_EdgeColor = Shader.PropertyToID("_EdgeColor");
    private static readonly int ID_EdgeIntensity = Shader.PropertyToID("_EdgeIntensity");
    private static readonly int ID_EdgeAdditive = Shader.PropertyToID("_EdgeAdditive");

    private static readonly int ID_AlphaCutoff = Shader.PropertyToID("_AlphaCutoff");
    private static readonly int ID_AlphaPower = Shader.PropertyToID("_AlphaPower");

    private void Reset()
    {
        CacheComponents();
        ResolveMaterial();
        Apply();
    }

    private void OnEnable()
    {
        CacheComponents();
        ResolveMaterial();
        Apply();
    }

    private void OnDisable()
    {
        // 編輯器或執行時都不強制還原材質，避免干擾使用者手動指定材質。
    }

    private void OnValidate()
    {
        CacheComponents();
        ResolveMaterial();
        Apply();
    }

    private void Update()
    {
        if (!previewAutoPlay)
        {
            return;
        }

        previewTimer += Application.isPlaying ? Time.deltaTime : 0.016f;

        if (pingPong)
        {
            dissolveAmount = Mathf.PingPong(previewTimer / Mathf.Max(0.01f, previewDuration), 1f);
        }
        else
        {
            dissolveAmount = previewTimer / Mathf.Max(0.01f, previewDuration);

            if (dissolveAmount >= 1f)
            {
                dissolveAmount = 1f;
                previewAutoPlay = false;
            }
        }

        Apply();
    }

    private void CacheComponents()
    {
        if (cachedGraphic == null)
        {
            cachedGraphic = GetComponent<Graphic>();
        }

        if (cachedRenderer == null)
        {
            cachedRenderer = GetComponent<Renderer>();
        }
    }

    private void ResolveMaterial()
    {
        if (targetMaterial != null)
        {
            runtimeMaterial = targetMaterial;
            sourceMaterial = targetMaterial;
            return;
        }

        if (cachedGraphic != null)
        {
            Material graphicMaterial = cachedGraphic.material;

            if (graphicMaterial == null)
            {
                runtimeMaterial = null;
                sourceMaterial = null;
                return;
            }

            if (Application.isPlaying && instanceMaterialOnPlay)
            {
                if (runtimeMaterial == null || sourceMaterial != graphicMaterial)
                {
                    runtimeMaterial = new Material(graphicMaterial);
                    runtimeMaterial.name = graphicMaterial.name + " Instance";
                    cachedGraphic.material = runtimeMaterial;
                    sourceMaterial = runtimeMaterial;
                }
            }
            else
            {
                runtimeMaterial = graphicMaterial;
                sourceMaterial = graphicMaterial;
            }

            return;
        }

        if (cachedRenderer != null)
        {
            Material rendererMaterial = Application.isPlaying && instanceMaterialOnPlay
                ? cachedRenderer.material
                : cachedRenderer.sharedMaterial;

            runtimeMaterial = rendererMaterial;
            sourceMaterial = rendererMaterial;
        }
    }

    public void Apply()
    {
        if (runtimeMaterial == null)
        {
            return;
        }

        SetFloatIfExists(ID_DissolveAmount, dissolveAmount);
        SetFloatIfExists(ID_DissolveMode, (float)dissolveMode);
        SetFloatIfExists(ID_InvertDissolve, invertDissolve ? 1f : 0f);

        if (noiseTexture != null && runtimeMaterial.HasProperty(ID_NoiseTex))
        {
            runtimeMaterial.SetTexture(ID_NoiseTex, noiseTexture);
        }

        SetFloatIfExists(ID_NoiseScale, noiseScale);
        SetFloatIfExists(ID_NoiseStrength, noiseStrength);
        SetVectorIfExists(ID_NoiseSpeed, new Vector4(noiseSpeed.x, noiseSpeed.y, 0f, 0f));

        SetFloatIfExists(ID_BigNoiseScale, bigNoiseScale);
        SetFloatIfExists(ID_DetailNoiseScale, detailNoiseScale);
        SetFloatIfExists(ID_DetailNoiseStrength, detailNoiseStrength);
        SetFloatIfExists(ID_UVRandomRotate, uvRandomRotate);

        SetFloatIfExists(ID_DirectionAngle, directionAngle);
        SetVectorIfExists(ID_Origin, new Vector4(originX, originY, 0f, 0f));

        SetFloatIfExists(ID_RingWidth, ringWidth);
        SetFloatIfExists(ID_SpiralTurns, spiralTurns);
        SetFloatIfExists(ID_StripeCount, stripeCount);
        SetFloatIfExists(ID_StripeSoftness, stripeSoftness);

        SetFloatIfExists(ID_EdgeWidth, edgeWidth);
        SetFloatIfExists(ID_EdgeSoftness, edgeSoftness);
        SetColorIfExists(ID_EdgeColor, edgeColor);
        SetFloatIfExists(ID_EdgeIntensity, edgeIntensity);
        SetFloatIfExists(ID_EdgeAdditive, edgeAdditive ? 1f : 0f);

        SetFloatIfExists(ID_AlphaCutoff, alphaCutoff);
        SetFloatIfExists(ID_AlphaPower, alphaPower);

#if UNITY_EDITOR
        if (!Application.isPlaying)
        {
            EditorUtility.SetDirty(runtimeMaterial);
        }
#endif
    }

    private void SetFloatIfExists(int propertyId, float value)
    {
        if (runtimeMaterial != null && runtimeMaterial.HasProperty(propertyId))
        {
            runtimeMaterial.SetFloat(propertyId, value);
        }
    }

    private void SetVectorIfExists(int propertyId, Vector4 value)
    {
        if (runtimeMaterial != null && runtimeMaterial.HasProperty(propertyId))
        {
            runtimeMaterial.SetVector(propertyId, value);
        }
    }

    private void SetColorIfExists(int propertyId, Color value)
    {
        if (runtimeMaterial != null && runtimeMaterial.HasProperty(propertyId))
        {
            runtimeMaterial.SetColor(propertyId, value);
        }
    }

    public void SetDissolve(float value)
    {
        dissolveAmount = Mathf.Clamp01(value);
        Apply();
    }

    public void SetMode(int mode)
    {
        dissolveMode = (DissolveMode)Mathf.Clamp(mode, 0, 5);
        Apply();
    }

    public void SetNoiseMode()
    {
        dissolveMode = DissolveMode.Noise;
        Apply();
    }

    public void SetLinearMode()
    {
        dissolveMode = DissolveMode.Linear;
        Apply();
    }

    public void SetRadialMode()
    {
        dissolveMode = DissolveMode.Radial;
        Apply();
    }

    public void SetRingMode()
    {
        dissolveMode = DissolveMode.Ring;
        Apply();
    }

    public void SetSpiralMode()
    {
        dissolveMode = DissolveMode.Spiral;
        Apply();
    }

    public void SetStripeMode()
    {
        dissolveMode = DissolveMode.Stripe;
        Apply();
    }

    public void ResetDissolve()
    {
        previewAutoPlay = false;
        previewTimer = 0f;
        dissolveAmount = 0f;
        Apply();
    }

    public void CompleteDissolve()
    {
        previewAutoPlay = false;
        previewTimer = previewDuration;
        dissolveAmount = 1f;
        Apply();
    }

    public void PlayDissolveOnce()
    {
        previewTimer = 0f;
        dissolveAmount = 0f;
        pingPong = false;
        previewAutoPlay = true;
        Apply();
    }

    public void PlayDissolvePingPong()
    {
        previewTimer = 0f;
        pingPong = true;
        previewAutoPlay = true;
        Apply();
    }

    public void StopPreview()
    {
        previewAutoPlay = false;
        Apply();
    }

    public void ApplyLargeHolePreset()
    {
        dissolveMode = DissolveMode.Noise;
        noiseScale = 4f;
        noiseStrength = 0.55f;

        bigNoiseScale = 1.6f;
        detailNoiseScale = 18f;
        detailNoiseStrength = 0.42f;
        uvRandomRotate = 0.7f;

        edgeWidth = 0.055f;
        edgeSoftness = 0.045f;
        edgeIntensity = 2.6f;

        Apply();
    }

    public void ApplyFineBreakPreset()
    {
        dissolveMode = DissolveMode.Noise;
        noiseScale = 4f;
        noiseStrength = 0.65f;

        bigNoiseScale = 5f;
        detailNoiseScale = 36f;
        detailNoiseStrength = 0.65f;
        uvRandomRotate = 0.8f;

        edgeWidth = 0.04f;
        edgeSoftness = 0.035f;
        edgeIntensity = 2.2f;

        Apply();
    }

    public void ApplySoftBurnPreset()
    {
        dissolveMode = DissolveMode.Noise;
        noiseScale = 4f;
        noiseStrength = 0.45f;

        bigNoiseScale = 2.4f;
        detailNoiseScale = 16f;
        detailNoiseStrength = 0.28f;
        uvRandomRotate = 0.55f;

        edgeWidth = 0.08f;
        edgeSoftness = 0.075f;
        edgeIntensity = 2f;

        Apply();
    }
}