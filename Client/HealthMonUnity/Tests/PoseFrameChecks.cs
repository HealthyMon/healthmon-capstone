using System;
public static class PoseFrameChecks
{
    static int checks;
    static void Equal(int[] got,params int[] expected)
    {
        if(string.Join(",",got)!=string.Join(",",expected))throw new Exception("Camera orientation mismatch: "+string.Join(",",got));
        checks++;
    }
    public static void Main()
    {
        // Bottom row A B C, top row D E F. Independent expected clockwise rotations.
        var source=new[]{1,2,3,4,5,6};var target=new int[6];
        HealthMonPoseFrame.CopyUpright(source,target,3,2,0,false,3,2);Equal(target,1,2,3,4,5,6);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,90,false,2,3);Equal(target,3,6,2,5,1,4);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,180,false,3,2);Equal(target,6,5,4,3,2,1);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,270,false,2,3);Equal(target,4,1,5,2,6,3);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,0,true,3,2);Equal(target,4,5,6,1,2,3);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,90,true,2,3);Equal(target,6,3,5,2,4,1);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,180,true,3,2);Equal(target,3,2,1,6,5,4);
        HealthMonPoseFrame.CopyUpright(source,target,3,2,270,true,2,3);Equal(target,1,4,2,5,3,6);
        HealthMonPoseFrame.GetSize(1920,1080,90,960,out int w,out int h);Equal(new[]{w,h},540,960);
        HealthMonPoseFrame.GetSize(640,480,270,960,out w,out h);Equal(new[]{w,h},480,640);
        target=new int[2];HealthMonPoseFrame.CopyUpright(source,target,3,2,90,false,1,2);Equal(target,3,2);
        Console.WriteLine("HEALTHMON_POSE_FRAME_PASS checks="+checks);
    }
}
