using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

/// <summary>
/// Maps pointers over CustomizationPanel/CharacterPreview/PetPreviewImage (RawImage)
/// to rays in the PetPreviewCamera's RenderTexture projection.
/// IMPORTANT: ordinary ScreenPointToRay(eventData.position) is wrong here.
/// </summary>
public static class HealthMonPreviewJewelryCoordinates
{
    public static bool TryGetViewport(RawImage image, PointerEventData data, out Vector2 viewport)
    {
        viewport = Vector2.zero;
        if (image == null || data == null) return false;
        RectTransform rect = image.rectTransform;
        if (rect == null) return false;

        Canvas canvas = image.canvas;
        Camera uiCamera = canvas != null && canvas.renderMode == RenderMode.ScreenSpaceOverlay
            ? null : data.pressEventCamera;

        if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(
            rect, data.position, uiCamera, out Vector2 local)) return false;

        Rect bounds = rect.rect;
        if (bounds.width <= 0f || bounds.height <= 0f || !bounds.Contains(local)) return false;

        float u = (local.x - bounds.xMin) / bounds.width;
        float v = (local.y - bounds.yMin) / bounds.height;
        Rect uv = image.uvRect;
        viewport = new Vector2(uv.x + u * uv.width, uv.y + v * uv.height);
        return viewport.x >= 0f && viewport.x <= 1f && viewport.y >= 0f && viewport.y <= 1f;
    }

    public static bool TryGetRay(RawImage image, Camera previewCamera, PointerEventData data, out Ray ray)
    {
        ray = new Ray();
        if (previewCamera == null || !TryGetViewport(image, data, out Vector2 viewport)) return false;
        ray = previewCamera.ViewportPointToRay(new Vector3(viewport.x, viewport.y, 0f));
        return true;
    }
}
