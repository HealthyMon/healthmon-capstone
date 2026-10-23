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

    public void ApplyPortraitLayout(PortraitGameUI theme, Rect area)
    {
        if (countText != null)
        {
            theme.Place(countText.rectTransform, new Rect(area.x + 35, area.yMax - 135, area.width - 70, 100));
            countText.color = PortraitGameUI.Ink; countText.fontSizeMax = 38;
        }
        if (content == null) return;
        var scroll = content.GetComponentInParent<UnityEngine.UI.ScrollRect>();
        if (scroll != null) theme.Place((RectTransform)scroll.transform, new Rect(area.x + 25, area.y + 25, area.width - 50, area.height - 180));
        foreach (Transform item in content)
        {
            var layout = item.GetComponent<UnityEngine.UI.LayoutElement>() ?? item.gameObject.AddComponent<UnityEngine.UI.LayoutElement>();
            layout.preferredHeight = 260;
        }
    }

    public void RefreshWorkoutList()
    {
        ClearList();

        string json =
            HealthMonAndroidBridge
                .GetPendingWorkoutResults();

        // Health records must not be copied into logs.

        if (string.IsNullOrEmpty(json) ||
            json == "[]")
        {
            countText.text =
                "총 기록 수: 0";

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
                "총 기록 수: 0";

            return;
        }

        countText.text =
            $"총 기록 수: {result.items.Length}";

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
