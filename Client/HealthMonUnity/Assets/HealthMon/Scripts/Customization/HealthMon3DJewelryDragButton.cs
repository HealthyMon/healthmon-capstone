using UnityEngine;
using UnityEngine.EventSystems;

/// <summary>
/// Attach to one of four NEW UI palette buttons in HomePanel.
/// Mouse and mobile finger both use the EventSystem pointer/drag interfaces.
/// Drag the button across the visible 3D HomePet, release to attach the real model.
/// Tap (without drag) toggles equipment for that slot.
/// </summary>
public sealed class HealthMon3DJewelryDragButton : MonoBehaviour,
    IPointerDownHandler, IPointerClickHandler, IBeginDragHandler, IDragHandler, IEndDragHandler
{
    [SerializeField] private HealthMon3DJewelryRig rig;
    [SerializeField] private Camera homeCamera;
    [SerializeField, Range(0, 3)] private int slotIndex;

    private bool dragging;
    private bool ignoreClick;
    private Vector3 beforePosition;
    private bool wasEquipped;

    public void OnPointerDown(PointerEventData eventData)
    {
        ignoreClick = false;
    }

    public void OnPointerClick(PointerEventData eventData)
    {
        if (ignoreClick || rig == null) return;
        rig.Toggle(slotIndex);
    }

    public void OnBeginDrag(PointerEventData eventData)
    {
        if (rig == null || homeCamera == null) return;
        dragging = rig.BeginDrag(slotIndex, out beforePosition, out wasEquipped);
        if (!dragging) return;
        ignoreClick = true;
        rig.TryPreviewAt(slotIndex, homeCamera, eventData.position);
    }

    public void OnDrag(PointerEventData eventData)
    {
        if (dragging) rig.TryPreviewAt(slotIndex, homeCamera, eventData.position);
    }

    public void OnEndDrag(PointerEventData eventData)
    {
        if (!dragging) return;
        dragging = false;
        rig.FinishDrag(slotIndex, homeCamera, eventData.position, beforePosition, wasEquipped);
    }

    private void OnDisable()
    {
        if (dragging && rig != null) rig.CancelDrag(slotIndex, beforePosition, wasEquipped);
        dragging = false;
    }
}
