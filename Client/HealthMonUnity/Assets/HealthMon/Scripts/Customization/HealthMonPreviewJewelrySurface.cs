using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

/// <summary>
/// Drag an equipped 3D model directly in the PetPreviewImage's RenderTexture.
/// When the optional adjust editor is connected, a picked item becomes selected
/// for rotation and scaling as well.
/// </summary>
public sealed class HealthMonPreviewJewelrySurface : MonoBehaviour,
    IBeginDragHandler, IDragHandler, IEndDragHandler
{
    [SerializeField] private HealthMon3DJewelryRig previewRig;
    [SerializeField] private RawImage petPreviewImage;
    [SerializeField] private Camera petPreviewCamera;
    [SerializeField, Min(5f)] private float pickRadiusUiUnits = 90f;
    [Header("Optional rotate/scale editor")]
    [SerializeField] private HealthMon3DJewelryAdjustPanel adjustPanel;

    private bool dragging;
    private int activeSlot = -1;
    private Vector3 startPosition;
    private bool startEquipped;

    public void OnBeginDrag(PointerEventData data)
    {
        if (previewRig == null || petPreviewImage == null || petPreviewCamera == null) return;
        if (!HealthMonPreviewJewelryCoordinates.TryGetViewport(
            petPreviewImage, data, out Vector2 uv)) return;

        int best = -1;
        float bestDistance = pickRadiusUiUnits;
        RectTransform rect = petPreviewImage.rectTransform;
        Rect uvRect = petPreviewImage.uvRect;
        if (Mathf.Abs(uvRect.width) < 0.001f || Mathf.Abs(uvRect.height) < 0.001f) return;
        Vector2 normalized = new Vector2(
            (uv.x - uvRect.x) / uvRect.width,
            (uv.y - uvRect.y) / uvRect.height);

        for (int i = 0; i < 4; i++)
        {
            if (!previewRig.IsEquipped(i) ||
                !previewRig.TryGetJewelryWorldCenter(i, out Vector3 center)) continue;
            Vector3 projected = petPreviewCamera.WorldToViewportPoint(center);
            if (projected.z <= 0f) continue;
            float dx = (projected.x - normalized.x) * rect.rect.width;
            float dy = (projected.y - normalized.y) * rect.rect.height;
            float distance = Mathf.Sqrt(dx * dx + dy * dy);
            if (distance < bestDistance) { best = i; bestDistance = distance; }
        }

        if (best < 0) return;
        activeSlot = best;
        dragging = previewRig.BeginDrag(activeSlot, out startPosition, out startEquipped);
        if (!dragging) { activeSlot = -1; return; }
        if (adjustPanel != null) adjustPanel.SelectSlot(activeSlot, false);
        DragTo(data);
    }

    public void OnDrag(PointerEventData data)
    {
        if (dragging) DragTo(data);
    }

    private void DragTo(PointerEventData data)
    {
        if (HealthMonPreviewJewelryCoordinates.TryGetRay(
            petPreviewImage, petPreviewCamera, data, out Ray ray))
            previewRig.TryPreviewOnRay(activeSlot, ray);
    }

    public void OnEndDrag(PointerEventData data)
    {
        if (!dragging) return;
        dragging = false;
        if (HealthMonPreviewJewelryCoordinates.TryGetRay(
            petPreviewImage, petPreviewCamera, data, out Ray ray))
            previewRig.FinishDragOnRay(activeSlot, ray, startPosition, startEquipped);
        else
            previewRig.CancelDrag(activeSlot, startPosition, startEquipped);
        activeSlot = -1;
        if (adjustPanel != null) adjustPanel.RefreshValues();
    }

    private void OnDisable()
    {
        if (dragging && previewRig != null)
            previewRig.CancelDrag(activeSlot, startPosition, startEquipped);
        dragging = false;
        activeSlot = -1;
    }
}
