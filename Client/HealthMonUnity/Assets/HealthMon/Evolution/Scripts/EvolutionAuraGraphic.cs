using UnityEngine;
using UnityEngine.UI;
namespace HealthMon.Evolution
{
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionAuraGraphic : MaskableGraphic
    {
        public bool floor;
        private void Update() { if(Application.isPlaying && isActiveAndEnabled && Time.frameCount%3==0) SetVerticesDirty(); }
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            float s=floor ? rectTransform.rect.width : Mathf.Min(rectTransform.rect.width,rectTransform.rect.height);
            float t=Application.isPlaying ? Time.unscaledTime : 0f;
            float pulse=1f+.04f*Mathf.Sin(t*1.5f);
            if (floor)
            {
                EvolutionMesh.EllipseSoft(vh,Vector2.zero,new Vector2(s*.46f,s*.13f)*pulse,
                    new Color(.18f,.98f,.93f,.38f));
                EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(s*.37f,s*.09f),3f,0,Mathf.PI*2f,
                    new Color(.55f,1f,.96f,.66f),92);
                EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(s*.28f,s*.063f),2f,0,Mathf.PI*2f,
                    new Color(.73f,.57f,1f,.65f),92);
                for(int i=0;i<8;i++)
                {
                    float a=t*.2f+i*Mathf.PI/4f;
                    EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(s*.42f,s*.105f),6f,a,a+.20f,
                        new Color(.38f,1f,.92f,.88f),7);
                }
            }
            else
            {
                EvolutionMesh.EllipseSoft(vh,Vector2.zero,new Vector2(s*.48f,s*.47f)*pulse,
                    new Color(.14f,.83f,.98f,.25f));
                EvolutionMesh.EllipseSoft(vh,Vector2.zero,new Vector2(s*.35f,s*.37f),
                    new Color(.48f,.37f,.98f,.18f));
                EvolutionMesh.Arc(vh,Vector2.zero,new Vector2(s*.425f,s*.425f),3f,
                    .1f+t*.11f,1.68f+t*.11f,new Color(.44f,.98f,.95f,.35f),48);
            }
        }
    }
}
