using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using IGS_GAME_EX;
using Spine.Unity;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public sealed class SpinePrefabBuilderWindow : EditorWindow
{
    private const float SampleRate = 60f;
    private const string DefaultSpineFolder = "Assets/ArkGame/ArkSlotGame/GameModule/UGUI_GAME/Game238_MoneyGone/Res/Prefabs/Spine";
    private const string DefaultPrefabFolder = "Assets/ArkGame/ArkSlotGame/GameModule/UGUI_GAME/Game238_MoneyGone/Res/Prefabs";
    private const string DefaultAnimationFolder = "Assets/ArkGame/ArkSlotGame/GameModule/UGUI_GAME/Game238_MoneyGone/Res/Animation";
    private const string SkeletonGraphicDefaultMaterialGuid = "b66cf7a186d13054989b33a5c90044e4";

    private DefaultAsset spineFolder;
    private DefaultAsset prefabOutputFolder;
    private DefaultAsset animationOutputFolder;
    private Material skeletonGraphicMaterial;
    private readonly List<DefaultAsset> ignoredFolders = new List<DefaultAsset>();
    private bool skipExistingPrefabs = true;
    private bool overwriteExisting = true;
    private bool recursive = true;
    [SerializeField] private string machineName = string.Empty;

    private static string MachineNamePreferenceKey => "SpinePrefabBuilder.MachineName." + Application.dataPath;

    [MenuItem("Tools/Spine/Spine Prefab Builder")]
    private static void Open()
    {
        var window = GetWindow<SpinePrefabBuilderWindow>("Spine Prefab Builder");
        window.minSize = new Vector2(520f, 500f);
        window.InitializeDefaults();
    }

    private void OnEnable()
    {
        machineName = EditorPrefs.GetString(MachineNamePreferenceKey, machineName ?? string.Empty);
        InitializeDefaults();
    }

    private void InitializeDefaults()
    {
        if (spineFolder == null)
            spineFolder = AssetDatabase.LoadAssetAtPath<DefaultAsset>(DefaultSpineFolder);
        if (prefabOutputFolder == null)
            prefabOutputFolder = AssetDatabase.LoadAssetAtPath<DefaultAsset>(DefaultPrefabFolder);
        if (animationOutputFolder == null)
            animationOutputFolder = AssetDatabase.LoadAssetAtPath<DefaultAsset>(DefaultAnimationFolder);
        if (skeletonGraphicMaterial == null)
            skeletonGraphicMaterial = LoadDefaultSkeletonGraphicMaterial();
    }

    private void OnGUI()
    {
        EditorGUILayout.LabelField("Build Spine Prefabs", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox(
            "Scans *_SkeletonData assets, creates a prefab, AnimatorController, and one AnimationClip per Spine animation. " +
            "Clip length is Max(Spine duration, 1 frame). Idle/Loop animations are marked loop.",
            MessageType.Info);

        spineFolder = (DefaultAsset)EditorGUILayout.ObjectField("Spine Folder", spineFolder, typeof(DefaultAsset), false);
        prefabOutputFolder = (DefaultAsset)EditorGUILayout.ObjectField("Prefab Output", prefabOutputFolder, typeof(DefaultAsset), false);
        animationOutputFolder = (DefaultAsset)EditorGUILayout.ObjectField("Animation Output", animationOutputFolder, typeof(DefaultAsset), false);
        EditorGUI.BeginChangeCheck();
        machineName = EditorGUILayout.TextField("Machine Name / 機種名", machineName);
        if (EditorGUI.EndChangeCheck())
            EditorPrefs.SetString(MachineNamePreferenceKey, machineName);
        bool validMachineName = true;
        try
        {
            string example = GetOutputBaseName("SpineName", machineName);
            EditorGUILayout.HelpBox($"檔名預覽：{example}.prefab / {example}_Idle.anim / {example}.controller\n留空維持原名；機種名與原名以 _ 分隔。Spine 動畫名稱與 Animator State 名稱不變。", MessageType.None);
        }
        catch (ArgumentException exception)
        {
            validMachineName = false;
            EditorGUILayout.HelpBox(exception.Message, MessageType.Error);
        }
        skeletonGraphicMaterial = (Material)EditorGUILayout.ObjectField("SkeletonGraphic Material", skeletonGraphicMaterial, typeof(Material), false);
        recursive = EditorGUILayout.ToggleLeft("Scan subfolders", recursive);
        skipExistingPrefabs = EditorGUILayout.ToggleLeft("Skip SkeletonData when prefab already exists", skipExistingPrefabs);
        overwriteExisting = EditorGUILayout.ToggleLeft("Overwrite generated assets when not skipped", overwriteExisting);

        DrawIgnoredFolders();

        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button("Use Selected Folder"))
                UseSelectedFolder();
            using (new EditorGUI.DisabledScope(!validMachineName))
            {
                if (GUILayout.Button("Build"))
                    BuildFromWindow();
            }
        }
    }

    private void UseSelectedFolder()
    {
        if (Selection.activeObject == null)
            return;

        string path = AssetDatabase.GetAssetPath(Selection.activeObject);
        if (AssetDatabase.IsValidFolder(path))
            spineFolder = Selection.activeObject as DefaultAsset;
    }

    private void BuildFromWindow()
    {
        try
        {
            string spineFolderPath = GetFolderPath(spineFolder, "Spine Folder");
            string prefabFolderPath = GetFolderPath(prefabOutputFolder, "Prefab Output");
            string animationFolderPath = GetFolderPath(animationOutputFolder, "Animation Output");
            var ignoredFolderPaths = GetIgnoredFolderPaths();

            if (skeletonGraphicMaterial == null)
                throw new InvalidOperationException("SkeletonGraphic Material is not assigned.");

            Build(spineFolderPath, prefabFolderPath, animationFolderPath, skeletonGraphicMaterial, recursive, ignoredFolderPaths, skipExistingPrefabs, overwriteExisting, machineName);
            EditorUtility.DisplayDialog("Spine Prefab Builder", "Build finished.", "OK");
        }
        catch (Exception exception)
        {
            Debug.LogException(exception);
            EditorUtility.DisplayDialog("Spine Prefab Builder", exception.Message, "OK");
        }
    }

    private void DrawIgnoredFolders()
    {
        EditorGUILayout.Space(8f);
        EditorGUILayout.LabelField("Ignored Folders", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox("SkeletonData assets under these folders will not be built.", MessageType.None);

        for (int i = 0; i < ignoredFolders.Count; i++)
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                ignoredFolders[i] = (DefaultAsset)EditorGUILayout.ObjectField(ignoredFolders[i], typeof(DefaultAsset), false);
                if (GUILayout.Button("Remove", GUILayout.Width(76f)))
                {
                    ignoredFolders.RemoveAt(i);
                    i--;
                }
            }
        }

        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button("Add Ignored Folder"))
                ignoredFolders.Add(null);
            if (GUILayout.Button("Add Selected Folder"))
                AddSelectedIgnoredFolder();
            if (GUILayout.Button("Clear"))
                ignoredFolders.Clear();
        }
    }

    private void AddSelectedIgnoredFolder()
    {
        if (Selection.activeObject == null)
            return;

        string path = AssetDatabase.GetAssetPath(Selection.activeObject);
        if (!AssetDatabase.IsValidFolder(path))
            return;

        var selectedFolder = Selection.activeObject as DefaultAsset;
        if (selectedFolder != null && !ignoredFolders.Contains(selectedFolder))
            ignoredFolders.Add(selectedFolder);
    }

    private static string GetFolderPath(DefaultAsset folder, string label)
    {
        if (folder == null)
            throw new InvalidOperationException($"{label} is not assigned.");

        string path = AssetDatabase.GetAssetPath(folder);
        if (!AssetDatabase.IsValidFolder(path))
            throw new InvalidOperationException($"{label} is not a valid project folder: {path}");
        return path;
    }

    private List<string> GetIgnoredFolderPaths()
    {
        var result = new List<string>();
        foreach (var folder in ignoredFolders)
        {
            if (folder == null)
                continue;

            string path = AssetDatabase.GetAssetPath(folder);
            if (!AssetDatabase.IsValidFolder(path))
                throw new InvalidOperationException($"Ignored Folder is not a valid project folder: {path}");

            result.Add(NormalizeAssetPath(path));
        }

        return result.Distinct(StringComparer.Ordinal).ToList();
    }

    private static Material LoadDefaultSkeletonGraphicMaterial()
    {
        string path = AssetDatabase.GUIDToAssetPath(SkeletonGraphicDefaultMaterialGuid);
        return string.IsNullOrEmpty(path) ? null : AssetDatabase.LoadAssetAtPath<Material>(path);
    }

    private static void Build(
        string spineFolderPath,
        string prefabFolderPath,
        string animationFolderPath,
        Material uiMaterial,
        bool scanRecursive,
        IReadOnlyList<string> ignoredFolderPaths,
        bool skipExistingPrefab,
        bool overwrite,
        string machineName = "")
    {
        // Validate before any assets are generated, including non-window callers.
        machineName = NormalizeMachineName(machineName);
        spineFolderPath = NormalizeAssetPath(spineFolderPath);
        string[] folders = { spineFolderPath };
        string[] guids = AssetDatabase.FindAssets("_SkeletonData", folders);
        var skeletonAssets = guids
            .Select(AssetDatabase.GUIDToAssetPath)
            .Select(NormalizeAssetPath)
            .Where(path => !IsInIgnoredFolder(path, ignoredFolderPaths))
            .Where(path => scanRecursive || NormalizeAssetPath(Path.GetDirectoryName(path)) == spineFolderPath)
            .Select(path => AssetDatabase.LoadAssetAtPath<SkeletonDataAsset>(path))
            .Where(asset => asset != null && asset.name.EndsWith("_SkeletonData", StringComparison.Ordinal))
            .OrderBy(asset => asset.name, StringComparer.Ordinal)
            .ToList();

        if (skeletonAssets.Count == 0)
            throw new InvalidOperationException($"No *_SkeletonData assets found under {spineFolderPath}.");

        int builtCount = 0;
        int skippedCount = 0;
        foreach (var skeletonDataAsset in skeletonAssets)
        {
            if (BuildOne(skeletonDataAsset, prefabFolderPath, animationFolderPath, uiMaterial, skipExistingPrefab, overwrite, machineName))
                builtCount++;
            else
                skippedCount++;
        }

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        Debug.Log($"Spine Prefab Builder finished. Built {builtCount} prefab(s), skipped {skippedCount} existing prefab(s).");
    }

    private static string NormalizeAssetPath(string path)
    {
        return string.IsNullOrEmpty(path) ? string.Empty : path.Replace('\\', '/').TrimEnd('/');
    }

    private static bool IsInIgnoredFolder(string assetPath, IReadOnlyList<string> ignoredFolderPaths)
    {
        for (int i = 0; i < ignoredFolderPaths.Count; i++)
        {
            string ignoredFolderPath = ignoredFolderPaths[i];
            if (assetPath.Equals(ignoredFolderPath, StringComparison.Ordinal)
                || assetPath.StartsWith(ignoredFolderPath + "/", StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    private static bool BuildOne(SkeletonDataAsset skeletonDataAsset, string prefabFolderPath, string animationFolderPath, Material uiMaterial, bool skipExistingPrefab, bool overwrite, string machineName = "")
    {
        string originalBaseName = GetBaseName(skeletonDataAsset.name);
        string baseName = GetOutputBaseName(originalBaseName, machineName);
        string prefabPath = $"{prefabFolderPath}/{baseName}.prefab";
        if (skipExistingPrefab && AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath) != null)
        {
            Debug.Log($"Skipped existing Spine prefab: {prefabPath}");
            return false;
        }

        var spineAnimations = ReadAnimations(skeletonDataAsset);
        if (spineAnimations.Count == 0)
            throw new InvalidOperationException($"{skeletonDataAsset.name} has no Spine animations.");

        var clips = new List<AnimationClip>(spineAnimations.Count);
        var stateNames = new List<string>(spineAnimations.Count);
        for (int i = 0; i < spineAnimations.Count; i++)
        {
            var info = spineAnimations[i];
            string clipName = $"{baseName}_{ToSafeAssetFileName(info.Name)}";
            string clipPath = $"{animationFolderPath}/{clipName}.anim";
            clips.Add(CreateOrUpdateClip(clipPath, clipName, info.Duration, i, info.IsLoop, overwrite));
            // State names are runtime lookup keys, not output filenames.
            stateNames.Add($"{originalBaseName}_{ToSafeAssetFileName(info.Name)}");
        }

        string controllerPath = $"{animationFolderPath}/{baseName}.controller";
        var controller = CreateOrUpdateController(controllerPath, baseName, clips, stateNames, overwrite);

        CreateOrUpdatePrefab(prefabPath, baseName, skeletonDataAsset, uiMaterial, controller, spineAnimations, overwrite);
        Debug.Log($"Built Spine prefab: {prefabPath} ({spineAnimations.Count} animation(s))");
        return true;
    }

    private static string GetBaseName(string skeletonDataName)
    {
        const string suffix = "_SkeletonData";
        return skeletonDataName.EndsWith(suffix, StringComparison.Ordinal)
            ? skeletonDataName.Substring(0, skeletonDataName.Length - suffix.Length)
            : skeletonDataName;
    }

    private static string NormalizeMachineName(string value)
    {
        string name = value ?? string.Empty;
        // Use the same restrictions on Windows and macOS; never turn a prefix into a path.
        const string invalidCharacters = "<>:\"/\\|?*";
        if (name.Any(character => char.IsControl(character) || invalidCharacters.IndexOf(character) >= 0))
            throw new ArgumentException("機種名不可包含換行或檔名禁用字元：< > : \" / \\ | ? *");
        return name.Trim();
    }

    private static string GetOutputBaseName(string originalBaseName, string machineName)
    {
        string prefix = NormalizeMachineName(machineName);
        if (prefix.Length == 0)
            return originalBaseName;
        return prefix + (prefix.EndsWith("_", StringComparison.Ordinal) ? string.Empty : "_") + originalBaseName;
    }

    private static string ToSafeAssetFileName(string value)
    {
        var invalidCharacters = Path.GetInvalidFileNameChars();
        var characters = value.Select(character => invalidCharacters.Contains(character) || character == '/' || character == '\\' ? '_' : character).ToArray();
        return new string(characters);
    }

    private static List<SpineAnimationInfo> ReadAnimations(SkeletonDataAsset skeletonDataAsset)
    {
        skeletonDataAsset.Clear();
        var skeletonData = skeletonDataAsset.GetSkeletonData(false);
        if (skeletonData == null)
            throw new InvalidOperationException($"Unable to load SkeletonData: {skeletonDataAsset.name}");

        var result = new List<SpineAnimationInfo>();
        foreach (var animation in skeletonData.Animations)
        {
            float duration = Mathf.Max(animation.Duration, 1f / SampleRate);
            result.Add(new SpineAnimationInfo(animation.Name, duration, IsLoopAnimation(animation.Name)));
        }
        return result;
    }

    private static bool IsLoopAnimation(string animationName)
    {
        return animationName.IndexOf("Idle", StringComparison.OrdinalIgnoreCase) >= 0
            || animationName.IndexOf("Loop", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    private static AnimationClip CreateOrUpdateClip(string path, string clipName, float duration, int eventIndex, bool loop, bool overwrite)
    {
        var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
        if (clip != null && !overwrite)
            throw new InvalidOperationException($"AnimationClip already exists: {path}");

        if (clip == null)
        {
            clip = new AnimationClip();
            AssetDatabase.CreateAsset(clip, path);
        }
        else
        {
            ClearClip(clip);
        }

        ApplyClipData(clip, clipName, duration, eventIndex, loop);
        SaveAndImportAsset(path, clip);

        clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
        if (!IsClipValid(clip, eventIndex))
        {
            ApplyClipData(clip, clipName, duration, eventIndex, loop);
            SaveAndImportAsset(path, clip);
            clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
        }

        if (!IsClipValid(clip, eventIndex))
            throw new InvalidOperationException($"AnimationClip was created but did not keep curves/events: {path}");

        return clip;
    }

    private static void ApplyClipData(AnimationClip clip, string clipName, float duration, int eventIndex, bool loop)
    {
        clip.name = clipName;
        clip.frameRate = SampleRate;
        clip.wrapMode = loop ? WrapMode.Loop : WrapMode.Default;

        var binding = CreateActiveBinding();
        var curve = AnimationCurve.Constant(0f, duration, 1f);
        AnimationUtility.SetEditorCurve(clip, binding, curve);
        AnimationUtility.SetAnimationEvents(clip, new[]
        {
            new AnimationEvent
            {
                time = 0f,
                functionName = "SetSpineAnimationCtrl",
                intParameter = eventIndex
            }
        });

        var settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.startTime = 0f;
        settings.stopTime = duration;
        settings.loopTime = loop;
        AnimationUtility.SetAnimationClipSettings(clip, settings);

        EditorUtility.SetDirty(clip);
    }

    private static EditorCurveBinding CreateActiveBinding()
    {
        var binding = new EditorCurveBinding
        {
            path = "UIRoot/New SkeletonGraphic",
            type = typeof(GameObject),
            propertyName = "m_IsActive"
        };
        return binding;
    }

    private static void SaveAndImportAsset(string path, UnityEngine.Object asset)
    {
        EditorUtility.SetDirty(asset);
        AssetDatabase.SaveAssets();
        AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
    }

    private static bool IsClipValid(AnimationClip clip, int eventIndex)
    {
        if (clip == null)
            return false;

        var curve = AnimationUtility.GetEditorCurve(clip, CreateActiveBinding());
        if (curve == null || curve.keys.Length < 2)
            return false;

        var events = AnimationUtility.GetAnimationEvents(clip);
        return events.Length == 1
            && events[0].functionName == "SetSpineAnimationCtrl"
            && events[0].intParameter == eventIndex;
    }

    private static void ClearClip(AnimationClip clip)
    {
        foreach (var binding in AnimationUtility.GetCurveBindings(clip))
            AnimationUtility.SetEditorCurve(clip, binding, null);
        foreach (var binding in AnimationUtility.GetObjectReferenceCurveBindings(clip))
            AnimationUtility.SetObjectReferenceCurve(clip, binding, null);
        AnimationUtility.SetAnimationEvents(clip, new AnimationEvent[0]);
    }

    private static AnimatorController CreateOrUpdateController(string path, string controllerName, IReadOnlyList<AnimationClip> clips, IReadOnlyList<string> stateNames, bool overwrite)
    {
        var existing = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
        if (existing != null)
        {
            if (!overwrite)
                throw new InvalidOperationException($"AnimatorController already exists: {path}");
            AssetDatabase.DeleteAsset(path);
        }

        var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
        controller.name = controllerName;
        var stateMachine = controller.layers[0].stateMachine;
        stateMachine.anyStatePosition = new Vector3(50f, 20f, 0f);
        stateMachine.entryPosition = new Vector3(50f, 120f, 0f);
        stateMachine.exitPosition = new Vector3(800f, 120f, 0f);
        stateMachine.parentStateMachinePosition = new Vector3(800f, 20f, 0f);

        for (int i = 0; i < clips.Count; i++)
        {
            var state = stateMachine.AddState(stateNames[i], new Vector3(20f, 200f + i * 90f, 0f));
            state.motion = clips[i];
            if (i == 0)
                stateMachine.defaultState = state;
        }

        EditorUtility.SetDirty(controller);
        return controller;
    }

    private static void CreateOrUpdatePrefab(
        string path,
        string baseName,
        SkeletonDataAsset skeletonDataAsset,
        Material uiMaterial,
        RuntimeAnimatorController controller,
        IReadOnlyList<SpineAnimationInfo> animations,
        bool overwrite)
    {
        if (!overwrite && AssetDatabase.LoadAssetAtPath<GameObject>(path) != null)
            throw new InvalidOperationException($"Prefab already exists: {path}");

        var root = new GameObject(baseName, typeof(RectTransform), typeof(Animator), typeof(SpineGraphicAnimationEventCtrl));
        try
        {
            root.layer = 5;
            SetupRectTransform(root.GetComponent<RectTransform>(), null);

            var animator = root.GetComponent<Animator>();
            animator.runtimeAnimatorController = controller;

            var uiRoot = new GameObject("UIRoot", typeof(RectTransform));
            uiRoot.layer = 5;
            uiRoot.transform.SetParent(root.transform, false);
            SetupRectTransform(uiRoot.GetComponent<RectTransform>(), root.GetComponent<RectTransform>());

            var spineObject = new GameObject("New SkeletonGraphic", typeof(RectTransform), typeof(CanvasRenderer), typeof(SkeletonGraphic), typeof(SpineGraphicCtrl));
            spineObject.layer = 0;
            spineObject.transform.SetParent(uiRoot.transform, false);
            SetupRectTransform(spineObject.GetComponent<RectTransform>(), uiRoot.GetComponent<RectTransform>());

            var skeletonGraphic = spineObject.GetComponent<SkeletonGraphic>();
            skeletonGraphic.skeletonDataAsset = skeletonDataAsset;
            skeletonGraphic.material = uiMaterial;
            skeletonGraphic.raycastTarget = true;

            var spineCtrl = spineObject.GetComponent<SpineGraphicCtrl>();
            SetSerializedObjectReference(spineCtrl, "m_TargetSpine", skeletonGraphic);
            SetSerializedBool(spineCtrl, "m_bOnEnableToPlay", true);
            SetSerializedFloat(spineCtrl, "m_TimeScale", 1f);

            var eventCtrl = root.GetComponent<SpineGraphicAnimationEventCtrl>();
            SetupEventInfo(eventCtrl, spineCtrl, animations);

            PrefabUtility.SaveAsPrefabAsset(root, path);
        }
        finally
        {
            DestroyImmediate(root);
        }
    }

    private static void SetupRectTransform(RectTransform rectTransform, RectTransform parent)
    {
        rectTransform.localScale = Vector3.one;
        rectTransform.localRotation = Quaternion.identity;
        rectTransform.anchorMin = new Vector2(0.5f, 0.5f);
        rectTransform.anchorMax = new Vector2(0.5f, 0.5f);
        rectTransform.anchoredPosition = Vector2.zero;
        rectTransform.sizeDelta = new Vector2(100f, 100f);
        rectTransform.pivot = new Vector2(0.5f, 0.5f);
        if (parent != null)
            rectTransform.SetParent(parent, false);
    }

    private static void SetupEventInfo(SpineGraphicAnimationEventCtrl eventCtrl, SpineGraphicCtrl spineCtrl, IReadOnlyList<SpineAnimationInfo> animations)
    {
        var serializedObject = new SerializedObject(eventCtrl);
        var array = serializedObject.FindProperty("spineAnimationCtrlInfoAry");
        array.arraySize = animations.Count;

        for (int i = 0; i < animations.Count; i++)
        {
            var element = array.GetArrayElementAtIndex(i);
            element.FindPropertyRelative("spineAnimationCtrl").objectReferenceValue = spineCtrl;
            element.FindPropertyRelative("animationName").stringValue = animations[i].Name;
            element.FindPropertyRelative("isLoop").boolValue = animations[i].IsLoop;
        }

        serializedObject.ApplyModifiedPropertiesWithoutUndo();
    }

    private static void SetSerializedObjectReference(UnityEngine.Object target, string fieldName, UnityEngine.Object value)
    {
        var serializedObject = new SerializedObject(target);
        serializedObject.FindProperty(fieldName).objectReferenceValue = value;
        serializedObject.ApplyModifiedPropertiesWithoutUndo();
    }

    private static void SetSerializedBool(UnityEngine.Object target, string fieldName, bool value)
    {
        var serializedObject = new SerializedObject(target);
        serializedObject.FindProperty(fieldName).boolValue = value;
        serializedObject.ApplyModifiedPropertiesWithoutUndo();
    }

    private static void SetSerializedFloat(UnityEngine.Object target, string fieldName, float value)
    {
        var serializedObject = new SerializedObject(target);
        serializedObject.FindProperty(fieldName).floatValue = value;
        serializedObject.ApplyModifiedPropertiesWithoutUndo();
    }

    private readonly struct SpineAnimationInfo
    {
        public readonly string Name;
        public readonly float Duration;
        public readonly bool IsLoop;

        public SpineAnimationInfo(string name, float duration, bool isLoop)
        {
            Name = name;
            Duration = duration;
            IsLoop = isLoop;
        }
    }
}
