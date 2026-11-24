using UnityEngine;
using UnityEngine.UI;

/// <summary>Resolution-independent rounded panels, without stretched UI bitmaps.</summary>
[RequireComponent(typeof(CanvasRenderer))]
public sealed class HealthMonStatusPanelGraphic : MaskableGraphic
{
    public Color Top = Color.white, Bottom = Color.white, Border = Color.clear;
    public float Radius = 20, BorderWidth = 1.5f;
    private const int CornerSteps = 10;

    protected override void OnPopulateMesh(VertexHelper vh)
    {
        vh.Clear();
        Rect bounds = GetPixelAdjustedRect();
        if (bounds.width <= 0 || bounds.height <= 0) return;
        if (BorderWidth > 0 && Border.a > 0)
        {
            Rounded(vh, bounds, Radius, Border, Border, bounds);
            float inset = Mathf.Min(BorderWidth, Mathf.Min(bounds.width, bounds.height) * .5f);
            var inner = new Rect(bounds.x + inset, bounds.y + inset, bounds.width - inset * 2, bounds.height - inset * 2);
            Rounded(vh, inner, Mathf.Max(0, Radius - inset), Bottom, Top, bounds);
        }
        else Rounded(vh, bounds, Radius, Bottom, Top, bounds);
    }

    private void Rounded(VertexHelper vh, Rect r, float radius, Color bottom, Color top, Rect gradient)
    {
        if (r.width <= 0 || r.height <= 0) return;
        radius = Mathf.Clamp(radius, 0, Mathf.Min(r.width, r.height) * .5f);
        int start = vh.currentVertCount;
        Add(vh, r.center, Tint(r.center.y, bottom, top, gradient));
        for (int corner = 0; corner < 4; corner++)
        {
            Vector2 c = new Vector2(corner == 0 || corner == 3 ? r.xMax - radius : r.xMin + radius,
                corner < 2 ? r.yMax - radius : r.yMin + radius);
            for (int step = 0; step <= CornerSteps; step++)
            {
                float angle = (corner * 90 + step * 90f / CornerSteps) * Mathf.Deg2Rad;
                Vector2 p = c + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius;
                Add(vh, p, Tint(p.y, bottom, top, gradient));
            }
        }
        int count = 4 * (CornerSteps + 1);
        for (int i = 0; i < count; i++) vh.AddTriangle(start, start + 1 + i, start + 1 + (i + 1) % count);
    }

    private Color Tint(float y, Color bottom, Color top, Rect gradient) =>
        Color.Lerp(bottom, top, Mathf.InverseLerp(gradient.yMin, gradient.yMax, y)) * color;
    private static void Add(VertexHelper vh, Vector2 p, Color tint) => vh.AddVert(p, tint, Vector2.zero);
}
