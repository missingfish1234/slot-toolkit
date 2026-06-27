using UnityEngine;
using UnityEngine.UI;

[DisallowMultipleComponent]
[RequireComponent(typeof(Graphic))]
public class ArkDissolveAutoPlayOnEnable : MonoBehaviour
{
    [SerializeField]
    private bool instanceMaterialOnAwake = true;

    [SerializeField]
    private bool forceAutoDissolve = true;

    [SerializeField]
    private bool resetDissolveAmount = true;

    private static readonly int ID_DissolveStartTime = Shader.PropertyToID("_DissolveStartTime");
    private static readonly int ID_AutoDissolve = Shader.PropertyToID("_AutoDissolve");
    private static readonly int ID_DissolveAmount = Shader.PropertyToID("_DissolveAmount");

    private Graphic m_Graphic;
    private Material m_RuntimeMaterial;

    private void Awake()
    {
        m_Graphic = GetComponent<Graphic>();
        EnsureRuntimeMaterial();
    }

    private void OnEnable()
    {
        RestartDissolve();
    }

    private void OnDestroy()
    {
        if (Application.isPlaying && m_RuntimeMaterial != null)
        {
            Destroy(m_RuntimeMaterial);
        }
    }

    public void RestartDissolve()
    {
        if (m_Graphic == null)
        {
            m_Graphic = GetComponent<Graphic>();
        }

        EnsureRuntimeMaterial();

        Material material = m_Graphic != null ? m_Graphic.material : null;
        if (material == null)
        {
            return;
        }

        if (material.HasProperty(ID_DissolveStartTime))
        {
            material.SetFloat(ID_DissolveStartTime, Time.timeSinceLevelLoad);
        }

        if (forceAutoDissolve && material.HasProperty(ID_AutoDissolve))
        {
            material.SetFloat(ID_AutoDissolve, 1f);
        }

        if (resetDissolveAmount && material.HasProperty(ID_DissolveAmount))
        {
            material.SetFloat(ID_DissolveAmount, 0f);
        }
    }

    private void EnsureRuntimeMaterial()
    {
        if (!Application.isPlaying || !instanceMaterialOnAwake || m_RuntimeMaterial != null || m_Graphic == null || m_Graphic.material == null)
        {
            return;
        }

        m_RuntimeMaterial = new Material(m_Graphic.material);
        m_RuntimeMaterial.name = m_Graphic.material.name + " (Instance)";
        m_Graphic.material = m_RuntimeMaterial;
    }
}
