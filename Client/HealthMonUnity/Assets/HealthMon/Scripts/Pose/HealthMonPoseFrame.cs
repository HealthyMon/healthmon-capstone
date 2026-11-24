using System;

/// <summary>Bottom-left pixel coordinates from WebCamTexture to upright, bounded JPEG pixels.</summary>
public static class HealthMonPoseFrame
{
    public static void GetSize(int width,int height,int rotation,int maxSide,out int outWidth,out int outHeight)
    {
        int w=rotation==90||rotation==270?height:width,h=rotation==90||rotation==270?width:height;
        float scale=Math.Min(1f,(float)maxSide/Math.Max(w,h));
        outWidth=Math.Max(1,(int)Math.Round(w*scale));outHeight=Math.Max(1,(int)Math.Round(h*scale));
    }
    public static void CopyUpright<T>(T[] input,T[] output,int width,int height,int rotation,bool verticalMirror,int outWidth,int outHeight)
    {
        int uprightWidth=rotation==90||rotation==270?height:width,uprightHeight=rotation==90||rotation==270?width:height;
        for(int dy=0;dy<outHeight;dy++)for(int dx=0;dx<outWidth;dx++)
        {
            int x=dx*uprightWidth/outWidth,y=dy*uprightHeight/outHeight,sx=x,sy=y;
            if(rotation==90){sx=width-1-y;sy=x;}
            else if(rotation==180){sx=width-1-x;sy=height-1-y;}
            else if(rotation==270){sx=y;sy=height-1-x;}
            if(verticalMirror)sy=height-1-sy;
            output[dy*outWidth+dx]=input[sy*width+sx];
        }
    }
}
