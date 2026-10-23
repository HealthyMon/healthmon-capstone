using UnityEngine;

public static class HealthMonAndroidBridge
{
    private const string BridgeClassName = "com.healthmon.capstone.mobile.unity.HealthMonUnityBridge";

    public static bool IsAndroidDevice
    {
        get {
#if UNITY_ANDROID && !UNITY_EDITOR
            return true;
#else
            return false;
#endif
        }
    }
    // These calls may execute on Task.Run. Every worker explicitly attaches to the JVM.
    private static T CallSync<T>(string method, params object[] args)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        using (var bridge = new AndroidJavaClass(BridgeClassName)) return bridge.CallStatic<T>(method, args);
#else
        return default(T);
#endif
    }
    public static string ConfigureServerSync(string url, string token, string petId)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        AndroidJNI.AttachCurrentThread();
        try { return CallSync<string>("configureServerSync", url, token, petId); }
        finally { AndroidJNI.DetachCurrentThread(); }
#else
        return null;
#endif
    }
    public static bool ClearServerSync() { return CallSync<bool>("clearServerSync"); }
    public static bool RequestServerSync() { return CallSync<bool>("requestServerSync"); }
    public static string GetServerSyncStatus()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        AndroidJNI.AttachCurrentThread();
        try { return CallSync<string>("getServerSyncStatus"); }
        finally { AndroidJNI.DetachCurrentThread(); }
#else
        return null;
#endif
    }
    public static bool ConfirmWorkoutUpload(string workoutId) { return CallSync<bool>("confirmWorkoutUpload", workoutId); }

    public static void Initialize()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
            using AndroidJavaClass unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
            AndroidJavaObject activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity");
            using AndroidJavaClass bridge = new AndroidJavaClass(BridgeClassName);

            bridge.CallStatic("initialize", activity);
#else
        Debug.Log("HealthMonAndroidBridge.Initialize - Editor");
#endif
    }

    public static int GetPendingWorkoutCount()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
                using AndroidJavaClass bridge = new AndroidJavaClass(BridgeClassName);

                return bridge.CallStatic<int>("getPendingWorkoutCount");
#else
        return 0;
#endif
    }

    public static bool RequestLiveWorkoutState()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
    using AndroidJavaClass bridge =
        new AndroidJavaClass(BridgeClassName);

    return bridge.CallStatic<bool>("requestLiveWorkoutState");
#else
        return false;
#endif
    }

    public static string GetLatestLiveWorkoutState()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
                using AndroidJavaClass bridge = new AndroidJavaClass(BridgeClassName);

                return bridge.CallStatic<string>("getLatestLiveWorkoutState");
#else
        return null;
#endif
    }

    public static string GetPendingWorkoutResults()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
    using AndroidJavaClass bridge =
        new AndroidJavaClass(BridgeClassName);

    return bridge.CallStatic<string>(
        "getPendingWorkoutResults"
    );
#else
        return "[]";
#endif
    }
}
