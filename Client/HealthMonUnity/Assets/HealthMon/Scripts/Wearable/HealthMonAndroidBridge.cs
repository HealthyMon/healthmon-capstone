using UnityEngine;

public static class HealthMonAndroidBridge
{
    private const string BridgeClassName = "com.healthmon.capstone.mobile.unity.HealthMonUnityBridge";

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
