using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using SlotTools.NumberRoller;

public static class ToolkitEngineQA
{
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    public static void RunPlay()
    {
        EditorSettings.enterPlayModeOptionsEnabled = true;
        EditorSettings.enterPlayModeOptions = EnterPlayModeOptions.DisableDomainReload | EnterPlayModeOptions.DisableSceneReload;
        EditorApplication.playModeStateChanged += StartPlayTests;
        EditorApplication.isPlaying = true;
    }
    private static void StartPlayTests(PlayModeStateChange state)
    {
        if (state != PlayModeStateChange.EnteredPlayMode) return;
        EditorApplication.playModeStateChanged -= StartPlayTests;
        new GameObject("IsolatedPlayQA").AddComponent<ToolkitPlayQARunner>();
    }
    public static void Run()
    {
        try
        {
            TestRoller();
            TestMask();
            TestUvChannels();
            var shaders = AssetDatabase.FindAssets("t:Shader", new[] {"Assets/Tools"});
            foreach (var guid in shaders)
            {
                var shader = AssetDatabase.LoadAssetAtPath<Shader>(AssetDatabase.GUIDToAssetPath(guid));
                var errors = ShaderUtil.GetShaderMessages(shader).Where(x => x.severity.ToString() == "Error").ToArray();
                Check(errors.Length == 0, shader.name + ": " + string.Join("; ", errors.Select(x => x.message)));
            }
            Debug.Log("TOOLKIT_QA_PASS: ImageLine 10000 updates stable glyph IDs and bounded nodes; source replacement cleanup; user-child preservation; mask restore/rotation; UV channels; " + shaders.Length + " shaders imported without errors.");
            EditorApplication.Exit(0);
        }
        catch(Exception error) { Debug.LogException(error); EditorApplication.Exit(1); }
    }

    private static void TestRoller()
    {
        var go = new GameObject("RollerQA", typeof(RectTransform));
        var root = new GameObject("ImageRoot", typeof(RectTransform)); root.transform.SetParent(go.transform, false);
        var user = new GameObject("UserDecoration"); user.transform.SetParent(root.transform, false);
        var roller = go.AddComponent<RobustNumberRoller>();
        roller.imageRoot = root.GetComponent<RectTransform>(); roller.displayMode = RobustNumberRoller.DisplayMode.ImageLine;
        roller.glyphSource = RobustNumberRoller.GlyphSource.BMFontFntTexture; roller.useThousandsSeparator=false;
        var texture = new Texture2D(100,10); roller.bmFontTexture = texture;
        var font = new TextAsset(string.Join("\n",Enumerable.Range(0,10).Select(x => "char id="+(48+x)+" x="+(x*10)+" y=0 width=10 height=10 xadvance=10"))); roller.bmFontText=font;
        roller.RebuildDisplay();
        var field=typeof(RobustNumberRoller).GetField("_ownedSprites",BindingFlags.NonPublic|BindingFlags.Instance);
        var sprites=((IEnumerable)field.GetValue(roller)).Cast<Sprite>().ToArray(); Check(sprites.Length==10,"Expected ten owned glyph sprites");
        for(int i=0;i<10000;i++)roller.SetImmediate(i);
        var current=((IEnumerable)field.GetValue(roller)).Cast<Sprite>().ToArray();
        Check(current.SequenceEqual(sprites),"Glyphs recreated while values changed");
        Check(root.transform.childCount<=5,"ImageLine nodes grew during roll"); Check(user!=null,"User child removed");
        var old=sprites[0]; roller.bmFontText=new TextAsset(font.text); roller.RebuildDisplay();
        Check(old==null,"Old owned sprite not destroyed on rebuild"); Check(user!=null,"User child removed on rebuild");
        var owned=((IEnumerable)field.GetValue(roller)).Cast<Sprite>().ToArray();
        UnityEngine.Object.DestroyImmediate(go); Check(owned.All(x=>x==null),"Owned sprite not destroyed with owner");
        UnityEngine.Object.DestroyImmediate(texture); UnityEngine.Object.DestroyImmediate(font);
    }

