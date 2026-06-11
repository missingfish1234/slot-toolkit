using UnityEditor;
using UnityEngine;

/// <summary>
/// BMFont 彩虹 Shader 的美術友善面板。
/// 放置路徑建議：Assets/Editor/BMFontRainbowArtistShaderGUI.cs
/// Shader 內需包含：CustomEditor "BMFontRainbowArtistShaderGUI"
/// </summary>
public class BMFontRainbowArtistShaderGUI : ShaderGUI
{
    private MaterialEditor _editor;
    private MaterialProperty[] _props;
    private Material _mat;

    private static bool _showBasic = true;
    private static bool _showRainbow = true;
    private static bool _showSweep = true;
    private static bool _showDiamond = false;
    private static bool _showAdvanced = false;
    private static bool _showDebug = false;

    public override void OnGUI(MaterialEditor materialEditor, MaterialProperty[] properties)
    {
        _editor = materialEditor;
        _props = properties;
        _mat = materialEditor.target as Material;

        if (_mat == null)
        {
            base.OnGUI(materialEditor, properties);
            return;
        }

        EditorGUILayout.Space(4);
        EditorGUILayout.LabelField("BMFont 彩虹效果｜美術面板", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox("常用只需要調整：彩虹寬度、速度、強度、掃光寬度、掃光強度、鑽石強度。進階參數已收合，避免誤調。", MessageType.Info);

        DrawPresetBar();
        EditorGUILayout.Space(6);

        DrawBasic();
        DrawRainbow();
        DrawSweep();
        DrawDiamond();
        DrawAdvanced();
        DrawDebug();

        if (GUI.changed)
        {
            foreach (Object target in materialEditor.targets)
            {
                if (target is Material m) SyncKeywords(m);
            }
        }
    }

    private void DrawPresetBar()
    {
        EditorGUILayout.LabelField("快速預設", EditorStyles.boldLabel);
        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button("手機效能")) ApplyPresetMobile();
            if (GUILayout.Button("標準彩虹")) ApplyPresetStandard();
            if (GUILayout.Button("Big Win華麗")) ApplyPresetBigWin();
            if (GUILayout.Button("粒子安全")) ApplyPresetParticle();
        }
    }

    private void DrawBasic()
    {
        _showBasic = EditorGUILayout.Foldout(_showBasic, "基本設定", true);
        if (!_showBasic) return;

        using (new EditorGUI.IndentLevelScope())
        {
            Texture("_MainTex", "BMFont 字型圖集");
            Slider("_UseSrcRGB", "乘上原圖顏色");
            Slider("_Alpha", "整體透明度");
            Toggle("_ParticleMode", "粒子模式 / 忽略 UV1 UV2", "_PARTICLEMODE_ON");
        }
    }

    private void DrawRainbow()
    {
        _showRainbow = EditorGUILayout.Foldout(_showRainbow, "彩虹填色", true);
        if (!_showRainbow) return;

        using (new EditorGUI.IndentLevelScope())
        {
            Toggle("_FillEnable", "啟用彩虹填色", "_FILL_ON");
            if (Float("_FillEnable") < 0.5f) return;

            Slider("_FillFlowMode", "流動模式 0線性 1放射 2螺旋 3色帶");
            Slider("_FillAngle", "彩虹方向");
            Slider("_FillSpeed", "彩虹速度");
            Slider("_FillPixelsPerCycle", "彩虹帶寬 / 像素");
            Slider("_FillDensityAnim", "彩虹密度倍率");
            Slider("_FillHue", "色相偏移");
            Slider("_FillSaturation", "飽和度");
            Slider("_FillIntensity", "彩虹強度");
            Slider("_FillSoftWhite", "柔和白光");
            Slider("_FillDetailBoost", "細節強化");

            Toggle("_FillL2Enable", "第二層彩虹", "_FILL_L2_ON");
            if (Float("_FillL2Enable") > 0.5f)
            {
                using (new EditorGUI.IndentLevelScope())
                {
                    Slider("_FillL2Mix", "第二層混合");
                    Slider("_FillL2Angle", "第二層角度");
                    Slider("_FillL2Speed", "第二層速度");
                    Slider("_FillL2Density", "第二層密度");
                }
            }
        }
    }

    private void DrawSweep()
    {
        _showSweep = EditorGUILayout.Foldout(_showSweep, "掃光", true);
        if (!_showSweep) return;

        using (new EditorGUI.IndentLevelScope())
        {
            Toggle("_SweepEnable", "啟用外側掃光", "_SWEEP_ON");
            if (Float("_SweepEnable") > 0.5f)
            {
                Slider("_SweepAngle", "外掃光角度");
                Slider("_SweepSpeed", "外掃光速度");
                Slider("_SweepWidthPx", "螢幕模式寬度 px");
                Slider("_SweepFeatherPx", "螢幕模式羽化 px");
                Slider("_SweepObjWidth", "物件模式寬度");
                Slider("_SweepObjFeather", "物件模式羽化");
                Color("_SweepColor", "外掃光顏色");
                Slider("_SweepColorIntensity", "外掃光強度");
                Slider("_SweepColorMode", "混合模式 0相加 1濾色 2取代");
                Slider("_SweepExcludeFill", "避免覆蓋填色區");
            }

            Toggle("_InnerSweepEnable", "啟用內側掃光", "_INNER_SWEEP_ON");
            if (Float("_InnerSweepEnable") > 0.5f)
            {
                using (new EditorGUI.IndentLevelScope())
                {
                    Color("_InnerSweepColor", "內掃光顏色");
                    Slider("_InnerSweepAngle", "內掃光角度");
                    Slider("_InnerSweepSpeed", "內掃光速度");
                    Slider("_InnerSweepDensity", "內掃光密度");
                    Slider("_InnerSweepWidth", "內掃光寬度");
                    Slider("_InnerSweepFeather", "內掃光羽化");
                    Slider("_InnerSweepIntensity", "內掃光強度");
                    Texture("_InnerSweepMaskTex", "內掃光遮罩");
                }
            }
        }
    }

    private void DrawDiamond()
    {
        _showDiamond = EditorGUILayout.Foldout(_showDiamond, "鑽石 / 寶石質感", true);
        if (!_showDiamond) return;

        using (new EditorGUI.IndentLevelScope())
        {
            Toggle("_DiamondEnable", "啟用鑽石覆蓋", "_DIAMOND_ON");
            if (Float("_DiamondEnable") < 0.5f) return;

            Texture("_DiamondTex", "鑽石法線貼圖");
            Slider("_DiamondIntensity", "鑽石高光強度");
            Slider("_DiamondBaseDim", "壓暗底層彩虹");
            Slider("_DiamondTiling", "鑽石密度");
            Slider("_DiamondSparkleSpeed", "閃爍速度");
            Slider("_DiamondNormalFlat", "光滑度");
            Slider("_DiamondContrast", "陰影對比");

            Toggle("_DiamondL2Enable", "第二層鑽石", "_DIAMOND_L2_ON");
            if (Float("_DiamondL2Enable") > 0.5f)
            {
                using (new EditorGUI.IndentLevelScope())
                {
                    Slider("_DiamondL2Mix", "第二層混合");
                    Slider("_DiamondL2Tiling", "第二層密度");
                    Slider("_DiamondL2SparkleSpeed", "第二層閃爍");
                }
            }
        }
    }

    private void DrawAdvanced()
    {
        _showAdvanced = EditorGUILayout.Foldout(_showAdvanced, "進階設定 / 同步 / 遮罩 / Noise", true);
        if (!_showAdvanced) return;

        using (new EditorGUI.IndentLevelScope())
        {
            EditorGUILayout.LabelField("彩虹座標同步", EditorStyles.boldLabel);
            Slider("_FillGroupMode", "填色群組 0整體 1每物件");
            Slider("_FillPerObjCoord", "每物件座標 0單字 1整串");
            Slider("_FillObjPixelsPerCycle", "每物件循環像素");
            Slider("_FillObjTiling", "每物件座標平鋪");
            Slider("_FillObjFreqGain", "每物件密度增益");
            Vector("_FillRadialCenter", "放射中心偏移");
            Slider("_FillRadialTurns", "放射/螺旋手臂數");
            Slider("_FillSpiralScale", "螺旋緊密度");
            Slider("_FillRadialBands", "放射色帶密度");

            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("Noise", EditorStyles.boldLabel);
            Toggle("_FillNoiseEnable", "啟用彩虹 Noise", "_FILL_NOISE_ON");
            if (Float("_FillNoiseEnable") > 0.5f)
            {
                Slider("_FillNoiseScale", "Noise 尺寸");
                Slider("_FillNoiseStrength", "Noise 擾動強度");
                Slider("_FillNoiseWarp", "Noise 扭曲感");
                Slider("_FillNoiseStyle", "Noise 風格");
                Slider("_FillNoiseStyleMix", "風格強度");
            }

            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("遮罩", EditorStyles.boldLabel);
            Toggle("_FillMaskEnable", "啟用填色遮罩", "_FILL_MASK_ON");
            if (Float("_FillMaskEnable") > 0.5f)
            {
                Texture("_FillMaskTex", "填色遮罩");
                Slider("_FillMaskFeatherPx", "填色遮罩羽化");
                Slider("_FillMaskInvert", "填色遮罩反相");
            }

            Toggle("_SweepMaskEnable", "啟用掃光遮罩", "_SWEEP_MASK_ON");
            if (Float("_SweepMaskEnable") > 0.5f)
            {
                Texture("_SweepMaskTex", "掃光遮罩");
                Slider("_SweepMaskFeatherPx", "掃光遮罩羽化");
                Slider("_SweepMaskInvert", "掃光遮罩反相");
            }

            EditorGUILayout.Space(5);
            EditorGUILayout.LabelField("外掃光座標", EditorStyles.boldLabel);
            Slider("_SweepGroupMode", "外掃光群組 0整體 1每物件");
            Slider("_SweepFlowMode", "外掃光模式 0線性 1放射");
            Slider("_SweepUseObject", "線性使用物件座標");
            Slider("_SweepObjTiling", "物件平鋪密度");
            Slider("_SweepPixelsPerCycle", "螢幕每循環像素");
            Slider("_SweepRefHeight", "螢幕參考高度");
            Vector("_RadialCenter", "外掃光放射中心");
            Slider("_RadialTurns", "外掃光放射圈數");
        }
    }

    private void DrawDebug()
    {
        _showDebug = EditorGUILayout.Foldout(_showDebug, "Debug", true);
        if (!_showDebug) return;
        using (new EditorGUI.IndentLevelScope())
        {
            Slider("_FillAlphaCut", "透明度剪裁");
            Slider("_FillEdgeAA", "邊緣抗鋸齒");
            Slider("_DebugView", "顯示 Alpha Debug");
        }
    }

    private void ApplyPresetMobile()
    {
        Set("_FillEnable", 1); Set("_FillL2Enable", 0); Set("_FillNoiseEnable", 0);
        Set("_DiamondEnable", 0); Set("_DiamondL2Enable", 0); Set("_InnerSweepEnable", 0);
        Set("_SweepEnable", 1); Set("_FillIntensity", 1.05f); Set("_FillPixelsPerCycle", 220);
        Set("_SweepColorIntensity", 0.9f); Set("_SweepWidthPx", 32); Set("_SweepFeatherPx", 5);
        SyncKeywords(_mat);
    }

    private void ApplyPresetStandard()
    {
        Set("_FillEnable", 1); Set("_FillL2Enable", 0); Set("_FillNoiseEnable", 0);
        Set("_DiamondEnable", 0); Set("_InnerSweepEnable", 1); Set("_SweepEnable", 1);
        Set("_FillIntensity", 1.25f); Set("_FillSaturation", 1); Set("_FillPixelsPerCycle", 180);
        Set("_InnerSweepIntensity", 0.65f); Set("_SweepColorIntensity", 1.15f);
        SyncKeywords(_mat);
    }

    private void ApplyPresetBigWin()
    {
        Set("_FillEnable", 1); Set("_FillL2Enable", 1); Set("_FillNoiseEnable", 1);
        Set("_DiamondEnable", 1); Set("_DiamondL2Enable", 1); Set("_InnerSweepEnable", 1); Set("_SweepEnable", 1);
        Set("_FillIntensity", 1.55f); Set("_FillPixelsPerCycle", 135); Set("_FillL2Mix", 0.42f);
        Set("_FillNoiseStrength", 0.08f); Set("_DiamondIntensity", 1.15f); Set("_DiamondBaseDim", 0.35f);
        Set("_SweepColorIntensity", 1.65f); Set("_InnerSweepIntensity", 1.0f);
        SyncKeywords(_mat);
    }

    private void ApplyPresetParticle()
    {
        ApplyPresetMobile();
        Set("_ParticleMode", 1); Set("_FillGroupMode", 0); Set("_SweepGroupMode", 0); Set("_SweepUseObject", 0);
        Set("_FillNoiseEnable", 0); Set("_FillPixelsPerCycle", 160); Set("_SweepPixelsPerCycle", 210);
        SyncKeywords(_mat);
    }

    private void SyncKeywords(Material m)
    {
        Keyword(m, "_FILL_ON", "_FillEnable");
        Keyword(m, "_FILL_L2_ON", "_FillL2Enable");
        Keyword(m, "_FILL_MASK_ON", "_FillMaskEnable");
        Keyword(m, "_FILL_NOISE_ON", "_FillNoiseEnable");
        Keyword(m, "_DIAMOND_ON", "_DiamondEnable");
        Keyword(m, "_DIAMOND_L2_ON", "_DiamondL2Enable");
        Keyword(m, "_INNER_SWEEP_ON", "_InnerSweepEnable");
        Keyword(m, "_SWEEP_ON", "_SweepEnable");
        Keyword(m, "_SWEEP_MASK_ON", "_SweepMaskEnable");
        Keyword(m, "_PARTICLEMODE_ON", "_ParticleMode");
        EditorUtility.SetDirty(m);
    }

    private void Keyword(Material m, string keyword, string prop)
    {
        if (!m.HasProperty(prop)) return;
        if (m.GetFloat(prop) > 0.5f) m.EnableKeyword(keyword);
        else m.DisableKeyword(keyword);
    }

    private MaterialProperty P(string name) => FindProperty(name, _props, false);

    private float Float(string name)
    {
        MaterialProperty p = P(name);
        return p == null ? 0f : p.floatValue;
    }

    private void Set(string name, float value)
    {
        foreach (Object target in _editor.targets)
        {
            if (target is Material m && m.HasProperty(name))
            {
                Undo.RecordObject(m, "Apply BMFont Rainbow Preset");
                m.SetFloat(name, value);
                EditorUtility.SetDirty(m);
            }
        }
    }

    private void Slider(string name, string label)
    {
        MaterialProperty p = P(name);
        if (p != null) _editor.ShaderProperty(p, label);
    }

    private void Toggle(string name, string label, string keyword)
    {
        MaterialProperty p = P(name);
        if (p == null) return;

        EditorGUI.BeginChangeCheck();
        bool value = EditorGUILayout.Toggle(label, p.floatValue > 0.5f);
        if (EditorGUI.EndChangeCheck())
        {
            p.floatValue = value ? 1f : 0f;
            foreach (Object target in _editor.targets)
            {
                if (target is Material m)
                {
                    if (value) m.EnableKeyword(keyword);
                    else m.DisableKeyword(keyword);
                    EditorUtility.SetDirty(m);
                }
            }
        }
    }

    private void Texture(string name, string label)
    {
        MaterialProperty p = P(name);
        if (p != null) _editor.TexturePropertySingleLine(new GUIContent(label), p);
    }

    private void Color(string name, string label)
    {
        MaterialProperty p = P(name);
        if (p != null) _editor.ColorProperty(p, label);
    }

    private void Vector(string name, string label)
    {
        MaterialProperty p = P(name);
        if (p != null) _editor.VectorProperty(p, label);
    }
}
