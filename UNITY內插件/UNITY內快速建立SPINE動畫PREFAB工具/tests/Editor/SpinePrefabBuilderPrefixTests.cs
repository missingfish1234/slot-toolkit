using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Spine.Unity;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

// Run only in a disposable Unity project with this tool and its dependencies installed.
// Unity -batchmode -nographics -projectPath <project> -executeMethod SpinePrefabBuilderPrefixTests.Run
public static class SpinePrefabBuilderPrefixTests
{
    private static int assertions;

    public static void Run()
    {
        try
        {
            Check(Name("Hero", "") == "Hero", "Empty prefix preserves legacy name");
            Check(Name("Hero", null) == "Hero", "Null prefix preserves legacy name");
            Check(Name("Hero", "   ") == "Hero", "Blank prefix preserves legacy name");
            Check(Name("Hero", " Game238_MoneyGone ") == "Game238_MoneyGone_Hero", "Trim and separator");
            Check(Name("Hero", "Game238_") == "Game238_Hero", "No extra separator");
            Check(Name("Hero", "機種甲") == "機種甲_Hero", "Unicode prefix");
            foreach (char invalid in "<>:\"/\\|?*\r\n\t")
            {
                bool rejected = false;
                try { Name("Hero", "Game" + invalid); }
                catch (ArgumentException) { rejected = true; }
                Check(rejected, "Reject invalid prefix character " + (int)invalid);
            }

            string root = "Assets/PrefixQA_" + Guid.NewGuid().ToString("N");
            AssetDatabase.CreateFolder("Assets", Path.GetFileName(root));
            foreach (string folder in new[] { "Source", "Prefabs", "Animation" })
                AssetDatabase.CreateFolder(root, folder);
            var json = new TextAsset("{\"skeleton\":{\"hash\":\"prefix-qa\",\"spine\":\"4.2.0\"},\"bones\":[{\"name\":\"root\"}],\"animations\":{\"Idle\":{},\"Win\":{}}}");
            AssetDatabase.CreateAsset(json, root + "/Source/HeroJson.asset");
            var skeleton = ScriptableObject.CreateInstance<SkeletonDataAsset>();
            skeleton.skeletonJSON = json;
            AssetDatabase.CreateAsset(skeleton, root + "/Source/Hero_SkeletonData.asset");
            var material = new Material(Shader.Find("UI/Default"));
            AssetDatabase.CreateAsset(material, root + "/Source/UI.mat");
            AssetDatabase.SaveAssets();

            Build(root, material, "", true, true);
            VerifyOutputs(root, "Hero", skeleton);
            string oldGuid = AssetDatabase.AssetPathToGUID(root + "/Prefabs/Hero.prefab");
            Build(root, material, "Game238_MoneyGone", true, true);
            VerifyOutputs(root, "Game238_MoneyGone_Hero", skeleton);
            Check(AssetDatabase.AssetPathToGUID(root + "/Prefabs/Hero.prefab") == oldGuid, "Original prefab preserved");
            var data = new FileInfo(root + "/Animation/Game238_MoneyGone_Hero_Idle.anim");
            DateTime beforeSkip = data.LastWriteTimeUtc;
            Build(root, material, "Game238_MoneyGone", true, false);
            Check(new FileInfo(data.FullName).LastWriteTimeUtc == beforeSkip, "Skip uses prefixed path");
            Build(root, material, "Game238_MoneyGone", false, true);
            VerifyOutputs(root, "Game238_MoneyGone_Hero", skeleton);
            Build(root, material, "機種乙_", true, true);
            VerifyOutputs(root, "機種乙_Hero", skeleton);
            Check(AssetDatabase.FindAssets("t:Prefab", new[] { root + "/Prefabs" }).Length == 3, "Different prefixes coexist");
            int fileCount = Directory.GetFiles(root, "*", SearchOption.AllDirectories).Length;
            bool invalidBuildRejected = false;
            try { Build(root, material, "../Bad", false, true); }
            catch (ArgumentException) { invalidBuildRejected = true; }
            Check(invalidBuildRejected && Directory.GetFiles(root, "*", SearchOption.AllDirectories).Length == fileCount, "Invalid prefix fails before writing");

            var flags = BindingFlags.NonPublic | BindingFlags.Static;
            string key = (string)typeof(SpinePrefabBuilderWindow).GetProperty("MachineNamePreferenceKey", flags).GetValue(null);
            Check(key.EndsWith(Application.dataPath, StringComparison.Ordinal), "Preference is scoped to this project");
            bool hadKey = EditorPrefs.HasKey(key);
            string oldValue = EditorPrefs.GetString(key, "");
            SpinePrefabBuilderWindow window = null;
            try
            {
                EditorPrefs.SetString(key, "SavedGame");
                window = ScriptableObject.CreateInstance<SpinePrefabBuilderWindow>();
                Check((string)typeof(SpinePrefabBuilderWindow).GetField("machineName", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(window) == "SavedGame", "Reopened window loads saved prefix");
            }
            finally
            {
                if (window != null) UnityEngine.Object.DestroyImmediate(window);
                if (hadKey) EditorPrefs.SetString(key, oldValue); else EditorPrefs.DeleteKey(key);
            }
            Debug.Log("PREFIX_QA_PASS assertions=" + assertions + " outputs=" + root);
            EditorApplication.Exit(0);
        }
        catch (Exception exception)
        {
            Debug.LogException(exception);
            EditorApplication.Exit(1);
        }
    }

    private static object Invoke(string method, params object[] args)
    {
        try { return typeof(SpinePrefabBuilderWindow).GetMethod(method, BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, args); }
        catch (TargetInvocationException exception) { throw exception.InnerException ?? exception; }
    }

    private static string Name(string original, string prefix) => (string)Invoke("GetOutputBaseName", original, prefix);

    private static void Build(string root, Material material, string prefix, bool skip, bool overwrite)
    {
        Invoke("Build", root + "/Source", root + "/Prefabs", root + "/Animation", material, true, new string[0], skip, overwrite, prefix);
    }

    private static void VerifyOutputs(string root, string name, SkeletonDataAsset skeleton)
    {
        // Verify the saved prefab after import, not a cached object from a previous overwrite.
        AssetDatabase.ImportAsset(root + "/Prefabs/" + name + ".prefab", ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(root + "/Prefabs/" + name + ".prefab");
        var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(root + "/Animation/" + name + ".controller");
        Check(prefab != null && prefab.name == name, "Prefab name " + name);
        Check(controller != null && prefab.GetComponent<Animator>().runtimeAnimatorController == controller, "Controller reference " + name);
        Check(prefab.GetComponentInChildren<SkeletonGraphic>().skeletonDataAsset == skeleton, "Source reference unchanged");
        var states = controller.layers[0].stateMachine.states;
        Check(states.Length == 2, "Two Animator states");
        var eventComponent = prefab.GetComponent("SpineGraphicAnimationEventCtrl");
        var entries = new SerializedObject(eventComponent).FindProperty("spineAnimationCtrlInfoAry");
        Check(entries.arraySize == 2, "Two original event entries");
        for (int i = 0; i < 2; i++)
        {
            string animation = i == 0 ? "Idle" : "Win";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(root + "/Animation/" + name + "_" + animation + ".anim");
            Check(clip != null && clip.name == name + "_" + animation, "Clip output name");
            Check(states[i].state.name == "Hero_" + animation && states[i].state.motion == clip, "Legacy state name and new clip link");
            var events = AnimationUtility.GetAnimationEvents(clip);
            Check(events.Length == 1 && events[0].intParameter == i && events[0].functionName == "SetSpineAnimationCtrl", "Event index unchanged");
            Check(entries.GetArrayElementAtIndex(i).FindPropertyRelative("animationName").stringValue == animation, "Spine animation name unchanged");
            Check(AnimationUtility.GetAnimationClipSettings(clip).loopTime == (i == 0), "Loop flag unchanged");
            Check(AnimationUtility.GetCurveBindings(clip).Any(binding => binding.path == "UIRoot/New SkeletonGraphic"), "Curve binding unchanged");
        }
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception("Prefix QA failed: " + message);
        assertions++;
    }
}
