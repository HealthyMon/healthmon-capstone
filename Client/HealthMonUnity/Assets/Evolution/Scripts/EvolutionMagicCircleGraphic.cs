using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    /// <summary>Elliptical energy circles under the evolution sphere.</summary>
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionMagicCircleGraphic : MaskableGraphic
    {
        protected override void Awake()
        {
            base.Awake();
            raycastTarget = false;
        }

        private void Update()
        {
            if (Application.isPlaying && isActiveAndEnabled) SetVerticesDirty();
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            Rect rect = rectTransform.rect;
            float t = Application.isPlaying ? Time.unscaledTime : 0f;
            DrawEllipse(vh, rect.width * .44f, rect.height * .32f, 3.5f, 0f, Mathf.PI * 2f, new Color(.40f, 1f, .95f, .63f));
            DrawEllipse(vh, rect.width * .34f, rect.height * .22f, 2f, 0f, Mathf.PI * 2f, new Color(.80f, .56f, 1f, .63f));
            DrawEllipse(vh, rect.width * .23f, rect.height * .12f, 2.2f, 0f, Mathf.PI * 2f, new Color(.50f, 1f, .85f, .70f));
            for (int i = 0; i < 8; i++)
            {
                float a = i * Mathf.PI / 4f + t * .16f;
                DrawEllipse(vh, rect.width * .47f, rect.height * .36f, 7f, a, a + .28f, new Color(.41f, 1f, .95f, .78f));
            }
        }

        private static void DrawEllipse(VertexHelper vh, float rx, float ry, float lineWidth,
                                        float from, float to, Color color)
        {
            int samples = Mathf.Max(3, Mathf.RoundToInt((to - from) / (Mathf.PI * 2f) * 95));
            for (int i = 0; i < samples; i++)
            {
                float a = Mathf.Lerp(from, to, (float)i / samples);
                float b = Mathf.Lerp(from, to, (float)(i+1) / samples);
                Vector2 p0 = new Vector2(rx*Mathf.Cos(a), ry*Mathf.Sin(a));
                Vector2 p1 = new Vector2(rx*Mathf.Cos(b), ry*Mathf.Sin(b));
                Vector2 tangent = (p1-p0).normalized;
                Vector2 n = new Vector2(-tangent.y,tangent.x) * lineWidth * .5f;
                int k = vh.currentVertCount;
                Add(vh, p0-n, color); Add(vh, p0+n, color);
                Add(vh, p1+n, color); Add(vh, p1-n, color);
                vh.AddTriangle(k,k+1,k+2); vh.AddTriangle(k,k+2,k+3);
            }
        }
        private static void Add(VertexHelper vh, Vector2 point, Color c)
        {
            UIVertex v = UIVertex.simpleVert;
            v.position = new Vector3(point.x, point.y, 0);
            v.color = c;
            vh.AddVert(v);
        }
    }
}
