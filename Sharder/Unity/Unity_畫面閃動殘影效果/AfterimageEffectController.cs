using UnityEngine;
using System.Collections;

public class AfterimageEffectController : MonoBehaviour
{
    public static AfterimageEffectController Instance { get; private set; }

    public enum PresetType
    {
        [InspectorName("章魚強烈")]
        Octo,

        [InspectorName("高速殘影")]
        Speed
    }

    [Header("目標")]
    [InspectorName("目標效果")]
    [Tooltip("指定要控制的全畫面殘影效果元件。")]
    public FullScreenAfterimageEffect targetEffect;

    [Header("目前預設")]
    [InspectorName("預設效果")]
    [Tooltip("選擇這次演出要使用的完整預設。")]
    public PresetType currentPreset = PresetType.Octo;

    [InspectorName("立即套用預設到面板")]
    [Tooltip("勾一下會把目前預設的基礎值與時間套到這個控制器。")]
    public bool applyPresetNow = false;

    [Header("播放設定")]
    [InspectorName("播放前清除殘影")]
    [Tooltip("開始播放前先清除舊的殘影紀錄。")]
    public bool clearHistoryBeforePlay = true;

    [Header("基底參數")]
    [InspectorName("殘影混合強度")]
    [Range(0f, 1f)] public float baseBlendStrength = 0.60f;

    [InspectorName("殘影保留衰減")]
    [Range(0f, 1f)] public float baseHistoryFade = 0.94f;

    [InspectorName("第一層放大")]
    [Range(1.0f, 1.3f)] public float baseExpand1 = 1.015f;

    [InspectorName("第二層放大")]
    [Range(1.0f, 1.4f)] public float baseExpand2 = 1.045f;

    [InspectorName("第三層放大")]
    [Range(1.0f, 1.5f)] public float baseExpand3 = 1.09f;

    [InspectorName("第一層強度")]
    [Range(0f, 2f)] public float baseLayer1Weight = 1.00f;

    [InspectorName("第二層強度")]
    [Range(0f, 2f)] public float baseLayer2Weight = 0.75f;

    [InspectorName("第三層強度")]
    [Range(0f, 2f)] public float baseLayer3Weight = 0.50f;

    [InspectorName("RGB 色偏")]
    [Range(0f, 0.03f)] public float baseRgbSplit = 0.008f;

    [InspectorName("中心往外推力")]
    [Range(0f, 0.08f)] public float baseRadialPush = 0.026f;

    [InspectorName("第一層色調")]
    public Color baseTint1 = new Color(0.70f, 1.00f, 1.20f, 1f);

    [InspectorName("第二層色調")]
    public Color baseTint2 = new Color(1.20f, 0.60f, 1.10f, 1f);

    [InspectorName("第三層色調")]
    public Color baseTint3 = new Color(1.00f, 0.95f, 0.70f, 1f);

    [InspectorName("亮部增強")]
    [Range(0f, 4f)] public float baseBrightBoost = 1.65f;

    [InspectorName("白爆強度")]
    [Range(0f, 2f)] public float baseWhiteFlash = 0.35f;

    [InspectorName("整體對比")]
    [Range(0.5f, 2f)] public float baseContrast = 1.25f;

    [Header("段落時間")]
    [InspectorName("起爆時間")]
    [Range(0.01f, 1f)] public float preBurstTime = 0.10f;

    [InspectorName("爆發時間")]
    [Range(0.01f, 1f)] public float burstTime = 0.12f;

    [InspectorName("收尾時間")]
    [Range(0.01f, 2f)] public float releaseTime = 0.28f;

    [Header("起爆偏移")]
    [InspectorName("起爆-殘影混合偏移")] public float preBlendAdd = 0.04f;
    [InspectorName("起爆-衰減偏移")] public float preFadeAdd = 0.00f;
    [InspectorName("起爆-第一層放大偏移")] public float preExpand1Add = 0.002f;
    [InspectorName("起爆-第二層放大偏移")] public float preExpand2Add = 0.004f;
    [InspectorName("起爆-第三層放大偏移")] public float preExpand3Add = 0.006f;
    [InspectorName("起爆-第一層強度偏移")] public float preLayer1Add = 0.05f;
    [InspectorName("起爆-第二層強度偏移")] public float preLayer2Add = 0.03f;
    [InspectorName("起爆-第三層強度偏移")] public float preLayer3Add = 0.02f;
    [InspectorName("起爆-RGB色偏偏移")] public float preRgbSplitAdd = 0.001f;
    [InspectorName("起爆-外推偏移")] public float preRadialPushAdd = 0.004f;
    [InspectorName("起爆-亮部增強偏移")] public float preBrightBoostAdd = 0.08f;
    [InspectorName("起爆-白爆偏移")] public float preWhiteFlashAdd = 0.02f;
    [InspectorName("起爆-對比偏移")] public float preContrastAdd = 0.02f;

