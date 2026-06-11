#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

namespace SlotTools.NumberRoller.EditorTools
{
    [CustomEditor(typeof(RobustNumberRoller))]
    public class RobustNumberRollerEditor : Editor
    {
        public override void OnInspectorGUI()
        {
            RobustNumberRoller r = (RobustNumberRoller)target;

            EditorGUILayout.Space(6);
            EditorGUILayout.HelpBox("v4 重點：可讀 UGUI_IMAGE Text Font prefab/component；ImageOdometer 可用目前分數逐位滾動，適合一分一分快速滾上去。", MessageType.Info);

            DrawDefaultInspector();

            EditorGUILayout.Space(10);
            EditorGUILayout.LabelField("快速操作", EditorStyles.boldLabel);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("自動綁定"))
                {
                    Undo.RecordObject(r, "Auto Bind Number Roller");
                    r.AutoBind();
                    EditorUtility.SetDirty(r);
                }
                if (GUILayout.Button("重建顯示"))
                {
                    r.RebuildDisplay();
                    EditorUtility.SetDirty(r);
                }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("播放滾分"))
                {
                    if (Application.isPlaying) r.Play();
                    else
                    {
                        r.RebuildDisplay();
                        r.SetImmediate(r.startValue);
                        Debug.Log("請進入 Play Mode 後播放滾分；Edit Mode 目前只重建並顯示起始值。", r);
                    }
                }
                if (GUILayout.Button("停止在目標"))
                {
                    r.StopAtTarget();
                }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("顯示起始值")) r.SetImmediate(r.startValue);
                if (GUILayout.Button("顯示目標值")) r.SetImmediate(r.targetValue);
            }

            EditorGUILayout.Space(8);
            if (GUILayout.Button("從 UGUI_IMAGE 字典抽出到 Direct Sprites"))
            {
                Undo.RecordObject(r, "Pull UGUI Image Font Sprites");
                r.EditorPullUGUIImageTextFontToDirectSprites();
                EditorUtility.SetDirty(r);
            }

            if (GUILayout.Button("列出缺字報告"))
            {
                Debug.Log(r.GetMissingGlyphReport(), r);
            }

            EditorGUILayout.Space(6);
            EditorGUILayout.HelpBox("建議測試設定：Display Mode=ImageOdometer、Glyph Source=UGUIImageTextFontPrefab、Count Mode=StepPerTick、Points Per Tick=1、Tick Interval=0.005~0.02、Odometer Follows Current Value=開。", MessageType.None);
        }
    }
}
#endif
