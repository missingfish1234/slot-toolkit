using UnityEngine;
using UnityEngine.UI;
using Spine.Unity;

#if UNITY_EDITOR
using UnityEditor;
#endif

[ExecuteAlways]
[DisallowMultipleComponent]
[RequireComponent(typeof(SkeletonGraphic))]
public class SpineSkeletonGraphicMaskDriver : MonoBehaviour
{
    public enum MaskChannel
    {
        Alpha = 0,
        Red = 1,
        Green = 2,
        Blue = 3
    }

    [Header("遮罩設定")]
    public Texture2D maskTexture;
    public RectTransform maskRectTransform;

    [Header("遮罩通道")]
    public MaskChannel maskChannel = MaskChannel.Alpha;

    [Header("柔邊")]
    [Range(0f, 1f)]
    public float softness = 0f;

    [Header("反向遮罩")]
    public bool invertMask = false;

    [Header("限制在遮罩矩形內")]
    public bool useRectClamp = true;

    [Header("材質設定")]
    public Shader maskShader;

    private SkeletonGraphic skeletonGraphic;
    private Material runtimeMaterial;
    private Texture lastMainTexture;

    private static readonly int MainTexId = Shader.PropertyToID("_MainTex");
    private static readonly int MaskTexId = Shader.PropertyToID("_MaskTex");
    private static readonly int MaskRectId = Shader.PropertyToID("_MaskRect");
    private static readonly int MaskSoftnessId = Shader.PropertyToID("_MaskSoftness");
    private static readonly int MaskChannelId = Shader.PropertyToID("_MaskChannel");
    private static readonly int InvertMaskId = Shader.PropertyToID("_InvertMask");
    private static readonly int UseRectClampId = Shader.PropertyToID("_UseRectClamp");

    private readonly Vector3[] worldCorners = new Vector3[4];

    private void Reset()
    {
        skeletonGraphic = GetComponent<SkeletonGraphic>();

        if (maskShader == null)
            maskShader = Shader.Find("Custom/Spine/SkeletonGraphic Alpha Mask");
    }

    private void OnEnable()
    {
        skeletonGraphic = GetComponent<SkeletonGraphic>();

        if (maskShader == null)
            maskShader = Shader.Find("Custom/Spine/SkeletonGraphic Alpha Mask");

        CreateOrUpdateMaterial();
        ApplyMaterialToSkeletonGraphic();
        UpdateMaskProperties();
    }

    private void OnDisable()
    {
        if (skeletonGraphic != null)
        {
            skeletonGraphic.material = null;
            skeletonGraphic.SetMaterialDirty();
        }

        DestroyRuntimeMaterial();
    }

    private void OnDestroy()
    {
        DestroyRuntimeMaterial();
    }

    private void LateUpdate()
    {
        if (skeletonGraphic == null)
            skeletonGraphic = GetComponent<SkeletonGraphic>();

        if (maskShader == null)
            maskShader = Shader.Find("Custom/Spine/SkeletonGraphic Alpha Mask");

        CreateOrUpdateMaterial();
        ApplyMaterialToSkeletonGraphic();
        UpdateMaskProperties();
    }

#if UNITY_EDITOR
    private void OnValidate()
    {
        if (!Application.isPlaying)
        {
            skeletonGraphic = GetComponent<SkeletonGraphic>();

            if (maskShader == null)
                maskShader = Shader.Find("Custom/Spine/SkeletonGraphic Alpha Mask");

            EditorApplication.delayCall += () =>
            {
                if (this == null)
                    return;

                CreateOrUpdateMaterial();
                ApplyMaterialToSkeletonGraphic();
                UpdateMaskProperties();

                if (skeletonGraphic != null)
                    skeletonGraphic.SetMaterialDirty();
            };
        }
    }
#endif

    private void CreateOrUpdateMaterial()
    {
        if (maskShader == null || skeletonGraphic == null)
            return;

        Texture currentMainTexture = null;

        if (skeletonGraphic.mainTexture != null)
            currentMainTexture = skeletonGraphic.mainTexture;

        bool needCreate =
            runtimeMaterial == null ||
            runtimeMaterial.shader != maskShader ||
            currentMainTexture != lastMainTexture;

        if (!needCreate)
            return;

        DestroyRuntimeMaterial();

        runtimeMaterial = new Material(maskShader)
        {
            name = $"{gameObject.name}_SpineSkeletonGraphicMask_RuntimeMaterial",
            hideFlags = HideFlags.DontSave
        };

        if (currentMainTexture != null)
        {
            runtimeMaterial.SetTexture(MainTexId, currentMainTexture);
            lastMainTexture = currentMainTexture;
        }
    }

    private void ApplyMaterialToSkeletonGraphic()
    {
        if (skeletonGraphic == null || runtimeMaterial == null)
            return;

        if (skeletonGraphic.material != runtimeMaterial)
        {
            skeletonGraphic.material = runtimeMaterial;
            skeletonGraphic.SetMaterialDirty();
        }
    }

    private void UpdateMaskProperties()
    {
        if (runtimeMaterial == null)
            return;

        if (maskTexture != null)
            runtimeMaterial.SetTexture(MaskTexId, maskTexture);

        runtimeMaterial.SetFloat(MaskSoftnessId, softness);
        runtimeMaterial.SetFloat(MaskChannelId, (float)maskChannel);
        runtimeMaterial.SetFloat(InvertMaskId, invertMask ? 1f : 0f);
        runtimeMaterial.SetFloat(UseRectClampId, useRectClamp ? 1f : 0f);

        Vector4 localMaskRect = CalculateMaskRectInTargetLocalSpace();
        runtimeMaterial.SetVector(MaskRectId, localMaskRect);
    }

    private Vector4 CalculateMaskRectInTargetLocalSpace()
    {
        if (maskRectTransform == null)
        {
            RectTransform selfRect = transform as RectTransform;

            if (selfRect != null)
            {
                Rect rect = selfRect.rect;
                return new Vector4(rect.xMin, rect.yMin, rect.width, rect.height);
            }

            return new Vector4(-100f, -100f, 200f, 200f);
        }

        maskRectTransform.GetWorldCorners(worldCorners);

        Vector3 local0 = transform.InverseTransformPoint(worldCorners[0]);
        Vector3 local1 = transform.InverseTransformPoint(worldCorners[1]);
        Vector3 local2 = transform.InverseTransformPoint(worldCorners[2]);
        Vector3 local3 = transform.InverseTransformPoint(worldCorners[3]);

        float minX = Mathf.Min(local0.x, local1.x, local2.x, local3.x);
        float maxX = Mathf.Max(local0.x, local1.x, local2.x, local3.x);
        float minY = Mathf.Min(local0.y, local1.y, local2.y, local3.y);
        float maxY = Mathf.Max(local0.y, local1.y, local2.y, local3.y);

        float width = Mathf.Max(0.0001f, maxX - minX);
        float height = Mathf.Max(0.0001f, maxY - minY);

        return new Vector4(minX, minY, width, height);
    }

    private void DestroyRuntimeMaterial()
    {
        if (runtimeMaterial == null)
            return;

        if (Application.isPlaying)
            Destroy(runtimeMaterial);
        else
            DestroyImmediate(runtimeMaterial);

        runtimeMaterial = null;
        lastMainTexture = null;
    }
}