    [Header("爆發偏移")]
    [InspectorName("爆發-殘影混合偏移")] public float burstBlendAdd = 0.14f;
    [InspectorName("爆發-衰減偏移")] public float burstFadeAdd = 0.01f;
    [InspectorName("爆發-第一層放大偏移")] public float burstExpand1Add = 0.006f;
    [InspectorName("爆發-第二層放大偏移")] public float burstExpand2Add = 0.020f;
    [InspectorName("爆發-第三層放大偏移")] public float burstExpand3Add = 0.040f;
    [InspectorName("爆發-第一層強度偏移")] public float burstLayer1Add = 0.15f;
    [InspectorName("爆發-第二層強度偏移")] public float burstLayer2Add = 0.12f;
    [InspectorName("爆發-第三層強度偏移")] public float burstLayer3Add = 0.10f;
    [InspectorName("爆發-RGB色偏偏移")] public float burstRgbSplitAdd = 0.003f;
    [InspectorName("爆發-外推偏移")] public float burstRadialPushAdd = 0.012f;
    [InspectorName("爆發-亮部增強偏移")] public float burstBrightBoostAdd = 0.20f;
    [InspectorName("爆發-白爆偏移")] public float burstWhiteFlashAdd = 0.05f;
    [InspectorName("爆發-對比偏移")] public float burstContrastAdd = 0.06f;

    [Header("收尾偏移")]
    [InspectorName("收尾-殘影混合偏移")] public float releaseBlendAdd = -0.06f;
    [InspectorName("收尾-衰減偏移")] public float releaseFadeAdd = -0.02f;
    [InspectorName("收尾-第一層放大偏移")] public float releaseExpand1Add = 0.002f;
    [InspectorName("收尾-第二層放大偏移")] public float releaseExpand2Add = 0.008f;
    [InspectorName("收尾-第三層放大偏移")] public float releaseExpand3Add = 0.015f;
    [InspectorName("收尾-第一層強度偏移")] public float releaseLayer1Add = -0.05f;
    [InspectorName("收尾-第二層強度偏移")] public float releaseLayer2Add = -0.03f;
    [InspectorName("收尾-第三層強度偏移")] public float releaseLayer3Add = -0.02f;
    [InspectorName("收尾-RGB色偏偏移")] public float releaseRgbSplitAdd = -0.001f;
    [InspectorName("收尾-外推偏移")] public float releaseRadialPushAdd = -0.004f;
    [InspectorName("收尾-亮部增強偏移")] public float releaseBrightBoostAdd = -0.08f;
    [InspectorName("收尾-白爆偏移")] public float releaseWhiteFlashAdd = -0.02f;
    [InspectorName("收尾-對比偏移")] public float releaseContrastAdd = -0.02f;

    private Coroutine _sequenceRoutine;

    private void Awake()
    {
        Instance = this;
    }

    private void OnValidate()
    {
        if (applyPresetNow)
        {
            applyPresetNow = false;
            ApplyCurrentPresetToController();
        }
    }

    public void ApplyCurrentPresetToController()
    {
        switch (currentPreset)
        {
            case PresetType.Octo:
                ApplyOctoPreset();
                break;

            case PresetType.Speed:
                ApplySpeedPreset();
                break;
        }
    }

