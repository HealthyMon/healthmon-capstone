using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class HealthMonAndroidBuild
{
    [MenuItem("HealthMon/Pose/Build Android preview APK")]
    public static void BuildPreview()
    {
        if(!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Android,BuildTarget.Android))
            throw new BuildFailedException("Install Android Build Support for this exact Unity version first.");
        var target=NamedBuildTarget.Android;
        var oldId=PlayerSettings.GetApplicationIdentifier(target);
        var oldInternet=PlayerSettings.Android.forceInternetPermission;
        var oldHttp=PlayerSettings.insecureHttpOption;
        var oldBackend=PlayerSettings.GetScriptingBackend(target);
        var oldArchitectures=PlayerSettings.Android.targetArchitectures;
        var oldBundle=EditorUserBuildSettings.buildAppBundle;
        var oldPreloaded=PlayerSettings.GetPreloadedAssets();
        string root=Directory.GetParent(Application.dataPath).Parent.Parent.FullName;
        string output=Environment.GetEnvironmentVariable("HEALTHMON_ANDROID_APK")??Path.Combine(root,".runtime/apk/HealthMon-Pose-Android.apk");
        Directory.CreateDirectory(Path.GetDirectoryName(output));
        try
        {
            // Separate development package preserves the user's installed game and saves.
            PlayerSettings.SetApplicationIdentifier(target,"com.healthmon.capstone.posepreview");
            PlayerSettings.Android.forceInternetPermission=true;
            PlayerSettings.insecureHttpOption=InsecureHttpOption.DevelopmentOnly;
            PlayerSettings.SetScriptingBackend(target,ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures=AndroidArchitecture.ARM64;
            EditorUserBuildSettings.buildAppBundle=false;
            var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes=EditorBuildSettings.scenes.Where(s=>s.enabled).Select(s=>s.path).ToArray(),
                locationPathName=output,target=BuildTarget.Android,options=BuildOptions.Development
            });
            if(report.summary.result!=BuildResult.Succeeded)throw new BuildFailedException("Android preview build failed: "+report.summary.result);
            Debug.Log("HEALTHMON_ANDROID_APK_PASS "+output);
        }
        finally
        {
            PlayerSettings.SetApplicationIdentifier(target,oldId);
            PlayerSettings.Android.forceInternetPermission=oldInternet;
            PlayerSettings.insecureHttpOption=oldHttp;
            PlayerSettings.SetScriptingBackend(target,oldBackend);
            PlayerSettings.Android.targetArchitectures=oldArchitectures;
            EditorUserBuildSettings.buildAppBundle=oldBundle;
            PlayerSettings.SetPreloadedAssets(oldPreloaded);
            AssetDatabase.SaveAssets();
        }
    }
}

#if UNITY_ANDROID
// Only the separate local preview package needs HTTP to an adb loopback tunnel.
public sealed class HealthMonPoseAndroidNetwork : UnityEditor.Android.IPostGenerateGradleAndroidProject
{
    public int callbackOrder => 100;
    public void OnPostGenerateGradleAndroidProject(string path)
    {
        if(PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.Android)!="com.healthmon.capstone.posepreview")return;
        const string android="http://schemas.android.com/apk/res/android";
        string manifest=Path.Combine(path,"src/main/AndroidManifest.xml");
        var xml=new System.Xml.XmlDocument();xml.Load(manifest);
        var application=(System.Xml.XmlElement)xml.SelectSingleNode("/manifest/application");
        var existing=application.GetAttribute("networkSecurityConfig",android);
        if(existing.Length>0&&existing!="@xml/healthmon_pose_network")throw new BuildFailedException("Preview network config conflicts with existing config: "+existing);
        application.SetAttribute("networkSecurityConfig",android,"@xml/healthmon_pose_network");xml.Save(manifest);
        string folder=Path.Combine(path,"src/main/res/xml");Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,"healthmon_pose_network.xml"),
            "<network-security-config><base-config cleartextTrafficPermitted=\"false\"/>"+
            "<domain-config cleartextTrafficPermitted=\"true\"><domain>127.0.0.1</domain><domain>localhost</domain><domain>::1</domain></domain-config></network-security-config>");
    }
}
#endif