    private static void TestMask()
    {
        var go=new GameObject("MaskQA",typeof(RectTransform));
        var graphic=go.AddComponent<Spine.Unity.SkeletonGraphic>();
        var original=new Material(Shader.Find("UI/Default")); graphic.material=original;
        var driver=go.AddComponent<SpineSkeletonGraphicMaskDriver>();
        var mask=new GameObject("MaskRectQA",typeof(RectTransform)); var rect=mask.GetComponent<RectTransform>();
        rect.sizeDelta=new Vector2(100,80); rect.rotation=Quaternion.Euler(0,0,45); driver.maskRectTransform=rect;
        typeof(SpineSkeletonGraphicMaskDriver).GetMethod("LateUpdate",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(driver,null);
        var matrix=graphic.material.GetMatrix("_MaskTransform");
        Check(Mathf.Abs(matrix.m01)>0.5f,"Mask rotation matrix not applied");
        driver.enabled=false; Check(graphic.material==original,"Original mask material not restored");
        UnityEngine.Object.DestroyImmediate(go);UnityEngine.Object.DestroyImmediate(mask);UnityEngine.Object.DestroyImmediate(original);
    }

    private static void TestUvChannels()
    {
        var canvasGo=new GameObject("CanvasQA",typeof(Canvas));
        var go=new GameObject("ImageQA",typeof(RectTransform),typeof(Image));go.transform.SetParent(canvasGo.transform,false);
        go.AddComponent<BMFontUv2Filler>();
        var channels=canvasGo.GetComponent<Canvas>().additionalShaderChannels;
        Check((channels&AdditionalCanvasShaderChannels.TexCoord1)!=0 && (channels&AdditionalCanvasShaderChannels.TexCoord2)!=0,"Missing UV channels");
        UnityEngine.Object.DestroyImmediate(canvasGo);
    }
}

public class ToolkitPlayQARunner : MonoBehaviour
{
    private IEnumerator Start()
    {
        var go = new GameObject("DissolveQA", typeof(RectTransform), typeof(Image));
        var graphic = go.GetComponent<Image>();
        var original = new Material(Shader.Find("ArkGame/UI-Spine/Dissolve Multi Mode")); graphic.material = original;
        var controller = go.AddComponent<ArkDissolveController>(); controller.targetMaterial = original; controller.Apply();
        for (int i = 0; i < 100; i++)
        {
            var instance = graphic.material;
            if (!Check(instance != original, "Dissolve failed to isolate explicit shared material")) yield break;
            controller.dissolveAmount = .7f; controller.Apply();
            if (!Check(Mathf.Abs(original.GetFloat("_DissolveAmount")) < .0001f, "Dissolve changed original material")) yield break;
            controller.enabled = false; controller.Apply();
            if (!Check(graphic.material == original, "Dissolve disable failed to restore original")) yield break;
            yield return null;
            if (!Check(instance == null, "Dissolve leaked instance after disable")) yield break;
            controller.enabled = true;
        }
        var external = new Material(original); graphic.material = external;
        controller.enabled = false;
        if (!Check(graphic.material == external, "Dissolve overwrote external material reassignment")) yield break;
        Destroy(go); Destroy(original); Destroy(external);
        yield return null;
        Debug.Log("TOOLKIT_PLAY_QA_PASS: 100 real Play Mode dissolve enable/disable cycles, isolated shared material, cleanup, disabled Apply, external reassignment preservation.");
        EditorApplication.Exit(0);
    }
    private bool Check(bool condition, string message)
    {
        if (condition) return true;
        Debug.LogError("TOOLKIT_PLAY_QA_FAIL: " + message); EditorApplication.Exit(1); return false;
    }
}
