using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    [RequireComponent(typeof(CanvasRenderer))]
    public class EvolutionPanelGraphic : MaskableGraphic
    {
        public enum Theme { DarkCard, Status, Hint, MintButton, GhostButton, Badge }
        public Theme theme = Theme.DarkCard;
        [Range(0,100)] public float radius = 35;
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            Rect r=rectTransform.rect;
            float rad=Mathf.Min(radius,r.height*.5f);
            Color border, inner;
            switch(theme)
            {
                case Theme.Status: border=new Color(.21f,.95f,.86f,.62f);inner=new Color(.055f,.17f,.30f,.98f);break;
                case Theme.Hint: border=new Color(.50f,.52f,.98f,.43f);inner=new Color(.095f,.16f,.34f,.96f);break;
                case Theme.MintButton: border=new Color(.74f,1f,.94f,1f);inner=new Color(.36f,.95f,.81f,1f);break;
                case Theme.GhostButton: border=new Color(.37f,.55f,.88f,.65f);inner=new Color(.08f,.14f,.29f,.98f);break;
                case Theme.Badge: border=new Color(.48f,1f,.87f,.7f);inner=new Color(.10f,.29f,.36f,.9f);break;
                default: border=new Color(.47f,.55f,.94f,.31f);inner=new Color(.07f,.11f,.23f,.93f);break;
            }
            EvolutionMesh.Rounded(vh,r,rad,border);
            Rect inset=new Rect(r.x+2.6f,r.y+2.6f,r.width-5.2f,r.height-5.2f);
            EvolutionMesh.Rounded(vh,inset,Mathf.Max(1,rad-2.6f),inner);
            if(theme == Theme.MintButton)
            {
                Rect shine=new Rect(inset.x+10,inset.y+inset.height*.54f,inset.width-20,inset.height*.38f);
                EvolutionMesh.Rounded(vh,shine,shine.height*.5f,new Color(.80f,1f,1f,.18f));
            }
            else
            {
                EvolutionMesh.Arc(vh,new Vector2(r.center.x,r.center.y),
                    new Vector2(r.width*.40f,r.height*.39f),2.0f,Mathf.PI*.05f,Mathf.PI*.95f,
                    new Color(.73f,.93f,1f,.095f),20);
            }
        }
    }
}
