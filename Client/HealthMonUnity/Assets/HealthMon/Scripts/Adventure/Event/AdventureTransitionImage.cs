using UnityEngine;
using UnityEngine.Sprites;
using UnityEngine.UI;

/// <summary>Fill the transition canvas while keeping the animated creature undistorted.</summary>
[RequireComponent(typeof(Image))]
public sealed class AdventureTransitionImage : BaseMeshEffect
{
    public bool preserveCreature;

    public override void ModifyMesh(VertexHelper mesh)
    {
        if (!IsActive()) return;
        var image = (Image)graphic;
        var sprite = image.overrideSprite != null ? image.overrideSprite : image.sprite;
        if (sprite == null) return;
        var rect = image.GetPixelAdjustedRect();
        if (rect.width <= 0 || rect.height <= 0) return;
        var uv = DataUtility.GetOuterUV(sprite);
        mesh.Clear();
        float aspect = sprite.rect.width / sprite.rect.height;
        if (preserveCreature && rect.height > rect.width / aspect)
        {
            // Every animation frame places the slime between these two source rows.
            // Extend only the empty ceiling/floor; the creature keeps uniform scale
            // and occupies the full screen width instead of a small inset panel.
            const float lower = .14f, upper = .62f;
            float subjectHeight = rect.width / aspect * (upper - lower);
            float bottom = rect.yMin + rect.height * .48f - subjectHeight * .5f;
            float top = bottom + subjectHeight;
            Quad(mesh, rect.xMin, rect.xMax, rect.yMin, bottom, uv, 0, lower, image.color);
            Quad(mesh, rect.xMin, rect.xMax, bottom, top, uv, lower, upper, image.color);
            Quad(mesh, rect.xMin, rect.xMax, top, rect.yMax, uv, upper, 1, image.color);
        }
        else
        {
            // Stair artwork is a background: cover the display without stretching.
            float scale = Mathf.Max(rect.width / sprite.rect.width, rect.height / sprite.rect.height);
            float visibleX = rect.width / (sprite.rect.width * scale);
            float visibleY = rect.height / (sprite.rect.height * scale);
            var crop = new Vector4(
                Mathf.Lerp(uv.x, uv.z, (1 - visibleX) * .5f),
                Mathf.Lerp(uv.y, uv.w, (1 - visibleY) * .5f),
                Mathf.Lerp(uv.x, uv.z, (1 + visibleX) * .5f),
                Mathf.Lerp(uv.y, uv.w, (1 + visibleY) * .5f));
            Quad(mesh, rect.xMin, rect.xMax, rect.yMin, rect.yMax, crop, 0, 1, image.color);
        }
    }

    static void Quad(VertexHelper mesh, float left, float right, float bottom, float top,
        Vector4 uv, float lowV, float highV, Color color)
    {
        int start = mesh.currentVertCount;
        float low = Mathf.Lerp(uv.y, uv.w, lowV), high = Mathf.Lerp(uv.y, uv.w, highV);
        mesh.AddVert(new Vector3(left, bottom), color, new Vector2(uv.x, low));
        mesh.AddVert(new Vector3(left, top), color, new Vector2(uv.x, high));
        mesh.AddVert(new Vector3(right, top), color, new Vector2(uv.z, high));
        mesh.AddVert(new Vector3(right, bottom), color, new Vector2(uv.z, low));
        mesh.AddTriangle(start, start + 1, start + 2);
        mesh.AddTriangle(start + 2, start + 3, start);
    }
}
