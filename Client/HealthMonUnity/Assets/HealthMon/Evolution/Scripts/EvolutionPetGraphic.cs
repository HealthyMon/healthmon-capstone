using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    /// <summary>Transparent procedural fallback slime: no missing-sprite white squares.</summary>
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionPetGraphic : MaskableGraphic
    {
        private void Update()
        {
            if(Application.isPlaying && isActiveAndEnabled && Time.frameCount%3==0) SetVerticesDirty();
        }
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            float unit=Mathf.Min(rectTransform.rect.width,rectTransform.rect.height)/450f;
            float t=Application.isPlaying ? Time.unscaledTime : 0f;
            Vector2 pos=new Vector2(0,Mathf.Sin(t*1.5f)*6f)*unit;
            // leaf stem and foliage
            EvolutionMesh.Segment(vh,pos+new Vector2(0,142)*unit,pos+new Vector2(3,184)*unit,9*unit,
                new Color(.54f,1f,.78f,1f),new Color(.26f,.72f,.57f,1f));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-34,183)*unit,new Vector2(45,22)*unit,
                new Color(.62f,1f,.80f,1),new Color(.11f,.67f,.57f,1));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(35,190)*unit,new Vector2(41,23)*unit,
                new Color(.69f,1f,.83f,1),new Color(.12f,.69f,.64f,1));
            // depth shadow and soft blob highlights
            EvolutionMesh.EllipseSoft(vh,pos+new Vector2(0,-130)*unit,new Vector2(180,52)*unit,
                new Color(.08f,.98f,.84f,.25f));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(0,-9)*unit,new Vector2(174,151)*unit,
                new Color(.35f,.87f,.88f,1),new Color(.18f,.55f,.80f,1));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-27,25)*unit,new Vector2(126,111)*unit,
                new Color(.64f,1f,.91f,.82f),new Color(.45f,.91f,.98f,.08f));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-80,77)*unit,new Vector2(45,18)*unit,
                new Color(1,1,1,.65f),new Color(1,1,1,0));
            // two bright face points (readable at phone scale)
            Color eye=new Color(.075f,.16f,.32f,1);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-51,-15)*unit,new Vector2(11,17)*unit,eye,eye,24);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(50,-15)*unit,new Vector2(11,17)*unit,eye,eye,24);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-49,-8)*unit,new Vector2(4,5)*unit,Color.white,Color.white,16);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(52,-8)*unit,new Vector2(4,5)*unit,Color.white,Color.white,16);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(0,-44)*unit,new Vector2(17,10)*unit,
                new Color(.23f,.14f,.39f,1),new Color(.23f,.14f,.39f,1),24);
            EvolutionMesh.Ellipse(vh,pos+new Vector2(-96,-43)*unit,new Vector2(23,11)*unit,
                new Color(1f,.55f,.73f,.53f),new Color(1f,.55f,.73f,0));
            EvolutionMesh.Ellipse(vh,pos+new Vector2(96,-43)*unit,new Vector2(23,11)*unit,
                new Color(1f,.55f,.73f,.53f),new Color(1f,.55f,.73f,0));
        }
    }
}
