using UnityEngine;
using UnityEngine.UI;
namespace HealthMon.Evolution
{
    /// <summary>2 ribbon spirals projected onto front/back of the glass orb.</summary>
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionVortexGraphic : MaskableGraphic
    {
        [SerializeField] private bool frontHalf = true;
        [SerializeField, Range(.1f,2f)] private float rotationSpeed=.85f;
        [SerializeField, Range(48,128)] private int samplesPerRibbon=96;
        private float nextRefresh;
        public bool FrontHalf { get { return frontHalf; } set { frontHalf=value; SetVerticesDirty(); } }
        private void Update()
        {
            // 30fps mesh updates even if the project is running at 60fps.
            if(!Application.isPlaying || !isActiveAndEnabled || Time.unscaledTime<nextRefresh) return;
            nextRefresh=Time.unscaledTime+(1f/30f);
            SetVerticesDirty();
        }
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            float size=Mathf.Min(rectTransform.rect.width,rectTransform.rect.height)/800f;
            float spin=Application.isPlaying?Time.unscaledTime*rotationSpeed:0.4f;
            Make(vh,size,spin,0f,new Color(.31f,1f,.87f,1f));
            Make(vh,size,spin,2.45f,new Color(.71f,.53f,1f,1f));
        }
        private void Make(VertexHelper vh,float s,float spin,float shift,Color tint)
        {
            for(int i=0;i<samplesPerRibbon;i++)
            {
                float t0=(float)i/samplesPerRibbon, t1=(float)(i+1)/samplesPerRibbon;
                float tm=(t0+t1)*.5f;
                float phase=tm*Mathf.PI*4.0f+spin+shift;
                bool front = Mathf.Sin(phase)>0f;
                if(front!=frontHalf) continue;
                Vector2 p0=Point(t0,s,spin,shift), p1=Point(t1,s,spin,shift);
                float edgeFade=Mathf.SmoothStep(0f,1f,Mathf.Min(1f,Mathf.Min(tm,1f-tm)*9f));
                float d=Mathf.Abs(Mathf.Sin(phase));
                float alpha=(frontHalf?.75f:.23f)*(.45f+.55f*d)*edgeFade;
                float band=(16f+18f*d)*s;
                Color fade=new Color(tint.r,tint.g,tint.b,alpha*.12f);
                EvolutionMesh.Segment(vh,p0,p1,band*2.7f,fade,new Color(tint.r,tint.g,tint.b,0));
                EvolutionMesh.Segment(vh,p0,p1,band*1.4f,
                    new Color(tint.r,tint.g,tint.b,alpha*.75f),new Color(tint.r,tint.g,tint.b,alpha*.08f));
                EvolutionMesh.Segment(vh,p0,p1,Mathf.Max(2f,band*.14f),
                    new Color(1f,1f,1f,alpha*.95f),new Color(.65f,1f,1f,alpha*.5f));
            }
        }
        private static Vector2 Point(float t,float s,float spin,float shift)
        {
            float a=t*Mathf.PI*4f+spin+shift;
            float taper=.93f + .12f*Mathf.Sin(t*Mathf.PI);
            float r=307f*taper;
            return new Vector2(Mathf.Cos(a)*r,((t-.5f)*555f+Mathf.Sin(a)*37f))*s;
        }
    }
}
