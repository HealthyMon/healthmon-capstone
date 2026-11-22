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
    private Transform petAnchor;
    private int fittedWidth, fittedHeight, fittedChildren;
    private int fittedRenderers;
    private float nextFitCheck;

    private void LateUpdate()
    {
        if (homeWorld == null || !homeWorld.activeInHierarchy || homeCamera == null) return;
        if (petAnchor == null)
            foreach (var child in homeWorld.GetComponentsInChildren<Transform>(true))
                if (child.name == "HomePetAnchor") { petAnchor = child; break; }
        if (petAnchor == null) return;
        if (Time.unscaledTime < nextFitCheck && fittedWidth == Screen.width && fittedHeight == Screen.height) return;
        nextFitCheck = Time.unscaledTime + .25f;
        var renderers = petAnchor.GetComponentsInChildren<Renderer>();
        int signature = 17;
        foreach (var renderer in renderers)
            if (renderer.enabled) unchecked { signature = signature * 31 + renderer.GetInstanceID(); }
        if (fittedWidth == Screen.width && fittedHeight == Screen.height && fittedChildren == petAnchor.childCount && fittedRenderers == signature) return;
        bool found = false; var bounds = new Bounds();
        foreach (var renderer in renderers)
        {
            if (!renderer.enabled) continue;
            if (!found) { bounds = renderer.bounds; found = true; } else bounds.Encapsulate(renderer.bounds);
        }
        if (!found) return;
        Vector2 min = Vector2.one * float.PositiveInfinity, max = -min;
        for (int i = 0; i < 8; i++)
        {
            var point = bounds.center + Vector3.Scale(bounds.extents, new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1));
            var screen = (Vector2)homeCamera.WorldToViewportPoint(point);
            min = Vector2.Min(min, screen); max = Vector2.Max(max, screen);
        }
        float scale = Mathf.Min(.68f / Mathf.Max(.01f, max.x-min.x), .29f / Mathf.Max(.01f, max.y-min.y));
        var localCenter = petAnchor.InverseTransformPoint(bounds.center);
        petAnchor.localScale *= scale;
        var center = petAnchor.TransformPoint(localCenter);
        float depth = homeCamera.WorldToViewportPoint(center).z;
        petAnchor.position += homeCamera.ViewportToWorldPoint(new Vector3(.5f, .50f, depth)) - center;
        fittedWidth = Screen.width; fittedHeight = Screen.height; fittedChildren = petAnchor.childCount;
        fittedRenderers = signature;
    }

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
