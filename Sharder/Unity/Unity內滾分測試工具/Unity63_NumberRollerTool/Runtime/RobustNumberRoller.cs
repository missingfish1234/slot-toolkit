using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

#if UNITY_EDITOR
using UnityEditor;
#endif

namespace SlotTools.NumberRoller
{
    /// <summary>
    /// Unity 6.3 老虎機數字滾分工具 v4。
    /// 重點支援：UGUI Text + Font、TMP、UGUI Image Sprite、MakeFont/BMFont、UGUI_IMAGE Text Font 類型 Prefab/Component。
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(RectTransform))]
    [AddComponentMenu("Slot Tools/Number Roller/Robust Number Roller v4")]
    public class RobustNumberRoller : MonoBehaviour
    {
        public enum DisplayMode
        {
            UGUIText,
            TextMeshPro,
            ImageLine,
            ImageOdometer
        }

        public enum GlyphSource
        {
            DirectSprites,
            BMFontFntTexture,
            UnityFontSettings,
            UGUIImageTextFontPrefab
        }

        public enum CountMode
        {
            DurationSmooth,
            UnitsPerSecond,
            StepPerTick
        }

        public enum CountDirection
        {
            Auto,
            CountUp,
            CountDown
        }

        public enum VisualDirection
        {
            Up,
            Down
        }

        public enum RoundingMode
        {
            Floor,
            Round,
            Ceil
        }

        [Serializable]
        public class CharSpritePair
        {
            public string character = "";
            public Sprite sprite;
        }

        private sealed class GlyphInfo
        {
            public Sprite sprite;
            public Vector2 size;
            public float advance;
        }

        private sealed class DigitColumn
        {
            public RectTransform root;
            public readonly List<RectTransform> digitRects = new List<RectTransform>();
            public int placeIndex;
        }

        [Header("輸出模式")]
        public DisplayMode displayMode = DisplayMode.ImageOdometer;

        [Header("文字元件")]
        public Text uguiText;
        public TMP_Text tmpText;
        public Font unityFont;

        [Header("圖片字來源")]
        public GlyphSource glyphSource = GlyphSource.UGUIImageTextFontPrefab;
        [Tooltip("拖你的 UGUI_IMAGE Text Font / MakeFont 字典 prefab 或掛有字典的 Component。會嘗試讀 FontDictionary、m_SpriteAry、SpriteAry。")]
        public UnityEngine.Object uguiImageTextFontObject;

        [Tooltip("直接指定 Sprite 時，請依序放 0~9。也可用下方按鈕從 UGUI_IMAGE 字典自動抽出。")]
        public Sprite[] digitSprites = new Sprite[10];
        public Sprite commaSprite;
        public Sprite dotSprite;
        public Sprite minusSprite;
        public Sprite plusSprite;
        public Sprite dollarSprite;
        public List<CharSpritePair> extraSprites = new List<CharSpritePair>();

        [Header("BMFont / MakeFont")]
        public TextAsset bmFontText;
        public Texture2D bmFontTexture;
        [Min(1)] public float spritePixelsPerUnit = 100f;

        [Header("數值")]
        public double startValue = 0;
        public double targetValue = 88888;
        public CountDirection countDirection = CountDirection.Auto;
        public bool playOnEnable = false;
        public bool useUnscaledTime = false;

        [Header("滾分速度")]
        [Tooltip("DurationSmooth：照時間平滑補間。UnitsPerSecond：依每秒增加分數。StepPerTick：每幾秒固定加幾分，適合一分一分快速跳。")]
        public CountMode countMode = CountMode.UnitsPerSecond;
        [Min(0.01f)] public float duration = 1.6f;
        [Min(0.01)] public double unitsPerSecond = 6000;
        [Tooltip("StepPerTick 模式用。1 = 一分一分加；10 = 每次跳 10 分。")]
        [Min(0.0001)] public double pointsPerTick = 1;
        [Tooltip("StepPerTick 模式用。0.01 = 每 0.01 秒跳一次。示意影片建議 0.005 ~ 0.03。")]
        [Min(0.0001f)] public float tickInterval = 0.01f;
        [Tooltip("避免分數很大時單幀卡死。")]
        [Range(1, 5000)] public int maxTicksPerFrame = 500;
        public AnimationCurve speedCurve = AnimationCurve.EaseInOut(0, 0, 1, 1);

        [Header("格式")]
        public string prefix = "";
        public string suffix = "";
        public bool useThousandsSeparator = true;
        [Range(0, 4)] public int decimalPlaces = 0;
        public RoundingMode roundingMode = RoundingMode.Round;
        public bool hideMinusSign = false;
        public bool padZero = false;
        [Min(1)] public int digitCount = 6;
        [Tooltip("ImageOdometer 用。開啟後，版面會用 start/target 較大的位數自動增加，不會只卡 digitCount。")]
        public bool autoExpandDigitCount = true;

        [Header("Image 版面")]
        public RectTransform imageRoot;
        [Min(1)] public float charWidth = 42f;
        [Min(1)] public float charHeight = 76f;
        [Min(0)] public float spacing = 0f;
        [Min(1)] public float symbolWidth = 20f;
        public bool useNativeGlyphWidth = true;
        public bool preserveAspect = true;
        public Color imageColor = Color.white;

        [Header("輪帶視覺")]
        public VisualDirection visualDirection = VisualDirection.Up;
        [Tooltip("數字輪帶用目前分數逐位計算。開啟後會像真正分數一分一分上去，而不是整排直接補到目標。")]
        public bool odometerFollowsCurrentValue = true;
        [Tooltip("只在 odometerFollowsCurrentValue 關閉時使用。保留舊版整位數從開始轉到目標的表演。")]
        [Range(0, 8)] public int extraRollLoops = 1;

        [Header("缺字 fallback")]
        public TMP_FontAsset fallbackTMPFont;
        [Min(8)] public float fallbackFontSize = 56f;

        [Header("事件")]
        public UnityEvent onRollStart;
        public UnityEvent onRollComplete;

        public double CurrentValue => _currentValue;
        public bool IsRolling => _isRolling;

        private readonly Dictionary<char, GlyphInfo> _glyphs = new Dictionary<char, GlyphInfo>();
        private readonly List<DigitColumn> _columns = new List<DigitColumn>();
        private double _from;
        private double _to;
        private double _currentValue;
        private float _elapsed;
        private float _durationResolved;
        private float _tickAccumulator;
        private bool _isRolling;
        private string _lastText;
        private string _layoutText;

        private void Reset()
        {
            AutoBind();
        }

        private void Awake()
        {
            AutoBind();
            RebuildDisplay();
            SetImmediate(startValue);
        }

        private void OnEnable()
        {
            if (playOnEnable) Play();
        }

#if UNITY_EDITOR
        private void OnValidate()
        {
            digitCount = Mathf.Max(1, digitCount);
            charWidth = Mathf.Max(1, charWidth);
            charHeight = Mathf.Max(1, charHeight);
            symbolWidth = Mathf.Max(1, symbolWidth);
            tickInterval = Mathf.Max(0.0001f, tickInterval);
            pointsPerTick = Math.Max(0.0001, pointsPerTick);
        }
#endif

        private void Update()
        {
            if (!_isRolling) return;

            float dt = useUnscaledTime ? Time.unscaledDeltaTime : Time.deltaTime;
            if (countMode == CountMode.StepPerTick)
            {
                UpdateStepPerTick(dt);
            }
            else
            {
                UpdateSmoothOrSpeed(dt);
            }
        }

        [ContextMenu("自動綁定")]
        public void AutoBind()
        {
            if (imageRoot == null) imageRoot = GetComponent<RectTransform>();
            if (uguiText == null) uguiText = GetComponent<Text>() ?? GetComponentInChildren<Text>(true);
            if (tmpText == null) tmpText = GetComponent<TMP_Text>() ?? GetComponentInChildren<TMP_Text>(true);
            if (uguiText != null && unityFont != null) uguiText.font = unityFont;
            EnsureLayout();
        }

        [ContextMenu("重建顯示")]
        public void RebuildDisplay()
        {
            AutoBind();
            BuildGlyphs();
            ClearChildren();
            _columns.Clear();
            _lastText = null;

            if (displayMode == DisplayMode.ImageOdometer)
            {
                BuildOdometerLayout();
                ApplyOdometerByCurrentValue(_currentValue);
            }
            else
            {
                ApplyStatic(_currentValue);
            }
        }

        [ContextMenu("播放滾分")]
        public void Play()
        {
            Play(startValue, targetValue);
        }

        public void PlayTo(double to)
        {
            Play(_currentValue, to);
        }

        public void PlayAdd(double delta)
        {
            Play(_currentValue, _currentValue + delta);
        }

        public void Play(double from, double to)
        {
            ResolveDirection(ref from, ref to);
            _from = from;
            _to = to;
            _currentValue = from;
            _elapsed = 0f;
            _tickAccumulator = 0f;
            _durationResolved = ResolveDuration(from, to);

            if (displayMode == DisplayMode.ImageOdometer)
            {
                RebuildDisplay();
            }
            ApplyCurrent();
            _isRolling = true;
            onRollStart?.Invoke();
        }

        [ContextMenu("設定到起始值")]
        public void SetToStart()
        {
            SetImmediate(startValue);
        }

        [ContextMenu("設定到目標值")]
        public void SetToTarget()
        {
            SetImmediate(targetValue);
        }

        public void SetImmediate(double value)
        {
            _isRolling = false;
            _from = value;
            _to = value;
            _currentValue = value;
            ApplyCurrent();
        }

        [ContextMenu("停止在目標值")]
        public void StopAtTarget()
        {
            _currentValue = _to;
            _isRolling = false;
            ApplyCurrent();
            onRollComplete?.Invoke();
        }

        [ContextMenu("列出缺字報告")]
        public string GetMissingGlyphReport()
        {
            BuildGlyphs();
            string sample = prefix + suffix + "0123456789,.+- $BEKMPTXYZxGQ";
            List<char> missing = new List<char>();
            foreach (char c in sample)
            {
                if (c == ' ') continue;
                if (!_glyphs.ContainsKey(c) && !missing.Contains(c)) missing.Add(c);
            }
            if (missing.Count == 0) return "OK：常用數字與符號都讀得到。";
            return "缺少字元：" + string.Join(", ", missing.ConvertAll(c => c.ToString()).ToArray());
        }

        private void UpdateSmoothOrSpeed(float dt)
        {
            _elapsed += dt;
            float t = _durationResolved <= 0.0001f ? 1f : Mathf.Clamp01(_elapsed / _durationResolved);
            float eased = countMode == CountMode.DurationSmooth && speedCurve != null ? Mathf.Clamp01(speedCurve.Evaluate(t)) : t;
            _currentValue = _from + (_to - _from) * eased;
            ApplyCurrent();

            if (t >= 1f)
            {
                CompleteRoll();
            }
        }

        private void UpdateStepPerTick(float dt)
        {
            _tickAccumulator += dt;
            int loops = 0;
            double dir = Math.Sign(_to - _currentValue);
            if (Math.Abs(dir) < 0.001)
            {
                CompleteRoll();
                return;
            }

            while (_tickAccumulator >= tickInterval && loops < maxTicksPerFrame)
            {
                _tickAccumulator -= tickInterval;
                _currentValue += pointsPerTick * dir;
                if ((dir > 0 && _currentValue >= _to) || (dir < 0 && _currentValue <= _to))
                {
                    _currentValue = _to;
                    break;
                }
                loops++;
            }

            // 即使這一幀還沒到 tick，也要保持畫面目前值，不讓它瞬間跳目標。
            ApplyCurrent();

            if (Math.Abs(_currentValue - _to) < 0.00001)
            {
                CompleteRoll();
            }
        }

        private void CompleteRoll()
        {
            _currentValue = _to;
            _isRolling = false;
            ApplyCurrent();
            onRollComplete?.Invoke();
        }

        private void ApplyCurrent()
        {
            if (displayMode == DisplayMode.ImageOdometer)
            {
                if (_columns.Count == 0) BuildOdometerLayout();
                if (odometerFollowsCurrentValue) ApplyOdometerByCurrentValue(_currentValue);
                else ApplyLegacyOdometer();
            }
            else
            {
                ApplyStatic(_currentValue);
            }
        }

        private void ApplyStatic(double value)
        {
            string text = FormatValue(value);
            if (displayMode == DisplayMode.UGUIText)
            {
                if (uguiText != null)
                {
                    if (unityFont != null) uguiText.font = unityFont;
                    uguiText.text = text;
                }
                return;
            }
            if (displayMode == DisplayMode.TextMeshPro)
            {
                if (tmpText != null) tmpText.text = text;
                return;
            }
            if (displayMode != DisplayMode.ImageLine) return;

            BuildGlyphs();
            if (_lastText == text) return;
            _lastText = text;
            ClearChildren();
            foreach (char c in text) CreateImageGlyph(c, imageRoot, false, 0);
        }

        public string FormatValue(double value)
        {
            if (hideMinusSign) value = Math.Abs(value);
            double pow = Math.Pow(10, decimalPlaces);
            switch (roundingMode)
            {
                case RoundingMode.Floor: value = Math.Floor(value * pow) / pow; break;
                case RoundingMode.Ceil: value = Math.Ceiling(value * pow) / pow; break;
                default: value = Math.Round(value, decimalPlaces); break;
            }
            string fmt = useThousandsSeparator ? "N" + decimalPlaces : "F" + decimalPlaces;
            return prefix + value.ToString(fmt, CultureInfo.InvariantCulture) + suffix;
        }

        private void BuildOdometerLayout()
        {
            BuildGlyphs();
            EnsureLayout();
            ClearChildren();
            _columns.Clear();

            string body = BuildDigitBody(MaxAbsForLayout());
            _layoutText = prefix + body + suffix;
            int place = CountDigitsIn(_layoutText) - 1;

            foreach (char c in _layoutText)
            {
                if (char.IsDigit(c))
                {
                    CreateDigitColumn(place);
                    place--;
                }
                else
                {
                    CreateImageGlyph(c, imageRoot, false, 0);
                }
            }
        }

        private long MaxAbsForLayout()
        {
            long a = Math.Abs((long)Math.Round(startValue));
            long b = Math.Abs((long)Math.Round(targetValue));
            return Math.Max(a, b);
        }

        private string BuildDigitBody(long value)
        {
            string digits = Math.Abs(value).ToString(CultureInfo.InvariantCulture);
            int minDigits = digitCount;
            if (autoExpandDigitCount) minDigits = Math.Max(minDigits, digits.Length);
            if (padZero || digits.Length < minDigits) digits = digits.PadLeft(minDigits, '0');
            if (!autoExpandDigitCount && digits.Length > digitCount) digits = digits.Substring(digits.Length - digitCount);

            if (useThousandsSeparator)
            {
                for (int i = digits.Length - 3; i > 0; i -= 3) digits = digits.Insert(i, ",");
            }
            return digits;
        }

        private void CreateDigitColumn(int placeIndex)
        {
            GameObject viewportGO = new GameObject("Digit_10^" + placeIndex, typeof(RectTransform), typeof(RectMask2D), typeof(LayoutElement));
            viewportGO.transform.SetParent(imageRoot, false);
            RectTransform viewport = viewportGO.GetComponent<RectTransform>();
            LayoutElement le = viewportGO.GetComponent<LayoutElement>();
            viewport.sizeDelta = new Vector2(charWidth, charHeight);
            le.preferredWidth = charWidth;
            le.preferredHeight = charHeight;

            DigitColumn col = new DigitColumn { root = viewport, placeIndex = placeIndex };
            for (int i = 0; i < 10; i++)
            {
                GameObject go = new GameObject("D_" + i, typeof(RectTransform), typeof(Image));
                go.transform.SetParent(viewportGO.transform, false);
                RectTransform rt = go.GetComponent<RectTransform>();
                Image img = go.GetComponent<Image>();
                GlyphInfo g = GetGlyph((char)('0' + i));
                if (g != null && g.sprite != null) img.sprite = g.sprite;
                img.color = imageColor;
                img.preserveAspect = preserveAspect;
                rt.anchorMin = new Vector2(0.5f, 0.5f);
                rt.anchorMax = new Vector2(0.5f, 0.5f);
                rt.pivot = new Vector2(0.5f, 0.5f);
                rt.sizeDelta = new Vector2(charWidth, charHeight);
                col.digitRects.Add(rt);
            }
            _columns.Add(col);
        }

        private void ApplyOdometerByCurrentValue(double value)
        {
            double abs = Math.Abs(value);
            float dirMul = visualDirection == VisualDirection.Up ? 1f : -1f;

            foreach (DigitColumn col in _columns)
            {
                double raw = abs / Pow10(col.placeIndex);
                float pos = (float)(raw - Math.Floor(raw / 10.0) * 10.0);

                for (int i = 0; i < col.digitRects.Count; i++)
                {
                    RectTransform rt = col.digitRects[i];
                    float delta = pos - i;
                    if (delta > 5f) delta -= 10f;
                    if (delta < -5f) delta += 10f;
                    rt.anchoredPosition = new Vector2(0f, delta * charHeight * dirMul);
                }
            }
        }

        private void ApplyLegacyOdometer()
        {
            float t = _durationResolved <= 0.0001f ? 1f : Mathf.Clamp01(_elapsed / _durationResolved);
            float eased = speedCurve != null ? Mathf.Clamp01(speedCurve.Evaluate(t)) : t;
            long from = Math.Abs((long)Math.Round(_from));
            long to = Math.Abs((long)Math.Round(_to));
            float dirMul = visualDirection == VisualDirection.Up ? 1f : -1f;

            foreach (DigitColumn col in _columns)
            {
                long p = Pow10(col.placeIndex);
                int startDigit = (int)((from / p) % 10);
                int targetDigit = (int)((to / p) % 10);
                float end = targetDigit;
                if (extraRollLoops > 0 || end < startDigit) end += 10f * Mathf.Max(0, extraRollLoops);
                if (end < startDigit) end += 10f;
                float pos = Mathf.Lerp(startDigit, end, eased) % 10f;
                for (int i = 0; i < col.digitRects.Count; i++)
                {
                    float delta = pos - i;
                    if (delta > 5f) delta -= 10f;
                    if (delta < -5f) delta += 10f;
                    col.digitRects[i].anchoredPosition = new Vector2(0f, delta * charHeight * dirMul);
                }
            }
        }

        private void CreateImageGlyph(char c, RectTransform parent, bool inStrip, int stripIndex)
        {
            GlyphInfo g = GetGlyph(c);
            if (g == null || g.sprite == null)
            {
                CreateFallbackText(c.ToString(), parent, inStrip, stripIndex);
                return;
            }

            GameObject go = new GameObject("Glyph_" + SafeName(c), typeof(RectTransform), typeof(Image), typeof(LayoutElement));
            go.transform.SetParent(parent, false);
            RectTransform rt = go.GetComponent<RectTransform>();
            Image img = go.GetComponent<Image>();
            LayoutElement le = go.GetComponent<LayoutElement>();
            img.sprite = g.sprite;
            img.color = imageColor;
            img.preserveAspect = preserveAspect;

            float w = char.IsDigit(c) ? charWidth : symbolWidth;
            if (useNativeGlyphWidth && g.advance > 0) w = g.advance;
            float h = charHeight;
            rt.sizeDelta = new Vector2(w, h);
            le.preferredWidth = w;
            le.preferredHeight = h;
        }

        private void CreateFallbackText(string s, RectTransform parent, bool inStrip, int stripIndex)
        {
            GameObject go = new GameObject("Missing_" + s, typeof(RectTransform), typeof(TextMeshProUGUI), typeof(LayoutElement));
            go.transform.SetParent(parent, false);
            RectTransform rt = go.GetComponent<RectTransform>();
            TMP_Text txt = go.GetComponent<TMP_Text>();
            LayoutElement le = go.GetComponent<LayoutElement>();
            txt.text = s;
            txt.font = fallbackTMPFont;
            txt.fontSize = fallbackFontSize;
            txt.alignment = TextAlignmentOptions.Center;
            txt.color = imageColor;
            txt.enableWordWrapping = false;
            float w = char.IsDigit(s[0]) ? charWidth : symbolWidth;
            rt.sizeDelta = new Vector2(w, charHeight);
            le.preferredWidth = w;
            le.preferredHeight = charHeight;
        }

        private void BuildGlyphs()
        {
            _glyphs.Clear();
            switch (glyphSource)
            {
                case GlyphSource.DirectSprites:
                    BuildDirectSprites();
                    break;
                case GlyphSource.BMFontFntTexture:
                    BuildBMFontSprites();
                    break;
                case GlyphSource.UnityFontSettings:
                    BuildUnityFontSprites();
                    break;
                case GlyphSource.UGUIImageTextFontPrefab:
                    BuildUGUIImageTextFontSprites();
                    break;
            }
        }

        private GlyphInfo GetGlyph(char c)
        {
            if (_glyphs.Count == 0) BuildGlyphs();
            if (_glyphs.TryGetValue(c, out GlyphInfo g)) return g;
            return null;
        }

        private void BuildDirectSprites()
        {
            if (digitSprites != null)
            {
                for (int i = 0; i < Mathf.Min(10, digitSprites.Length); i++)
                    AddGlyphIf((char)('0' + i), digitSprites[i]);
            }
            AddGlyphIf(',', commaSprite);
            AddGlyphIf('.', dotSprite);
            AddGlyphIf('-', minusSprite);
            AddGlyphIf('+', plusSprite);
            AddGlyphIf('$', dollarSprite);
            if (extraSprites != null)
            {
                foreach (CharSpritePair p in extraSprites)
                {
                    if (p == null || string.IsNullOrEmpty(p.character) || p.sprite == null) continue;
                    AddGlyphIf(p.character[0], p.sprite);
                }
            }
        }

        private void BuildBMFontSprites()
        {
            if (bmFontText == null || bmFontTexture == null) return;
            string[] lines = bmFontText.text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            foreach (string raw in lines)
            {
                string line = raw.Trim();
                if (!line.StartsWith("char ", StringComparison.Ordinal)) continue;
                int id = ReadInt(line, "id", -1);
                int x = ReadInt(line, "x", 0);
                int y = ReadInt(line, "y", 0);
                int w = ReadInt(line, "width", 0);
                int h = ReadInt(line, "height", 0);
                int adv = ReadInt(line, "xadvance", w);
                if (id < 0 || w <= 0 || h <= 0) continue;
                Rect rect = new Rect(x, bmFontTexture.height - y - h, w, h);
                AddGlyphFromRect((char)id, bmFontTexture, rect, new Vector2(w, h), adv);
            }
        }

        private void BuildUnityFontSprites()
        {
            if (unityFont == null) return;
            try
            {
                unityFont.RequestCharactersInTexture("0123456789,.+- $BEKMPTXYZxGQ" + prefix + suffix, Mathf.Max(1, Mathf.RoundToInt(charHeight)), FontStyle.Normal);
            }
            catch { }

            if (unityFont.material == null || unityFont.material.mainTexture == null) return;
            Texture2D tex = unityFont.material.mainTexture as Texture2D;
            if (tex == null) return;

            CharacterInfo[] chars = unityFont.characterInfo;
            if (chars == null || chars.Length == 0)
            {
                foreach (char c in "0123456789,.+- $BEKMPTXYZxGQ" + prefix + suffix)
                {
                    if (c == ' ') continue;
                    if (unityFont.GetCharacterInfo(c, out CharacterInfo ci, Mathf.Max(1, Mathf.RoundToInt(charHeight)), FontStyle.Normal))
                        AddGlyphFromCharacterInfo(c, tex, ci);
                }
                return;
            }

            foreach (CharacterInfo ci in chars)
            {
                AddGlyphFromCharacterInfo((char)ci.index, tex, ci);
            }
        }

        private void AddGlyphFromCharacterInfo(char c, Texture2D tex, CharacterInfo ci)
        {
            Rect uv = ci.uv;
            float x = uv.x * tex.width;
            float y = uv.height < 0 ? (uv.y + uv.height) * tex.height : uv.y * tex.height;
            float w = Mathf.Abs(uv.width * tex.width);
            float h = Mathf.Abs(uv.height * tex.height);
            if (w <= 0.5f || h <= 0.5f) return;
            Rect rect = new Rect(Mathf.Round(x), Mathf.Round(y), Mathf.Round(w), Mathf.Round(h));
            float adv = ci.advance > 0 ? ci.advance : w;
            AddGlyphFromRect(c, tex, rect, new Vector2(w, h), adv);
        }

        private void BuildUGUIImageTextFontSprites()
        {
            if (uguiImageTextFontObject == null)
            {
                BuildDirectSprites();
                return;
            }

            bool found = TryExtractSpritesByReflection(uguiImageTextFontObject, true);
            if (!found && uguiImageTextFontObject is GameObject go)
            {
                Component[] comps = go.GetComponentsInChildren<Component>(true);
                foreach (Component c in comps)
                {
                    if (c == null) continue;
                    if (TryExtractSpritesByReflection(c, false)) found = true;
                }
            }

            if (!found) BuildDirectSprites();
        }

        private bool TryExtractSpritesByReflection(UnityEngine.Object obj, bool allowGameObject)
        {
            if (obj == null) return false;
            bool found = false;

            if (allowGameObject && obj is GameObject go)
            {
                foreach (Component c in go.GetComponentsInChildren<Component>(true))
                    if (c != null && TryExtractSpritesByReflection(c, false)) found = true;
                return found;
            }

            Type t = obj.GetType();
            BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            foreach (FieldInfo fi in t.GetFields(flags))
            {
                object value = null;
                try { value = fi.GetValue(obj); } catch { continue; }
                if (value == null) continue;

                string fieldName = fi.Name.ToLowerInvariant();
                if (fieldName.Contains("spriteary") || fieldName.Contains("sprites") || fieldName.Contains("spritearray"))
                {
                    if (TryAddArrayByDefaultOrder(value)) found = true;
                }

                if (fieldName.Contains("fontdictionary") || fieldName.Contains("dictionary"))
                {
                    if (TryAddDictionary(value)) found = true;
                    if (TryAddSerializedDictionaryLike(value)) found = true;
                }
            }
            return found;
        }

        private bool TryAddDictionary(object value)
        {
            if (value is IDictionary dict)
            {
                bool any = false;
                foreach (DictionaryEntry entry in dict)
                {
                    if (entry.Key == null || entry.Value == null) continue;
                    char c = entry.Key.ToString()[0];
                    if (entry.Value is Sprite s)
                    {
                        AddGlyphIf(c, s);
                        any = true;
                    }
                }
                return any;
            }
            return false;
        }

        private bool TryAddSerializedDictionaryLike(object value)
        {
            Type t = value.GetType();
            BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            FieldInfo keysField = t.GetField("_Keys", flags) ?? t.GetField("keys", flags) ?? t.GetField("Keys", flags);
            FieldInfo valuesField = t.GetField("_Values", flags) ?? t.GetField("values", flags) ?? t.GetField("Values", flags);
            if (keysField == null || valuesField == null) return false;
            object keysObj = keysField.GetValue(value);
            object valuesObj = valuesField.GetValue(value);
            if (!(keysObj is IList keys) || !(valuesObj is IList values)) return false;

            bool any = false;
            int count = Mathf.Min(keys.Count, values.Count);
            for (int i = 0; i < count; i++)
            {
                object k = keys[i];
                object v = values[i];
                if (k == null || v == null) continue;
                string ks = k.ToString();
                if (string.IsNullOrEmpty(ks)) continue;
                if (v is Sprite s)
                {
                    AddGlyphIf(ks[0], s);
                    any = true;
                }
            }
            return any;
        }

        private bool TryAddArrayByDefaultOrder(object value)
        {
            if (!(value is IList list)) return false;
            string order = "0123456789B,.EKMPTXYZ";
            bool any = false;
            for (int i = 0; i < list.Count && i < order.Length; i++)
            {
                if (list[i] is Sprite s)
                {
                    AddGlyphIf(order[i], s);
                    any = true;
                }
            }
            return any;
        }

        private void AddGlyphFromRect(char c, Texture2D tex, Rect rect, Vector2 size, float advance)
        {
            try
            {
                Sprite s = Sprite.Create(tex, rect, new Vector2(0.5f, 0.5f), spritePixelsPerUnit);
                s.name = "NumGlyph_" + SafeName(c);
                _glyphs[c] = new GlyphInfo { sprite = s, size = size, advance = advance > 0 ? advance : size.x };
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[RobustNumberRoller] 建立字元 {c} Sprite 失敗：{e.Message}", this);
            }
        }

        private void AddGlyphIf(char c, Sprite s)
        {
            if (s == null) return;
            _glyphs[c] = new GlyphInfo
            {
                sprite = s,
                size = new Vector2(s.rect.width, s.rect.height),
                advance = s.rect.width
            };
        }

        private void EnsureLayout()
        {
            if (imageRoot == null) return;
            HorizontalLayoutGroup layout = imageRoot.GetComponent<HorizontalLayoutGroup>();
            if (layout == null) layout = imageRoot.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.childAlignment = TextAnchor.MiddleCenter;
            layout.spacing = spacing;
            layout.childControlWidth = false;
            layout.childControlHeight = false;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
        }

        private void ClearChildren()
        {
            if (imageRoot == null) return;
            for (int i = imageRoot.childCount - 1; i >= 0; i--)
            {
                Transform child = imageRoot.GetChild(i);
                if (Application.isPlaying) Destroy(child.gameObject);
                else DestroyImmediate(child.gameObject);
            }
        }

        private void ResolveDirection(ref double from, ref double to)
        {
            if (countDirection == CountDirection.CountUp && to < from)
            {
                double tmp = from; from = to; to = tmp;
            }
            else if (countDirection == CountDirection.CountDown && to > from)
            {
                double tmp = from; from = to; to = tmp;
            }
        }

        private float ResolveDuration(double from, double to)
        {
            if (countMode == CountMode.DurationSmooth) return Mathf.Max(0.01f, duration);
            if (countMode == CountMode.UnitsPerSecond) return Mathf.Max(0.01f, (float)(Math.Abs(to - from) / Math.Max(0.01, unitsPerSecond)));
            return Mathf.Max(0.01f, (float)(Math.Abs(to - from) / Math.Max(0.0001, pointsPerTick)) * tickInterval);
        }

        private static int CountDigitsIn(string s)
        {
            int n = 0;
            foreach (char c in s) if (char.IsDigit(c)) n++;
            return n;
        }

        private static double Pow10(int p)
        {
            double v = 1.0;
            for (int i = 0; i < p; i++) v *= 10.0;
            return v;
        }

        private static int ReadInt(string line, string key, int fallback)
        {
            string token = key + "=";
            int start = line.IndexOf(token, StringComparison.Ordinal);
            if (start < 0) return fallback;
            start += token.Length;
            if (start < line.Length && line[start] == '"') start++;
            int end = start;
            while (end < line.Length && line[end] != ' ' && line[end] != '\t' && line[end] != '"') end++;
            return int.TryParse(line.Substring(start, end - start), NumberStyles.Integer, CultureInfo.InvariantCulture, out int v) ? v : fallback;
        }

        private static string SafeName(char c)
        {
            if (char.IsLetterOrDigit(c)) return c.ToString();
            if (c == ',') return "Comma";
            if (c == '.') return "Dot";
            if (c == '-') return "Minus";
            if (c == '+') return "Plus";
            if (c == '$') return "Dollar";
            return ((int)c).ToString(CultureInfo.InvariantCulture);
        }

#if UNITY_EDITOR
        [ContextMenu("從 UGUI_IMAGE 字典抽出到 Direct Sprites")]
        public void EditorPullUGUIImageTextFontToDirectSprites()
        {
            if (uguiImageTextFontObject == null)
            {
                Debug.LogWarning("[RobustNumberRoller] 請先把 UGUI_IMAGE Text Font prefab 或 component 拖到 uguiImageTextFontObject。", this);
                return;
            }

            Dictionary<char, Sprite> map = new Dictionary<char, Sprite>();
            EditorExtractSerializedObject(uguiImageTextFontObject, map, true);
            if (uguiImageTextFontObject is GameObject go)
            {
                foreach (Component c in go.GetComponentsInChildren<Component>(true))
                    if (c != null) EditorExtractSerializedObject(c, map, false);
            }

            for (int i = 0; i < 10; i++)
            {
                if (map.TryGetValue((char)('0' + i), out Sprite s)) digitSprites[i] = s;
            }
            if (map.TryGetValue(',', out Sprite comma)) commaSprite = comma;
            if (map.TryGetValue('.', out Sprite dot)) dotSprite = dot;
            if (map.TryGetValue('-', out Sprite minus)) minusSprite = minus;
            if (map.TryGetValue('+', out Sprite plus)) plusSprite = plus;
            if (map.TryGetValue('$', out Sprite dollar)) dollarSprite = dollar;

            extraSprites.Clear();
            foreach (KeyValuePair<char, Sprite> kv in map)
            {
                if (char.IsDigit(kv.Key) || kv.Key == ',' || kv.Key == '.' || kv.Key == '-' || kv.Key == '+' || kv.Key == '$') continue;
                extraSprites.Add(new CharSpritePair { character = kv.Key.ToString(), sprite = kv.Value });
            }

            glyphSource = GlyphSource.DirectSprites;
            EditorUtility.SetDirty(this);
            Debug.Log($"[RobustNumberRoller] 已抽出 {map.Count} 個字元。來源已切換成 DirectSprites。", this);
        }

        private static void EditorExtractSerializedObject(UnityEngine.Object obj, Dictionary<char, Sprite> map, bool allowGameObject)
        {
            if (obj == null) return;
            if (allowGameObject && obj is GameObject go)
            {
                foreach (Component c in go.GetComponentsInChildren<Component>(true))
                    if (c != null) EditorExtractSerializedObject(c, map, false);
                return;
            }

            SerializedObject so;
            try { so = new SerializedObject(obj); } catch { return; }

            SerializedProperty spriteArray = so.FindProperty("m_SpriteAry") ?? so.FindProperty("SpriteAry") ?? so.FindProperty("spriteAry") ?? so.FindProperty("m_Sprites");
            if (spriteArray != null && spriteArray.isArray)
            {
                string order = "0123456789B,.EKMPTXYZ";
                int n = Mathf.Min(spriteArray.arraySize, order.Length);
                for (int i = 0; i < n; i++)
                {
                    SerializedProperty element = spriteArray.GetArrayElementAtIndex(i);
                    Sprite s = element.objectReferenceValue as Sprite;
                    if (s != null) map[order[i]] = s;
                }
            }

            SerializedProperty keys = so.FindProperty("FontDictionary._Keys") ?? so.FindProperty("fontDictionary._Keys");
            SerializedProperty values = so.FindProperty("FontDictionary._Values") ?? so.FindProperty("fontDictionary._Values");
            if (keys != null && values != null && keys.isArray && values.isArray)
            {
                int n = Mathf.Min(keys.arraySize, values.arraySize);
                for (int i = 0; i < n; i++)
                {
                    string k = keys.GetArrayElementAtIndex(i).stringValue;
                    if (string.IsNullOrEmpty(k)) continue;
                    Sprite s = values.GetArrayElementAtIndex(i).objectReferenceValue as Sprite;
                    if (s != null) map[k[0]] = s;
                }
            }
        }
#endif
    }
}
