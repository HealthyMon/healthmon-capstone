using TMPro;
using UnityEngine;

// Attach to FloatingSpeechBubble (a direct child of DialoguePanel).
// The entire dialogue panel still uses Screen Space - Overlay.
// This component tracks ARPlacementManager.SpawnedHealthMon every frame,
// including after switching back from Home; no ARPlacementManager event edit needed.
[RequireComponent(typeof(CanvasGroup))]
public sealed class SpeechBubbleFollowTarget : MonoBehaviour
{
    [Header("Scene references")]
    [SerializeField] private ARPlacementManager arPlacementManager;
    [SerializeField] private Camera arCamera;
    [SerializeField] private RectTransform bubbleRect;

    [Header("Placement")]
    [Tooltip("Extra height above the model's topmost active renderer, in world units.")]
    [SerializeField] private float headPaddingMeters = 0.12f;
    [Tooltip("Extra offset in screen pixels.")]
    [SerializeField] private Vector2 screenOffsetPixels = new Vector2(0f, 18f);
    [Tooltip("Spacing from the DialoguePanel top in its local UI units.")]
    [SerializeField] private float topReservedUI = 140f;
    [Tooltip("Spacing from the DialoguePanel bottom in its local UI units.")]
    [SerializeField] private float bottomReservedUI = 300f;
    [SerializeField] private float sidePaddingUI = 15f;

    private CanvasGroup group;
    private Canvas rootCanvas;
    private RectTransform parentRect;
    private GameObject lastPet;
    private Renderer[] petRenderers;

    private void Awake()
    {
        if (bubbleRect == null) bubbleRect = transform as RectTransform;
        group = GetComponent<CanvasGroup>();
        rootCanvas = GetComponentInParent<Canvas>();
        parentRect = bubbleRect != null ? bubbleRect.parent as RectTransform : null;
        group.interactable = false;
        group.blocksRaycasts = false; // Never intercept AR plane taps.
        group.alpha = 0f;
    }

    private void LateUpdate()
    {
        if (arPlacementManager == null || arCamera == null || bubbleRect == null || parentRect == null)
        {
            Show(false);
            return;
        }

        GameObject pet = arPlacementManager.SpawnedHealthMon;
        if (pet == null || !pet.activeInHierarchy || !arCamera.isActiveAndEnabled)
        {
            lastPet = null;
            petRenderers = null;
            Show(false);
            return;
        }

        if (lastPet != pet)
        {
            lastPet = pet;
            petRenderers = pet.GetComponentsInChildren<Renderer>(true);
        }

        // Renderers give a better head position than the prefab origin,
        // which may be near its feet. Includes animated meshes and accessories.
        Vector3 head = pet.transform.position + Vector3.up * 0.8f;
        bool foundRenderer = false;
        float topY = float.NegativeInfinity;
        if (petRenderers != null)
        {
            foreach (Renderer r in petRenderers)
            {
                if (r == null || !r.enabled || !r.gameObject.activeInHierarchy) continue;
                if (r.bounds.max.y > topY) topY = r.bounds.max.y;
                foundRenderer = true;
            }
        }
        if (foundRenderer)
            head = new Vector3(pet.transform.position.x, topY, pet.transform.position.z);
        head += Vector3.up * headPaddingMeters;

        Vector3 point = arCamera.WorldToScreenPoint(head);
        if (point.z <= 0f || point.x < -50f || point.x > Screen.width + 50f ||
            point.y < -50f || point.y > Screen.height + 50f)
        {
            Show(false);
            return;
        }

        Camera uiCamera = rootCanvas != null && rootCanvas.renderMode != RenderMode.ScreenSpaceOverlay
            ? rootCanvas.worldCamera : null;
        Vector2 local;
        if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(
            parentRect, (Vector2)point + screenOffsetPixels, uiCamera, out local))
        {
            Show(false);
            return;
        }

        // Set the bubble anchors & pivot to Middle-Center (0.5, 0.5).
        float halfW = bubbleRect.rect.width * Mathf.Abs(bubbleRect.localScale.x) * 0.5f;
        float halfH = bubbleRect.rect.height * Mathf.Abs(bubbleRect.localScale.y) * 0.5f;
        float lowX = parentRect.rect.xMin + halfW + sidePaddingUI;
        float highX = parentRect.rect.xMax - halfW - sidePaddingUI;
        float lowY = parentRect.rect.yMin + halfH + bottomReservedUI;
        float highY = parentRect.rect.yMax - halfH - topReservedUI;

        if (lowX > highX) lowX = highX = parentRect.rect.center.x;
        if (lowY > highY) lowY = highY = parentRect.rect.center.y;

        bubbleRect.anchoredPosition = new Vector2(
            Mathf.Clamp(local.x, lowX, highX),
            Mathf.Clamp(local.y, lowY, highY));
        Show(true);
    }

    private void Show(bool visible)
    {
        if (group != null) group.alpha = visible ? 1f : 0f;
    }
}
