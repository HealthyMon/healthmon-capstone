using UnityEngine;
using UnityEngine.UI;

namespace HealthMon.Evolution
{
    /// <summary>Small procedural primitives. No PNG/Sprite dependency; built with uGUI vertex colors.</summary>
    public static class EvolutionMesh
    {
        public static void Vert(VertexHelper vh, Vector2 p, Color c)
        {
            UIVertex v = UIVertex.simpleVert;
            v.position = new Vector3(p.x, p.y, 0f);
            v.color = c;
            v.uv0 = new Vector2(.5f, .5f);
            vh.AddVert(v);
        }

        public static void Quad(VertexHelper vh, Vector2 bl, Vector2 br, Vector2 tr, Vector2 tl,
            Color cbl, Color cbr, Color ctr, Color ctl)
        {
            int k = vh.currentVertCount;
            Vert(vh, bl, cbl); Vert(vh, br, cbr);
            Vert(vh, tr, ctr); Vert(vh, tl, ctl);
            vh.AddTriangle(k, k + 1, k + 2); vh.AddTriangle(k, k + 2, k + 3);
        }

        public static void RectGradient(VertexHelper vh, Rect r, Color bottom, Color top)
        {
            Quad(vh, new Vector2(r.xMin,r.yMin),new Vector2(r.xMax,r.yMin),
                new Vector2(r.xMax,r.yMax),new Vector2(r.xMin,r.yMax),bottom,bottom,top,top);
        }

        public static void Ellipse(VertexHelper vh, Vector2 center, Vector2 radii,
            Color middle, Color edge, int segments = 64)
        {
            int k = vh.currentVertCount;
            Vert(vh, center, middle);
            for (int i=0; i<=segments; i++)
            {
                float a = i * (Mathf.PI*2f)/segments;
                Vert(vh, center + new Vector2(Mathf.Cos(a)*radii.x,Mathf.Sin(a)*radii.y), edge);
                if (i>0) vh.AddTriangle(k,k+i,k+i+1);
            }
        }

        public static void EllipseSoft(VertexHelper vh, Vector2 center, Vector2 r, Color tint, int segments = 64)
        {
            for (int b=0; b<4; b++)
            {
                float inner = b * .25f;
                float outer = (b+1)*.25f;
                float a0 = b == 0 ? tint.a : tint.a * Mathf.Pow(1f-inner,1.1f);
                float a1 = tint.a * Mathf.Pow(1f-outer,1.6f);
                Ring(vh,center,new Vector2(r.x*inner,r.y*inner),
                    new Vector2(r.x*outer,r.y*outer),
                    new Color(tint.r,tint.g,tint.b,a0),new Color(tint.r,tint.g,tint.b,a1),segments);
            }
        }

        public static void Ring(VertexHelper vh, Vector2 center, Vector2 inner, Vector2 outer,
            Color cin, Color cout, int segments=96)
        {
            for (int i=0; i<segments; i++)
            {
                float a=i*2f*Mathf.PI/segments;
                float b=(i+1)*2f*Mathf.PI/segments;
                Vector2 u0 = center + new Vector2(Mathf.Cos(a)*inner.x,Mathf.Sin(a)*inner.y);
                Vector2 v0 = center + new Vector2(Mathf.Cos(a)*outer.x,Mathf.Sin(a)*outer.y);
                Vector2 u1 = center + new Vector2(Mathf.Cos(b)*inner.x,Mathf.Sin(b)*inner.y);
                Vector2 v1 = center + new Vector2(Mathf.Cos(b)*outer.x,Mathf.Sin(b)*outer.y);
                Quad(vh,u0,v0,v1,u1,cin,cout,cout,cin);
            }
        }

        public static void Arc(VertexHelper vh, Vector2 center, Vector2 radii, float width,
            float start, float end, Color col, int segments=60)
        {
            Vector2 inr = new Vector2(Mathf.Max(0,radii.x-width*.5f),Mathf.Max(0,radii.y-width*.5f));
            Vector2 outr = radii + Vector2.one*width*.5f;
            for (int i=0; i<segments; i++)
            {
                float a=Mathf.Lerp(start,end,(float)i/segments);
                float b=Mathf.Lerp(start,end,(float)(i+1)/segments);
                Quad(vh, center + new Vector2(Mathf.Cos(a)*inr.x,Mathf.Sin(a)*inr.y),
                    center + new Vector2(Mathf.Cos(a)*outr.x,Mathf.Sin(a)*outr.y),
                    center + new Vector2(Mathf.Cos(b)*outr.x,Mathf.Sin(b)*outr.y),
                    center + new Vector2(Mathf.Cos(b)*inr.x,Mathf.Sin(b)*inr.y), col,col,col,col);
            }
        }

        public static void Segment(VertexHelper vh, Vector2 p, Vector2 q, float width,
            Color inside, Color outside)
        {
            Vector2 d=q-p;
            if (d.sqrMagnitude<.0001f) return;
            Vector2 n = new Vector2(-d.y,d.x).normalized*width*.5f;
            Quad(vh,p-n,p,q,q-n,outside,inside,inside,outside);
            Quad(vh,p,p+n,q+n,q,inside,outside,outside,inside);
        }

        public static void Rounded(VertexHelper vh, Rect r, float radius, Color fill, int steps=10)
        {
            radius=Mathf.Clamp(radius,0f,Mathf.Min(r.width,r.height)*.5f);
            Vector2 center=r.center;
            int k=vh.currentVertCount;
            Vert(vh,center,fill);
            for(int corner=0;corner<4;corner++)
            {
                float baseDeg=corner*90f;
                Vector2 c=corner==0 ? new Vector2(r.xMax-radius,r.yMax-radius) :
                    corner==1 ? new Vector2(r.xMin+radius,r.yMax-radius) :
                    corner==2 ? new Vector2(r.xMin+radius,r.yMin+radius) :
                    new Vector2(r.xMax-radius,r.yMin+radius);
                for(int i=0;i<=steps;i++)
                {
                    float a=(baseDeg+i*90f/steps)*Mathf.Deg2Rad;
                    Vert(vh,c+new Vector2(Mathf.Cos(a),Mathf.Sin(a))*radius,fill);
                    int idx=corner*(steps+1)+i;
                    if(idx>0) vh.AddTriangle(k,k+idx,k+idx+1);
                }
            }
            // close fan
            int last=vh.currentVertCount-1;
            vh.AddTriangle(k,last,k+1);
        }

        public static void Star(VertexHelper vh, Vector2 p, float size, Color c)
        {
            // Four-point diamond sparkle
            int k=vh.currentVertCount;
            Vert(vh,p,c);
            for(int i=0;i<8;i++)
            {
                float a=i*Mathf.PI/4f;
                float radius = i%2==0?size:size*.22f;
                Vert(vh,p+new Vector2(Mathf.Sin(a)*radius,Mathf.Cos(a)*radius),
                    new Color(c.r,c.g,c.b,i%2==0?0:c.a*.75f));
            }
            for(int i=0;i<8;i++) vh.AddTriangle(k,k+1+i,k+1+((i+1)%8));
        }
    }
}