    private void ApplyOctoPreset()
    {
        // 基底
        baseBlendStrength = 0.60f;
        baseHistoryFade = 0.94f;
        baseExpand1 = 1.015f;
        baseExpand2 = 1.045f;
        baseExpand3 = 1.09f;
        baseLayer1Weight = 1.00f;
        baseLayer2Weight = 0.75f;
        baseLayer3Weight = 0.50f;
        baseRgbSplit = 0.008f;
        baseRadialPush = 0.026f;
        baseTint1 = new Color(0.70f, 1.00f, 1.20f, 1f);
        baseTint2 = new Color(1.20f, 0.60f, 1.10f, 1f);
        baseTint3 = new Color(1.00f, 0.95f, 0.70f, 1f);
        baseBrightBoost = 1.65f;
        baseWhiteFlash = 0.35f;
        baseContrast = 1.25f;

        // 時間
        preBurstTime = 0.10f;
        burstTime = 0.12f;
        releaseTime = 0.28f;

        // 偏移
        preBlendAdd = 0.04f;
        preFadeAdd = 0.00f;
        preExpand1Add = 0.002f;
        preExpand2Add = 0.004f;
        preExpand3Add = 0.006f;
        preLayer1Add = 0.05f;
        preLayer2Add = 0.03f;
        preLayer3Add = 0.02f;
        preRgbSplitAdd = 0.001f;
        preRadialPushAdd = 0.004f;
        preBrightBoostAdd = 0.08f;
        preWhiteFlashAdd = 0.02f;
        preContrastAdd = 0.02f;

        burstBlendAdd = 0.14f;
        burstFadeAdd = 0.01f;
        burstExpand1Add = 0.006f;
        burstExpand2Add = 0.020f;
        burstExpand3Add = 0.040f;
        burstLayer1Add = 0.15f;
        burstLayer2Add = 0.12f;
        burstLayer3Add = 0.10f;
        burstRgbSplitAdd = 0.003f;
        burstRadialPushAdd = 0.012f;
        burstBrightBoostAdd = 0.20f;
        burstWhiteFlashAdd = 0.05f;
        burstContrastAdd = 0.06f;

        releaseBlendAdd = -0.06f;
        releaseFadeAdd = -0.02f;
        releaseExpand1Add = 0.002f;
        releaseExpand2Add = 0.008f;
        releaseExpand3Add = 0.015f;
        releaseLayer1Add = -0.05f;
        releaseLayer2Add = -0.03f;
        releaseLayer3Add = -0.02f;
        releaseRgbSplitAdd = -0.001f;
        releaseRadialPushAdd = -0.004f;
        releaseBrightBoostAdd = -0.08f;
        releaseWhiteFlashAdd = -0.02f;
        releaseContrastAdd = -0.02f;
    }

    private void ApplySpeedPreset()
    {
        // 基底
        baseBlendStrength = 0.68f;
        baseHistoryFade = 0.95f;
        baseExpand1 = 1.010f;
        baseExpand2 = 1.038f;
        baseExpand3 = 1.080f;
        baseLayer1Weight = 1.00f;
        baseLayer2Weight = 0.72f;
        baseLayer3Weight = 0.42f;
        baseRgbSplit = 0.007f;
        baseRadialPush = 0.030f;
        baseTint1 = new Color(0.72f, 0.95f, 1.12f, 1f);
        baseTint2 = new Color(0.92f, 0.72f, 1.08f, 1f);
        baseTint3 = new Color(0.92f, 0.95f, 0.78f, 1f);
        baseBrightBoost = 1.05f;
        baseWhiteFlash = 0.06f;
        baseContrast = 1.18f;

        // 時間
        preBurstTime = 0.06f;
        burstTime = 0.10f;
        releaseTime = 0.18f;

        // 偏移
        preBlendAdd = 0.02f;
        preFadeAdd = 0.00f;
        preExpand1Add = 0.001f;
        preExpand2Add = 0.002f;
        preExpand3Add = 0.004f;
        preLayer1Add = 0.03f;
        preLayer2Add = 0.02f;
        preLayer3Add = 0.01f;
        preRgbSplitAdd = 0.001f;
        preRadialPushAdd = 0.004f;
        preBrightBoostAdd = 0.02f;
        preWhiteFlashAdd = 0.00f;
        preContrastAdd = 0.01f;

        burstBlendAdd = 0.08f;
        burstFadeAdd = 0.01f;
        burstExpand1Add = 0.002f;
        burstExpand2Add = 0.010f;
        burstExpand3Add = 0.022f;
        burstLayer1Add = 0.08f;
        burstLayer2Add = 0.06f;
        burstLayer3Add = 0.04f;
        burstRgbSplitAdd = 0.002f;
        burstRadialPushAdd = 0.010f;
        burstBrightBoostAdd = 0.03f;
        burstWhiteFlashAdd = -0.01f;
        burstContrastAdd = 0.03f;

        releaseBlendAdd = -0.05f;
        releaseFadeAdd = -0.02f;
        releaseExpand1Add = 0.001f;
        releaseExpand2Add = 0.004f;
        releaseExpand3Add = 0.010f;
        releaseLayer1Add = -0.03f;
        releaseLayer2Add = -0.02f;
        releaseLayer3Add = -0.01f;
        releaseRgbSplitAdd = -0.001f;
        releaseRadialPushAdd = -0.006f;
        releaseBrightBoostAdd = -0.02f;
        releaseWhiteFlashAdd = -0.01f;
        releaseContrastAdd = -0.01f;
    }

    public void PlayPresetSequence()
    {
        if (!gameObject.activeInHierarchy || targetEffect == null) return;

        if (_sequenceRoutine != null)
            StopCoroutine(_sequenceRoutine);

        _sequenceRoutine = StartCoroutine(CoPlayPresetSequence());
    }

