using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    /// <summary>UI-based twinkling stars, no ParticleSystem needed.</summary>
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionSparklesGraphic : MaskableGraphic
    {
        [SerializeField, Range(5, 48)] private int sparkleCount = 27;

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
            float scale = Mathf.Min(rectTransform.rect.width, rectTransform.rect.height) / 800f;
            float time = Application.isPlaying ? Time.unscaledTime : 1f;
            for (int i = 0; i < sparkleCount; i++)
            {
                float angle = (i * 2.399963f + .63f);
                float radial = (283f + (i * 57 % 110)) * scale;
                Vector2 p = new Vector2(Mathf.Cos(angle) * radial,
                                         Mathf.Sin(angle) * radial * .92f);
                float pulse = Mathf.Pow(Mathf.Max(0f, Mathf.Sin(time * (1.4f + (i % 5) * .24f) + i * 1.7f)), 2f);
                float radius = (3.5f + 10f * pulse + (i % 4) * .8f) * scale;
                Color tint = i % 3 == 0 ? new Color(.80f,.60f,1f,.65f*pulse)
                            : new Color(.65f,1f,.95f,.70f*pulse);
                AddStar(vh, p, radius, tint);
            }
        }

        private static void AddStar(VertexHelper vh, Vector2 p, float r, Color c)
        {
            if (r < .1f) return;
            int start = vh.currentVertCount;
            UIVertex v = UIVertex.simpleVert;
            v.position = new Vector3(p.x, p.y, 0f);
            v.color = new Color(1f,1f,1f,c.a);
            vh.AddVert(v);
            for (int i = 0; i < 8; i++)
            {
                float a = i * Mathf.PI / 4f;
                float ri = i % 2 == 0 ? r : r * .16f;
                v.position = new Vector3(p.x + Mathf.Cos(a) * ri, p.y + Mathf.Sin(a) * ri, 0f);
                v.color = c;
                vh.AddVert(v);
            }
            for (int i = 0; i < 8; i++)
                vh.AddTriangle(start, start + 1 + i, start + 1 + ((i + 1) % 8));
        }
    }
}
