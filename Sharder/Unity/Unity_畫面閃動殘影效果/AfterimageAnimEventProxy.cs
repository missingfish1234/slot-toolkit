using UnityEngine;

public class AfterimageAnimEventProxy : MonoBehaviour
{
    public void Anim_PlayPresetSequence()
    {
        if (AfterimageEffectController.Instance != null)
            AfterimageEffectController.Instance.PlayPresetSequence();
    }

    public void Anim_StopAfterimage()
    {
        if (AfterimageEffectController.Instance != null)
            AfterimageEffectController.Instance.Stop();
    }
}