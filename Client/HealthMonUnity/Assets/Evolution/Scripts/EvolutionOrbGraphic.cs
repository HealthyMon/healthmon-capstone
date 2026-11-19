using UnityEngine;
using UnityEngine.UI;
namespace HealthMon.Evolution
{
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionOrbGraphic : MaskableGraphic
    {
        [SerializeField] private bool frontGlass;

        [Header("SphereBack: Orb Body")]
        [SerializeField, Range(0f, 1f)] private float centerOpacity = 0.38f;
        [SerializeField, Range(0f, 1f)] private float edgeOpacity = 0.09f;

        [Header("SphereFrontGlass: Front Mist")]
        [SerializeField, Range(0f, 0.5f)] private float frontMistOpacity = 0.08f;

        protected override void OnValidate()
        {
            base.OnValidate();
            SetVerticesDirty();
        }
        public bool FrontGlass { get { return frontGlass; } set { frontGlass=value; SetVerticesDirty(); } }
        private void Update() { if(Application.isPlaying && isActiveAndEnabled && Time.frameCount%3==0) SetVerticesDirty(); }
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            float R=Mathf.Min(rectTransform.rect.width,rectTransform.rect.height)*.47f;
            float time=Application.isPlaying?Time.unscaledTime:0f;
            if (!frontGlass)
            {
                EvolutionMesh.Ellipse(vh,Vector2.zero,new Vector2(R,R),
                    new Color(.24f,.68f,.91f,centerOpacity),new Color(.22f,.52f,.86f,edgeOpacity),112);
                EvolutionMesh.Ring(vh,Vector2.zero,new Vector2(R*.78f,R*.78f),
                    new Vector2(R*.97f,R*.97f),
                    new Color(.20f,.86f,.96f,.02f),new Color(.63f,1f,1f,.12f),96);
                EvolutionMesh.EllipseSoft(vh,new Vector2(-R*.29f,R*.31f),new Vector2(R*.35f,R*.31f),
                    new Color(.75f,.97f,1f,.10f),48);
            }
            else
            {
                // Subtle glass tint overlays the 3D pet without blocking it.
                EvolutionMesh.Ellipse(vh, Vector2.zero, new Vector2(R*.92f,R*.92f),
                    new Color(.55f,.87f,1f,frontMistOpacity),
                    new Color(.42f,.78f,1f,frontMistOpacity*.18f), 112);
                EvolutionMesh.Ring(vh,Vector2.zero,new Vector2(R*.94f,R*.94f),
                    new Vector2(R,R),new Color(.37f,.9f,1f,.12f),new Color(.60f,1f,1f,.75f),112);
                EvolutionMesh.Ring(vh,Vector2.zero,new Vector2(R*.89f,R*.89f),
                    new Vector2(R*.925f,R*.925f),new Color(.63f,.95f,1f,.02f),new Color(.52f,.97f,1f,.19f),112);
                EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(R*.96f,R*.96f),11f,
                    Mathf.PI*.36f,Mathf.PI*.84f,new Color(.94f,1f,1f,.54f),45);
                EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(R*.968f,R*.968f),5f,
                    Mathf.PI*1.52f,Mathf.PI*1.78f,new Color(.72f,.71f,1f,.38f),32);
                EvolutionMesh.Star(vh,new Vector2(-R*.66f,R*.65f),18f+
                    Mathf.Sin(time*2f)*5f,new Color(.90f,1f,1f,.8f));
            }
        }
    }
}
