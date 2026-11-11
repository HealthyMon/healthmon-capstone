using UnityEngine;

/// <summary>
/// Switch between the existing AR rig and the new non-AR 3D Home.
/// Attach beside UIManager on Managers/UIMaanger.
/// </summary>
public sealed class HealthMonViewModeController : MonoBehaviour
{
    [Header("3D Home")]
    [SerializeField] private GameObject homeWorld;
    [SerializeField] private Camera homeCamera;

    [Header("Existing AR Rig")]
    [SerializeField] private GameObject arRoot;
    [SerializeField] private ARPlacementManager arPlacement;

    public void ShowHomeWorld()
    {
        arPlacement?.SetARMode(false);
        if (arRoot != null) arRoot.SetActive(false);
        if (homeWorld != null) homeWorld.SetActive(true);
        if (homeCamera != null) homeCamera.gameObject.SetActive(true);
    }

    public void ShowARWorld(bool petPlacementEnabled)
    {
        if (homeWorld != null) homeWorld.SetActive(false);
        if (homeCamera != null) homeCamera.gameObject.SetActive(false);
        if (arRoot != null) arRoot.SetActive(true);
        arPlacement?.SetARMode(petPlacementEnabled);
    }
}
