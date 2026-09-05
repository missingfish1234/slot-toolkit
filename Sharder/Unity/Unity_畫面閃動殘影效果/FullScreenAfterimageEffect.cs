using UnityEngine;

[ExecuteAlways]
[RequireComponent(typeof(Camera))]
public class FullScreenAfterimageEffect : MonoBehaviour
{
    public enum PreviewPreset
    {
        [InspectorName("自訂")]
        Custom,

        [InspectorName("柔和")]
        Soft,

        [InspectorName("爆發")]
        Burst,

        [InspectorName("章魚強烈")]
        Octo,

        [InspectorName("高速殘影")]
        Speed
    }

    [Header("材質設定")]
    [InspectorName("效果材質")]
    [Tooltip("指定全畫面殘影使用的材質。")]
    public Material effectMaterial;
    [Header("History 品質（預設維持原畫面）")]
    [Range(1, 4)] public int historyDownsample = 1;
    [Tooltip("啟用後 History 使用來源格式；原本的 ARGB32 預設保持不變。")]
    public bool preserveSourceFormat = false;

    [Header("主控制")]
    [InspectorName("播放時啟用效果")]
    [Tooltip("遊戲播放時是否啟用全畫面殘影。")]
    public bool effectEnabled = true;

    [InspectorName("啟用時清除殘影紀錄")]
    [Tooltip("物件啟用時清除前一次殘影，避免殘留。")]
    public bool clearHistoryOnEnable = true;

    [Header("編輯器預覽")]
    [InspectorName("編輯器預覽")]
    [Tooltip("未播放時，也能在 Game 視窗預覽效果。")]
    public bool previewInEditMode = true;

    [InspectorName("編輯器中啟用效果")]
    [Tooltip("在未播放狀態下是否顯示效果。")]
    public bool effectEnabledInEditMode = true;

    [InspectorName("使用假殘影預覽")]
    [Tooltip("編輯器預覽時，用目前畫面模擬殘影，方便先看大致風格。")]
    public bool previewUsesFakeHistory = true;

    [InspectorName("編輯器預覽強度")]
    [Tooltip("編輯器預覽時的假殘影強度。")]
    [Range(0f, 1f)]
    public float editorPreviewStrength = 0.65f;

    [InspectorName("手動清除殘影")]
    [Tooltip("勾一下會清除目前累積的殘影畫面。")]
    public bool forceClearHistory = false;

    [Header("預設風格")]
    [InspectorName("預覽風格")]
    [Tooltip("快速切換 柔和 / 爆發 / 章魚強烈 三種效果風格。")]
    public PreviewPreset previewPreset = PreviewPreset.Custom;

    [InspectorName("立即套用預設")]
    [Tooltip("勾一下會立刻套用上面選的預設。")]
    public bool applyPresetNow = false;

    [Header("殘影混合")]
    [InspectorName("殘影混合強度")]
    [Tooltip("數值越高，殘影越明顯、越厚重。")]
    [Range(0f, 1f)]
    public float blendStrength = 0.52f;

    [InspectorName("殘影保留衰減")]
    [Tooltip("數值越高，殘影停留越久。")]
    [Range(0f, 1f)]
    public float historyFade = 0.93f;

    [Header("殘影擴張層")]
    [InspectorName("第一層放大")]
    [Tooltip("第一層殘影的放大倍率，通常最貼近原畫面。")]
    [Range(1.0f, 1.3f)]
    public float expand1 = 1.01f;

    [InspectorName("第二層放大")]
    [Tooltip("第二層殘影的放大倍率，用來形成外擴感。")]
    [Range(1.0f, 1.4f)]
    public float expand2 = 1.03f;

    [InspectorName("第三層放大")]
    [Tooltip("第三層殘影的放大倍率，通常最外圍、最誇張。")]
    [Range(1.0f, 1.5f)]
    public float expand3 = 1.06f;

    [Header("各層權重")]
    [InspectorName("第一層強度")]
    [Tooltip("第一層殘影的可見程度。")]
    [Range(0f, 2f)]
    public float layer1Weight = 0.85f;

    [InspectorName("第二層強度")]
    [Tooltip("第二層殘影的可見程度。")]
    [Range(0f, 2f)]
    public float layer2Weight = 0.55f;

    [InspectorName("第三層強度")]
    [Tooltip("第三層殘影的可見程度。")]
    [Range(0f, 2f)]
    public float layer3Weight = 0.35f;

    [Header("色散與外推")]
    [InspectorName("RGB 色偏")]
    [Tooltip("數值越高，紅綠藍分離越明顯，會更有彩邊炸開感。")]
    [Range(0f, 0.03f)]
    public float rgbSplit = 0.0045f;

    [InspectorName("中心往外推力")]
    [Tooltip("讓殘影有從中心向外衝出的感覺。")]
    [Range(0f, 0.08f)]
    public float radialPush = 0.015f;

    [Header("殘影色調")]
    [InspectorName("第一層色調")]
    [Tooltip("第一層殘影的顏色。")]
    public Color tint1 = new Color(0.72f, 1.0f, 1.15f, 1f);

