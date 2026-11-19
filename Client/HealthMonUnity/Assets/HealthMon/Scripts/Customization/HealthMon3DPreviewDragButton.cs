using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

/// <summary>
/// Four palette buttons INSIDE CustomizationPanel. Tap to select/edit (when adjustPanel
/// is assigned) or retain legacy equip toggle (when unassigned). Drag to place the
/// original 3D accessory onto the SphereCollider of the Preview pet.
/// </summary>
public sealed class HealthMon3DPreviewDragButton : MonoBehaviour,
    IPointerClickHandler, IBeginDragHandler, IDragHandler, IEndDragHandler
{
    [SerializeField] private HealthMon3DJewelryRig previewRig;
    [SerializeField] private RawImage petPreviewImage;
    [SerializeField] private Camera petPreviewCamera;
    [SerializeField, Range(0, 3)] private int slotIndex;
    [Header("Optional rotate/scale editor")]
    [SerializeField] private HealthMon3DJewelryAdjustPanel adjustPanel;

    private bool dragging;
    private bool suppressClick;
    private Vector3 startPosition;
    private bool startEquipped;

    public void OnPointerClick(PointerEventData data)
    {
        if (suppressClick || previewRig == null) return;
        if (adjustPanel != null) adjustPanel.SelectSlot(slotIndex, true);
        else previewRig.Toggle(slotIndex);
    }

    public void OnBeginDrag(PointerEventData data)
    {
        suppressClick = false;
        if (previewRig == null || petPreviewImage == null || petPreviewCamera == null) return;
        dragging = previewRig.BeginDrag(slotIndex, out startPosition, out startEquipped);
        if (!dragging) return;
        suppressClick = true;
        if (adjustPanel != null) adjustPanel.SelectSlot(slotIndex, false);
        Preview(data);
    }

    public void OnDrag(PointerEventData data)
    {
        if (dragging) Preview(data);
    }

    private void Preview(PointerEventData data)
    {
        if (HealthMonPreviewJewelryCoordinates.TryGetRay(
            petPreviewImage, petPreviewCamera, data, out Ray ray))
            previewRig.TryPreviewOnRay(slotIndex, ray);
    }

    public void OnEndDrag(PointerEventData data)
    {
        if (!dragging) return;
        dragging = false;
        if (HealthMonPreviewJewelryCoordinates.TryGetRay(
            petPreviewImage, petPreviewCamera, data, out Ray ray))
            previewRig.FinishDragOnRay(slotIndex, ray, startPosition, startEquipped);
        else
            previewRig.CancelDrag(slotIndex, startPosition, startEquipped);
        if (adjustPanel != null) adjustPanel.RefreshValues();
    }

    private void OnDisable()
    {
        if (dragging && previewRig != null)
            previewRig.CancelDrag(slotIndex, startPosition, startEquipped);
        dragging = false;
    }
}
