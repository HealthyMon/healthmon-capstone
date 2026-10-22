using System.Collections;
using UnityEngine;

public class WearableTestController : MonoBehaviour
{
    [SerializeField]
    private float pollingInterval = 1.0f;

    private void Start()
    {
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority) return;
        Debug.Log("HealthMon LOCAL DEMO wearable diagnostics");

        HealthMonAndroidBridge.Initialize();
        Debug.Log("HealthMon TEST 2 - Initialize OK");

        int count = HealthMonAndroidBridge.GetPendingWorkoutCount();

        Debug.Log(
            $"HealthMon TEST 3 - Pending count = {count}"
        );

        try
        {
            bool requested = HealthMonAndroidBridge.RequestLiveWorkoutState();

            Debug.Log($"HealthMon TEST 4 - Live request sent = {requested}");
        }
        catch (System.Exception e)
        {
            Debug.LogError($"HealthMon TEST ERROR - Request: {e}");
        }

        Debug.Log("HealthMon TEST 5 - Coroutine start");

        StartCoroutine(PollLiveWorkoutState());
    }

    private IEnumerator PollLiveWorkoutState()
    {
        while (true)
        {
            Debug.Log("HealthMon TEST 6 - Poll");

            try
            {
                string json = HealthMonAndroidBridge.GetLatestLiveWorkoutState();

                if (string.IsNullOrEmpty(json))
                {
                    Debug.Log("HealthMon live state = null");
                }
                else
                {
                    Debug.Log("HealthMon live state received (payload omitted).");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogError($"HealthMon TEST ERROR - Poll: {e}");
            }

            yield return new WaitForSeconds(pollingInterval);
        }
    }
}