    [InspectorName("第二層色調")]
    [Tooltip("第二層殘影的顏色。")]
    public Color tint2 = new Color(1.15f, 0.65f, 1.05f, 1f);

    [InspectorName("第三層色調")]
    [Tooltip("第三層殘影的顏色。")]
    public Color tint3 = new Color(1.0f, 0.95f, 0.72f, 1f);

    [Header("高亮與爆閃")]
    [InspectorName("亮部增強")]
    [Tooltip("讓亮的區域更容易被殘影放大強化。")]
    [Range(0f, 4f)]
    public float brightBoost = 1.25f;

    [InspectorName("白爆強度")]
    [Tooltip("數值越高，亮部越容易接近洗白爆閃。")]
    [Range(0f, 2f)]
    public float whiteFlash = 0.18f;

    [InspectorName("整體對比")]
    [Tooltip("調整效果輸出的對比度。")]
    [Range(0.5f, 2f)]
    public float contrast = 1.15f;

    private RenderTexture _historyA;
    private RenderTexture _historyB;
    private bool _toggle;
    private int _lastWidth;
    private int _lastHeight;
    private RenderTextureFormat _lastFormat;

    private Camera _cam;
    private PreviewPreset _lastAppliedPreset = PreviewPreset.Custom;

    private void OnEnable()
    {
        _cam = GetComponent<Camera>();

        if (clearHistoryOnEnable)
            ClearHistoryManual();
    }

    private void OnDisable()
    {
        ReleaseHistory();
    }

    private void OnValidate()
    {
        if (_cam == null)
            _cam = GetComponent<Camera>();

        if (applyPresetNow)
        {
            applyPresetNow = false;
            ApplyPreset(previewPreset);
        }
        else if (previewPreset != PreviewPreset.Custom && previewPreset != _lastAppliedPreset)
        {
            ApplyPreset(previewPreset);
        }

        if (forceClearHistory)
        {
            forceClearHistory = false;
            ClearHistoryManual();
        }

#if UNITY_EDITOR
        if (!Application.isPlaying && previewInEditMode && _cam != null)
        {
            
            UnityEditor.SceneView.RepaintAll();
        }
#endif
    }

    private void Update()
    {
#if UNITY_EDITOR
        if (!Application.isPlaying && previewInEditMode && _cam != null)
        {
            
        }
#endif
    }

    public void ApplyPreset(PreviewPreset preset)
    {
        switch (preset)
        {
            case PreviewPreset.Soft:
                blendStrength = 0.30f;
                historyFade = 0.90f;

                expand1 = 1.005f;
                expand2 = 1.015f;
                expand3 = 1.03f;

                layer1Weight = 0.55f;
                layer2Weight = 0.30f;
                layer3Weight = 0.15f;

                rgbSplit = 0.0025f;
                radialPush = 0.008f;

                tint1 = Color.white;
                tint2 = new Color(0.92f, 0.98f, 1.05f, 1f);
                tint3 = new Color(1.00f, 0.98f, 0.90f, 1f);

                brightBoost = 0.95f;
                whiteFlash = 0.05f;
                contrast = 1.05f;
                break;

            case PreviewPreset.Burst:
                blendStrength = 0.45f;
                historyFade = 0.92f;

                expand1 = 1.01f;
                expand2 = 1.03f;
                expand3 = 1.055f;

                layer1Weight = 0.75f;
                layer2Weight = 0.50f;
                layer3Weight = 0.30f;

                rgbSplit = 0.004f;
                radialPush = 0.014f;

                tint1 = new Color(0.85f, 1.00f, 1.10f, 1f);
                tint2 = new Color(1.08f, 0.78f, 1.03f, 1f);
                tint3 = new Color(1.00f, 0.96f, 0.82f, 1f);

                brightBoost = 1.20f;
                whiteFlash = 0.16f;
                contrast = 1.12f;
                break;

            case PreviewPreset.Octo:
                blendStrength = 0.60f;
                historyFade = 0.94f;

                expand1 = 1.015f;
                expand2 = 1.045f;
                expand3 = 1.09f;

                layer1Weight = 1.00f;
                layer2Weight = 0.75f;
                layer3Weight = 0.50f;

                rgbSplit = 0.008f;
                radialPush = 0.026f;

                tint1 = new Color(0.70f, 1.00f, 1.20f, 1f);
                tint2 = new Color(1.20f, 0.60f, 1.10f, 1f);
                tint3 = new Color(1.00f, 0.95f, 0.70f, 1f);

                brightBoost = 1.65f;
                whiteFlash = 0.35f;
                contrast = 1.25f;
                break;

            case PreviewPreset.Speed:
                blendStrength = 0.68f;
                historyFade = 0.95f;

                expand1 = 1.010f;
                expand2 = 1.038f;
                expand3 = 1.080f;

                layer1Weight = 1.00f;
                layer2Weight = 0.72f;
                layer3Weight = 0.42f;

                rgbSplit = 0.007f;
                radialPush = 0.030f;

                tint1 = new Color(0.72f, 0.95f, 1.12f, 1f);
                tint2 = new Color(0.92f, 0.72f, 1.08f, 1f);
                tint3 = new Color(0.92f, 0.95f, 0.78f, 1f);

                brightBoost = 1.05f;
                whiteFlash = 0.06f;
                contrast = 1.18f;
                break;

            case PreviewPreset.Custom:
            default:
                break;

        }

        _lastAppliedPreset = preset;
        ClearHistoryManual();

#if UNITY_EDITOR
        if (!Application.isPlaying && _cam != null)
        {
            
            UnityEditor.SceneView.RepaintAll();
        }
#endif
    }

