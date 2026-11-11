using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionBackdropGraphic : MaskableGraphic
    {
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            Rect r=rectTransform.rect;
            EvolutionMesh.RectGradient(vh,r,new Color(.026f,.055f,.12f,1f),new Color(.067f,.095f,.22f,1f));
            EvolutionMesh.EllipseSoft(vh, new Vector2(r.center.x,r.yMin+r.height*.61f),
                new Vector2(r.width*.75f,r.height*.40f),new Color(.29f,.19f,.69f,.30f));
            EvolutionMesh.EllipseSoft(vh, new Vector2(r.center.x,r.yMin+r.height*.53f),
                new Vector2(r.width*.62f,r.height*.30f),new Color(.06f,.7f,.75f,.09f));
            // Small stationary stars, deterministic and inexpensive.
            for(int i=0;i<40;i++)
            {
                float xx=Mathf.Repeat((i*0.618034f+.18f)*13.42f,1f);
                float yy=Mathf.Repeat((i*0.381966f+.12f)*7.61f,1f);
                Vector2 p=new Vector2(Mathf.Lerp(r.xMin+30,r.xMax-30,xx),Mathf.Lerp(r.yMin+70,r.yMax-70,yy));
                float s=i%8==0 ? 8f : 2.5f;
                EvolutionMesh.Star(vh,p,s,new Color(.52f,.93f,1f,i%4==0?.6f:.25f));
            }
        }
    }
}
