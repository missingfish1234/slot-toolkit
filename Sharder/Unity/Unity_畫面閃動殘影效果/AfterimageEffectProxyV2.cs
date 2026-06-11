using UnityEngine;
using System.Collections;

public class AfterimageEffectProxyV2 : MonoBehaviour
{
    [Header("Auto Find")]
    public FullScreenAfterimageEffect targetEffect;
    public bool autoFindOnAwake = true;
    public bool useMainCameraOnly = true;

    [Header("Default Preset")]
    [Range(0f, 1f)] public float blendStrength = 0.52f;
    [Range(0f, 1f)] public float historyFade = 0.93f;

    [Header("Expand Layers")]
    [Range(1.0f, 1.3f)] public float expand1 = 1.01f;
    [Range(1.0f, 1.4f)] public float expand2 = 1.035f;
    [Range(1.0f, 1.5f)] public float expand3 = 1.07f;

    [Header("Layer Weights")]
    [Range(0f, 2f)] public float layer1Weight = 0.85f;
    [Range(0f, 2f)] public float layer2Weight = 0.55f;
    [Range(0f, 2f)] public float layer3Weight = 0.35f;

    [Header("Chromatic / Radial")]
    [Range(0f, 0.03f)] public float rgbSplit = 0.005f;
    [Range(0f, 0.08f)] public float radialPush = 0.018f;

    [Header("Tints")]
    public Color tint1 = new Color(0.72f, 1.0f, 1.15f, 1f);
    public Color tint2 = new Color(1.15f, 0.65f, 1.05f, 1f);
    public Color tint3 = new Color(1.0f, 0.95f, 0.72f, 1f);

    [Header("Highlight")]
    [Range(0f, 4f)] public float brightBoost = 1.35f;
    [Range(0f, 2f)] public float whiteFlash = 0.22f;
    [Range(0.5f, 2f)] public float contrast = 1.18f;

    [Header("Options")]
    public bool clearHistoryBeforePlay = true;
    public bool clearHistoryOnStop = true;

    private Coroutine _playRoutine;

    private void Awake()
    {
        if (autoFindOnAwake)
            ResolveTarget();
    }

    public void ResolveTarget()
    {
        if (targetEffect != null) return;

        if (useMainCameraOnly && Camera.main != null)
        {
            targetEffect = Camera.main.GetComponent<FullScreenAfterimageEffect>();
            if (targetEffect != null) return;
        }

        targetEffect = FindFirstObjectByType<FullScreenAfterimageEffect>();
    }

    public void Play()
    {
        ResolveTarget();
        if (targetEffect == null) return;

        if (clearHistoryBeforePlay)
            targetEffect.ClearHistoryManual();

        ApplyValues();
        targetEffect.effectEnabled = true;
    }

    public void Stop()
    {
        ResolveTarget();
        if (targetEffect == null) return;

        targetEffect.effectEnabled = false;

        if (clearHistoryOnStop)
            targetEffect.ClearHistoryManual();
    }

    public void PlayForSeconds(float seconds)
    {
        ResolveTarget();
        if (targetEffect == null || !gameObject.activeInHierarchy) return;

        if (_playRoutine != null)
            StopCoroutine(_playRoutine);

        _playRoutine = StartCoroutine(CoPlayForSeconds(seconds));
    }

    private IEnumerator CoPlayForSeconds(float seconds)
    {
        Play();
        yield return new WaitForSeconds(seconds);
        Stop();
        _playRoutine = null;
    }

    private void ApplyValues()
    {
        targetEffect.blendStrength = blendStrength;
        targetEffect.historyFade = historyFade;

        targetEffect.expand1 = expand1;
        targetEffect.expand2 = expand2;
        targetEffect.expand3 = expand3;

        targetEffect.layer1Weight = layer1Weight;
        targetEffect.layer2Weight = layer2Weight;
        targetEffect.layer3Weight = layer3Weight;

        targetEffect.rgbSplit = rgbSplit;
        targetEffect.radialPush = radialPush;

        targetEffect.tint1 = tint1;
        targetEffect.tint2 = tint2;
        targetEffect.tint3 = tint3;

        targetEffect.brightBoost = brightBoost;
        targetEffect.whiteFlash = whiteFlash;
        targetEffect.contrast = contrast;
    }

    public void Anim_PlayAfterimage()
    {
        Play();
    }

    public void Anim_StopAfterimage()
    {
        Stop();
    }

    public void Anim_PlayAfterimage_05s()
    {
        PlayForSeconds(0.5f);
    }

    public void Anim_PlayAfterimage_10s()
    {
        PlayForSeconds(1.0f);
    }

    public void Anim_PlayAfterimageStrong()
    {
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

        Play();
    }

    public void Anim_PlayAfterimageSoft()
    {
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

        Play();
    }
}