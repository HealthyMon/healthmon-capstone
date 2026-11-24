using System.Collections;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class WorkoutHistoryController : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private TMP_Text countText;
    [SerializeField] private Transform content;
    [SerializeField] private WorkoutRecordItemUI itemPrefab;

    private Coroutine pendingRefresh;
    private int requestVersion;
    private string displayedScope;

    private static string CurrentScope
    {
        get
        {
            if (!CommonServerConnection.UsesServerAuthority) return "offline";
            var connection = CommonServerConnection.Instance;
            return connection == null || !connection.IsConnected ? "disconnected" :
                connection.ServerInstanceId + ":" + connection.OwnerId + ":" + connection.Api?.PetId;
        }
    }

    private void OnEnable()
    {
        LayoutHistory();
        RefreshWorkoutList();
    }

    private void LayoutHistory()
    {
        if (countText == null) return;
        var page = countText.transform.parent as RectTransform;
        var unusedTabs = page.parent.Find("TabBar");
        if (unusedTabs != null && unusedTabs.childCount == 0) unusedTabs.gameObject.SetActive(false);
        HealthMonUILayout.Place(page, .05f, .17f, .95f, .97f);
        HealthMonUILayout.Text(page.Find("TitleText")?.GetComponent<TMP_Text>(), .06f, .90f, .67f, .98f, 42);
        HealthMonUILayout.Text(countText, .06f, .82f, .68f, .90f, 28);
        var refresh = page.Find("RefresthButton") as RectTransform;
        HealthMonUILayout.Place(refresh, .72f, .85f, .94f, .94f);
        if (refresh != null)
        {
            var label = refresh.GetComponentInChildren<Text>(true);
            if (label != null) { label.resizeTextForBestFit = true; label.resizeTextMinSize = 16; label.resizeTextMaxSize = 26; }
        }
        HealthMonUILayout.Place(page.Find("Scroll View") as RectTransform, .04f, .04f, .96f, .80f);
        if (page.Find("EmptyHistory") == null)
        {
            var empty = new GameObject("EmptyHistory", typeof(RectTransform), typeof(TextMeshProUGUI));
            empty.transform.SetParent(page, false);
            var label = empty.GetComponent<TMP_Text>(); label.font = countText.font;
            label.color = new Color(.82f, .91f, 1);
            label.alignment = TextAlignmentOptions.Center;
            HealthMonUILayout.Text(label, .12f, .38f, .88f, .55f, 30);
            label.text = "아직 기록이 없다!\n훈련을 완료해 첫 기록을 남겨라.";
            empty.SetActive(false);
        }
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

    private void Update()
    {
        if (displayedScope != CurrentScope) RefreshWorkoutList();
    }

    // Keep this method name: WearablePageController calls it after a workout ends.
    public void RefreshWorkoutList()
    {
        requestVersion++;
        if (pendingRefresh != null) StopCoroutine(pendingRefresh);
        pendingRefresh = null;
        if (!isActiveAndEnabled) return;
        displayedScope = CurrentScope;
        ClearList();
        if (countText == null || content == null || itemPrefab == null) return;
        if (!CommonServerConnection.UsesServerAuthority)
        {
            LoadLocalRecords();
            return;
        }
        pendingRefresh = StartCoroutine(LoadFromServer(requestVersion));
    }

    private void LoadLocalRecords()
    {
        // Phone records are shown only in explicitly selected offline mode.
        // A server failure must never reveal another account's local history.
        try
        {
            string json = HealthMonAndroidBridge.GetPendingWorkoutResults();
            // The Editor bridge and some Android versions return a bare array.
            if (string.IsNullOrWhiteSpace(json)) json = "[]";
            if (json.TrimStart().StartsWith("[")) json = "{\"items\":" + json + "}";
            var history = JsonUtility.FromJson<WorkoutRecordDataList>(json);
            int displayed = 0;
            foreach (var record in history?.items ?? new WorkoutRecordData[0])
            {
                if (record == null) continue;
                Instantiate(itemPrefab, content).SetData(record, ++displayed);
            }
            countText.text = $"기기 운동 기록 · {displayed}";
            countText.transform.parent.Find("EmptyHistory")?.gameObject.SetActive(displayed == 0);
        }
        catch (System.Exception)
        {
            countText.text = "기기 운동 기록 조회 실패";
        }
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
        string requestedScope = CurrentScope;
        api.GetWorkouts(
            result =>
            {
                if (this == null || !isActiveAndEnabled || version != requestVersion ||
                    !connection.IsConnected || connection.Api != api || api.PetId != requestedPet ||
                    CurrentScope != requestedScope)
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
                if (this == null || !isActiveAndEnabled || version != requestVersion || CurrentScope != requestedScope) return;
                countText.text = "서버 운동 기록을 가져오지 못했습니다.";
                Debug.LogWarning($"[ServerWorkouts] History request failed: HTTP {error.StatusCode}");
            });
    }

    private void ClearList()
    {
        countText?.transform.parent.Find("EmptyHistory")?.gameObject.SetActive(false);
        if (content == null) return;
        for (int i = content.childCount - 1; i >= 0; i--)
        {
            var item = content.GetChild(i).gameObject;
            item.SetActive(false);
            Destroy(item);
        }
    }
}