    private void ReleaseHistory()
    {
        if (_historyA != null)
        {
            _historyA.Release();
            DestroyImmediate(_historyA);
            _historyA = null;
        }

        if (_historyB != null)
        {
            _historyB.Release();
            DestroyImmediate(_historyB);
            _historyB = null;
        }
    }

    public void ClearHistoryManual()
    {
        ReleaseHistory();
    }

    private void EnsureHistoryTextures(int width, int height, RenderTextureFormat format)
    {
        if (_historyA != null && _historyB != null && width == _lastWidth && height == _lastHeight && format == _lastFormat)
            return;

        ReleaseHistory();

        _historyA = new RenderTexture(width, height, 0, format);
        _historyA.name = "AfterimageHistoryA";
        _historyA.hideFlags = HideFlags.HideAndDontSave;
        _historyA.Create();

        _historyB = new RenderTexture(width, height, 0, format);
        _historyB.name = "AfterimageHistoryB";
        _historyB.hideFlags = HideFlags.HideAndDontSave;
        _historyB.Create();

        _lastWidth = width;
        _lastHeight = height;
        _lastFormat = format;

        var active = RenderTexture.active;

        RenderTexture.active = _historyA;
        GL.Clear(false, true, Color.black);

        RenderTexture.active = _historyB;
        GL.Clear(false, true, Color.black);

        RenderTexture.active = active;
    }

    private void PushParams(float previewBlendMultiplier = 1f)
    {
        if (effectMaterial == null) return;

        effectMaterial.SetFloat("_BlendStrength", blendStrength * previewBlendMultiplier);
        effectMaterial.SetFloat("_HistoryFade", historyFade);

        effectMaterial.SetFloat("_Expand1", expand1);
        effectMaterial.SetFloat("_Expand2", expand2);
        effectMaterial.SetFloat("_Expand3", expand3);

        effectMaterial.SetFloat("_Layer1Weight", layer1Weight);
        effectMaterial.SetFloat("_Layer2Weight", layer2Weight);
        effectMaterial.SetFloat("_Layer3Weight", layer3Weight);

        effectMaterial.SetFloat("_RGBSplit", rgbSplit);
        effectMaterial.SetFloat("_RadialPush", radialPush);

        effectMaterial.SetColor("_Tint1", tint1);
        effectMaterial.SetColor("_Tint2", tint2);
        effectMaterial.SetColor("_Tint3", tint3);

        effectMaterial.SetFloat("_BrightBoost", brightBoost);
        effectMaterial.SetFloat("_WhiteFlash", whiteFlash);
        effectMaterial.SetFloat("_Contrast", contrast);
    }

    private bool ShouldRunEffect()
    {
        if (effectMaterial == null)
            return false;

        if (Application.isPlaying)
            return effectEnabled;

        if (!previewInEditMode)
            return false;

        return effectEnabledInEditMode;
    }

    private void OnRenderImage(RenderTexture src, RenderTexture dst)
    {
        if (!ShouldRunEffect())
        {
            Graphics.Blit(src, dst);
            return;
        }

        int divisor = Mathf.Clamp(historyDownsample, 1, 4);
        RenderTextureFormat format = preserveSourceFormat && SystemInfo.SupportsRenderTextureFormat(src.format) ? src.format : RenderTextureFormat.ARGB32;
        EnsureHistoryTextures(Mathf.Max(1, src.width / divisor), Mathf.Max(1, src.height / divisor), format);

        RenderTexture readHistory = _toggle ? _historyA : _historyB;
        RenderTexture writeHistory = _toggle ? _historyB : _historyA;

        bool isEditMode = !Application.isPlaying;

        if (isEditMode && previewUsesFakeHistory)
        {
            Graphics.Blit(src, readHistory);
            PushParams(editorPreviewStrength);
            effectMaterial.SetTexture("_HistoryTex", readHistory);

            Graphics.Blit(src, writeHistory, effectMaterial);
            Graphics.Blit(writeHistory, dst);
        }
        else
        {
            PushParams(1f);
            effectMaterial.SetTexture("_HistoryTex", readHistory);

            Graphics.Blit(src, writeHistory, effectMaterial);
            Graphics.Blit(writeHistory, dst);
            _toggle = !_toggle;
        }
    }
}
