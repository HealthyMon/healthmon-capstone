using System;
using UnityEngine;
using UnityEngine.UI;

/// <summary>Six independent 0..100 scores. Energy and combat units never enter this chart.</summary>
[RequireComponent(typeof(CanvasRenderer))]
public sealed class HealthMonRadarGraphic : MaskableGraphic
{
    private readonly float[] values = new float[6];
    private bool hasValues;
    public Color Grid = new Color(.20f, .67f, .86f, .30f);
    public Color Outline = new Color(.11f, .86f, 1f, 1f);
    public Color Fill = new Color(.06f, .77f, .92f, .30f);
    public Color Dot = new Color(1f, .87f, .28f, 1f);

    public void SetValues(float[] axes)
    {
        bool next = axes != null && axes.Length == 6;
        bool changed = hasValues != next;
        for (int i = 0; i < 6; i++)
        {
            float value = next ? HealthMonStatusSnapshot.Unit(axes[i] / 100) : 0;
            changed |= values[i] != value;
            values[i] = value;
        }
        hasValues = next;
        if (changed) SetVerticesDirty();
    }

    public static Vector2 AxisPoint(int axis, float radius)
    {
        double angle = Math.PI * .5 - axis * Math.PI / 3;
        return new Vector2((float)Math.Cos(angle) * radius, (float)Math.Sin(angle) * radius);
    }

    protected override void OnPopulateMesh(VertexHelper vh)
    {
        vh.Clear();
        Rect rect = GetPixelAdjustedRect();
        Vector2 c = rect.center;
        float radius = Mathf.Min(rect.width, rect.height) * .46f;
        if (radius <= 0) return;
        for (int ring = 1; ring <= 5; ring++)
            for (int axis = 0; axis < 6; axis++)
                Line(vh, c + AxisPoint(axis, radius * ring / 5), c + AxisPoint((axis + 1) % 6, radius * ring / 5), 1.1f, Grid);
        for (int axis = 0; axis < 6; axis++) Line(vh, c, c + AxisPoint(axis, radius), 1, Grid);
        if (!hasValues) return;
        int first = vh.currentVertCount;
        vh.AddVert(c, Fill, Vector2.zero);
        for (int axis = 0; axis < 6; axis++) vh.AddVert(c + AxisPoint(axis, radius * values[axis]), Fill, Vector2.zero);
        for (int axis = 0; axis < 6; axis++) vh.AddTriangle(first, first + 1 + axis, first + 1 + (axis + 1) % 6);
        for (int axis = 0; axis < 6; axis++)
        {
            Vector2 p = c + AxisPoint(axis, radius * values[axis]);
            Line(vh, p, c + AxisPoint((axis + 1) % 6, radius * values[(axis + 1) % 6]), 2.5f, Outline);
            Circle(vh, p, 4.5f, Dot);
        }
    }

    private static void Line(VertexHelper vh, Vector2 a, Vector2 b, float width, Color tint)
    {
        Vector2 delta = b - a;
        if (delta.sqrMagnitude < .0001f) return;
        Vector2 n = new Vector2(-delta.y, delta.x).normalized * width * .5f;
        int start = vh.currentVertCount;
        vh.AddVert(a - n, tint, Vector2.zero); vh.AddVert(a + n, tint, Vector2.zero);
        vh.AddVert(b + n, tint, Vector2.zero); vh.AddVert(b - n, tint, Vector2.zero);
        vh.AddTriangle(start, start + 1, start + 2); vh.AddTriangle(start, start + 2, start + 3);
    }

    private static void Circle(VertexHelper vh, Vector2 c, float radius, Color tint)
    {
        int start = vh.currentVertCount;
        vh.AddVert(c, tint, Vector2.zero);
        for (int i = 0; i < 12; i++)
            vh.AddVert(c + new Vector2(Mathf.Cos(i * Mathf.PI / 6), Mathf.Sin(i * Mathf.PI / 6)) * radius, tint, Vector2.zero);
        for (int i = 0; i < 12; i++) vh.AddTriangle(start, start + 1 + i, start + 1 + (i + 1) % 12);
    }
}
