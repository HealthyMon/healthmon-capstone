using TMPro;
using UnityEngine;

public class WorkoutHistoryController : MonoBehaviour
{
    [Header("UI")]
    [SerializeField]
    private TMP_Text countText;

    [SerializeField]
    private Transform content;

    [SerializeField]
    private WorkoutRecordItemUI itemPrefab;

    private void Start()
    {
        RefreshWorkoutList();
    }

    public void RefreshWorkoutList()
    {
        ClearList();

        string json =
            HealthMonAndroidBridge
                .GetPendingWorkoutResults();

        Debug.Log(
            $"HealthMon workout history JSON = {json}"
        );

        if (string.IsNullOrEmpty(json) ||
            json == "[]")
        {
            countText.text =
                "ÃÑ ±â·Ï ¼ö: 0";

            return;
        }

        string wrappedJson =
            "{\"items\":" + json + "}";

        WorkoutRecordDataList result =
            JsonUtility.FromJson<WorkoutRecordDataList>(
                wrappedJson
            );

        if (result == null ||
            result.items == null)
        {
            countText.text =
                "ÃÑ ±â·Ï ¼ö: 0";

            return;
        }

        countText.text =
            $"ÃÑ ±â·Ï ¼ö: {result.items.Length}";

        for (
            int i = 0;
            i < result.items.Length;
            i++
        )
        {
            WorkoutRecordItemUI item =
                Instantiate(
                    itemPrefab,
                    content
                );

            item.SetData(
                result.items[i],
                i + 1
            );
        }
    }

    private void ClearList()
    {
        for (
            int i = content.childCount - 1;
            i >= 0;
            i--
        )
        {
            Destroy(
                content.GetChild(i).gameObject
            );
        }
    }
}