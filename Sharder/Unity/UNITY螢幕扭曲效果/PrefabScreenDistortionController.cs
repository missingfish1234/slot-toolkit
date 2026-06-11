using UnityEngine;

[ExecuteAlways]
public class PrefabScreenDistortionController : MonoBehaviour
{
    [Header("目標")]
    public Camera targetCamera;
    public Renderer targetRenderer;

    [Header("扭曲參數")]
    [Range(-1f, 1f)]
    public float strength = 0.25f;

    [Range(0.01f, 1f)]
    public float radius = 0.25f;

    [Range(0.001f, 0.5f)]
    public float feather = 0.08f;

    [Range(0f, 1f)]
    public float opacity = 1f;

    private MaterialPropertyBlock mpb;

    private static readonly int CenterID = Shader.PropertyToID("_Center");
    private static readonly int StrengthID = Shader.PropertyToID("_Strength");
    private static readonly int RadiusID = Shader.PropertyToID("_Radius");
    private static readonly int FeatherID = Shader.PropertyToID("_Feather");
    private static readonly int OpacityID = Shader.PropertyToID("_Opacity");

    private void Reset()
    {
        targetRenderer = GetComponent<Renderer>();
        targetCamera = Camera.main;
    }

    private void LateUpdate()
    {
        if (targetCamera == null)
            targetCamera = Camera.main;

        if (targetRenderer == null)
            targetRenderer = GetComponent<Renderer>();

        if (targetCamera == null || targetRenderer == null)
            return;

        if (mpb == null)
            mpb = new MaterialPropertyBlock();

        Vector3 viewportPos = targetCamera.WorldToViewportPoint(transform.position);

        targetRenderer.GetPropertyBlock(mpb);

        mpb.SetVector(CenterID, new Vector4(viewportPos.x, viewportPos.y, 0, 0));
        mpb.SetFloat(StrengthID, strength);
        mpb.SetFloat(RadiusID, radius);
        mpb.SetFloat(FeatherID, feather);
        mpb.SetFloat(OpacityID, opacity);

        targetRenderer.SetPropertyBlock(mpb);
    }
}