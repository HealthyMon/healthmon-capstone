using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    /// <summary>Subtle pet float, aura breathing, and background glow.</summary>
    public class EvolutionStageMotion : MonoBehaviour
    {
        public RectTransform petPreview;
        public RectTransform glow;
        public Image glowImage;
        private Vector2 _petOriginalPos;
        private Vector3 _glowOriginalScale;

        private void OnEnable()
        {
            if (petPreview != null) _petOriginalPos = petPreview.anchoredPosition;
            if (glow != null) _glowOriginalScale = glow.localScale;
        }

        private void Update()
        {
            float t = Time.unscaledTime;
            if (petPreview != null)
                petPreview.anchoredPosition = _petOriginalPos + new Vector2(0f, Mathf.Sin(t * 1.7f) * 9f);
            if (glow != null)
                glow.localScale = _glowOriginalScale * (1f + Mathf.Sin(t * 1.9f) * .08f);
            if (glowImage != null)
            {
                Color c = glowImage.color;
                c.a = .44f + Mathf.Sin(t * 1.9f) * .11f;
                glowImage.color = c;
            }
        }
    }
}