    public void Stop()
    {
        if (targetEffect == null) return;
        targetEffect.effectEnabled = false;
        targetEffect.ClearHistoryManual();
    }

    private IEnumerator CoPlayPresetSequence()
    {
        if (clearHistoryBeforePlay)
            targetEffect.ClearHistoryManual();

        ApplyBaseToTarget();
        targetEffect.effectEnabled = true;

        ApplyPreBurstToTarget();
        yield return new WaitForSeconds(preBurstTime);

        ApplyBurstToTarget();
        yield return new WaitForSeconds(burstTime);

        ApplyReleaseToTarget();
        yield return new WaitForSeconds(releaseTime);

        Stop();
        _sequenceRoutine = null;
    }

    private void ApplyBaseToTarget()
    {
        targetEffect.blendStrength = baseBlendStrength;
        targetEffect.historyFade = baseHistoryFade;
        targetEffect.expand1 = baseExpand1;
        targetEffect.expand2 = baseExpand2;
        targetEffect.expand3 = baseExpand3;
        targetEffect.layer1Weight = baseLayer1Weight;
        targetEffect.layer2Weight = baseLayer2Weight;
        targetEffect.layer3Weight = baseLayer3Weight;
        targetEffect.rgbSplit = baseRgbSplit;
        targetEffect.radialPush = baseRadialPush;
        targetEffect.tint1 = baseTint1;
        targetEffect.tint2 = baseTint2;
        targetEffect.tint3 = baseTint3;
        targetEffect.brightBoost = baseBrightBoost;
        targetEffect.whiteFlash = baseWhiteFlash;
        targetEffect.contrast = baseContrast;
    }

    private void ApplyPreBurstToTarget()
    {
        ApplyOffsetToTarget(
            preBlendAdd, preFadeAdd,
            preExpand1Add, preExpand2Add, preExpand3Add,
            preLayer1Add, preLayer2Add, preLayer3Add,
            preRgbSplitAdd, preRadialPushAdd,
            preBrightBoostAdd, preWhiteFlashAdd, preContrastAdd
        );
    }

    private void ApplyBurstToTarget()
    {
        ApplyOffsetToTarget(
            burstBlendAdd, burstFadeAdd,
            burstExpand1Add, burstExpand2Add, burstExpand3Add,
            burstLayer1Add, burstLayer2Add, burstLayer3Add,
            burstRgbSplitAdd, burstRadialPushAdd,
            burstBrightBoostAdd, burstWhiteFlashAdd, burstContrastAdd
        );
    }

    private void ApplyReleaseToTarget()
    {
        ApplyOffsetToTarget(
            releaseBlendAdd, releaseFadeAdd,
            releaseExpand1Add, releaseExpand2Add, releaseExpand3Add,
            releaseLayer1Add, releaseLayer2Add, releaseLayer3Add,
            releaseRgbSplitAdd, releaseRadialPushAdd,
            releaseBrightBoostAdd, releaseWhiteFlashAdd, releaseContrastAdd
        );
    }

    private void ApplyOffsetToTarget(
        float blendAdd, float fadeAdd,
        float e1Add, float e2Add, float e3Add,
        float l1Add, float l2Add, float l3Add,
        float rgbAdd, float pushAdd,
        float brightAdd, float whiteAdd, float contrastAdd)
    {
        targetEffect.blendStrength = Mathf.Clamp01(baseBlendStrength + blendAdd);
        targetEffect.historyFade = Mathf.Clamp01(baseHistoryFade + fadeAdd);

        targetEffect.expand1 = Mathf.Max(1f, baseExpand1 + e1Add);
        targetEffect.expand2 = Mathf.Max(1f, baseExpand2 + e2Add);
        targetEffect.expand3 = Mathf.Max(1f, baseExpand3 + e3Add);

        targetEffect.layer1Weight = Mathf.Max(0f, baseLayer1Weight + l1Add);
        targetEffect.layer2Weight = Mathf.Max(0f, baseLayer2Weight + l2Add);
        targetEffect.layer3Weight = Mathf.Max(0f, baseLayer3Weight + l3Add);

        targetEffect.rgbSplit = Mathf.Max(0f, baseRgbSplit + rgbAdd);
        targetEffect.radialPush = Mathf.Max(0f, baseRadialPush + pushAdd);

        targetEffect.tint1 = baseTint1;
        targetEffect.tint2 = baseTint2;
        targetEffect.tint3 = baseTint3;

        targetEffect.brightBoost = Mathf.Max(0f, baseBrightBoost + brightAdd);
        targetEffect.whiteFlash = Mathf.Max(0f, baseWhiteFlash + whiteAdd);
        targetEffect.contrast = Mathf.Max(0.01f, baseContrast + contrastAdd);
    }
}