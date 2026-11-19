using System.Collections;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEngine;

public class WorkoutHistoryController : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private TMP_Text countText;
    [SerializeField] private Transform content;
    [SerializeField] private WorkoutRecordItemUI itemPrefab;

    private Coroutine pendingRefresh;
    private int requestVersion;

    private void OnEnable()
    {
        RefreshWorkoutList();
    }

    private void OnDisable()
    {
        requestVersion++;
        if (pendingRefresh != null)
        {
            StopCoroutine(pendingRefresh);
            pendingRefresh = null;
        }
    }

    // Keep this method name: WearablePageController calls it after a workout ends.
    public void RefreshWorkoutList()
    {
        requestVersion++;
        if (pendingRefresh != null) StopCoroutine(pendingRefresh);
        if (!isActiveAndEnabled) return;
        pendingRefresh = StartCoroutine(LoadFromServer(requestVersion));
    }

    private IEnumerator LoadFromServer(int version)
    {
        countText.text = "서버 운동 기록을 불러오는 중...";
        var connection = CommonServerConnection.Instance;
        // A newly started app may still be authenticating. Wait briefly rather than
        // falling back to private phone Room records.
        float deadline = Time.realtimeSinceStartup + 12f;
        while (version == requestVersion &&
               (connection == null || !connection.IsConnected || connection.Api == null || connection.Api.IsBusy) &&
               Time.realtimeSinceStartup < deadline)
        {
            yield return new WaitForSecondsRealtime(0.3f);
            connection = CommonServerConnection.Instance;
        }

        pendingRefresh = null;
        if (version != requestVersion) yield break;
        if (connection == null || !connection.IsConnected || connection.Api == null)
        {
            countText.text = "서버 연결 후 운동 기록을 조회할 수 있습니다.";
            Debug.LogWarning("[ServerWorkouts] History page: server not connected");
            yield break;
        }
        if (connection.Api.IsBusy)
        {
            countText.text = "다른 서버 요청 중입니다. 다시 조회해 주세요.";
            Debug.LogWarning("[ServerWorkouts] History page: API busy");
            yield break;
        }

        var api = connection.Api;
        string requestedPet = api.PetId;
        api.GetWorkouts(
            result =>
            {
                if (this == null || !isActiveAndEnabled || version != requestVersion ||
                    !connection.IsConnected || connection.Api != api || api.PetId != requestedPet)
                    return;
                ClearList();
                var records = result != null ? result.records : null;
                int displayed = 0;
                if (records != null)
                {
                    foreach (var record in records)
                    {
                        if (record == null || record.record == null) continue;
                        var item = Instantiate(itemPrefab, content);
                        item.SetServerData(record, ++displayed);
                    }
                }
                countText.text = $"총 기록 수: {displayed}";
                Debug.Log($"[ServerWorkouts] History loaded {displayed} records");
            },
            error =>
            {
                if (this == null || !isActiveAndEnabled || version != requestVersion) return;
                countText.text = "서버 운동 기록을 가져오지 못했습니다.";
                Debug.LogWarning($"[ServerWorkouts] History request failed: HTTP {error.StatusCode}");
            });
    }

    private void ClearList()
    {
        for (int i = content.childCount - 1; i >= 0; i--)
            Destroy(content.GetChild(i).gameObject);
    }
}
