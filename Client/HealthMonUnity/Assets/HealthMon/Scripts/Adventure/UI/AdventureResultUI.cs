using System;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class AdventureResultUI : MonoBehaviour
{
    [Header("Scene references")]
    [SerializeField] private AdventureManager adventureManager;
    [SerializeField] private GameObject resultPanel;
    [Header("Result fields")]
    [SerializeField] private TMP_Text reachedFloorText, reasonText, rangeText;
    [SerializeField] private TMP_Text clearedText, enemiesText, bossesText, eventsText, timeText;
    [SerializeField] private TMP_Text hpText, stText, rewardText;
    [SerializeField] private Image hpFill, stFill;
    [Header("Return")]
    [SerializeField] private Button returnButton;
    [SerializeField] private string mainSceneName;
    [SerializeField] private UnityEvent onReturnRequested = new UnityEvent();
    private bool displayed;
    private bool returning;

    private void Awake()
    {
        if (resultPanel != null) resultPanel.SetActive(false);
        if (returnButton != null) returnButton.onClick.AddListener(ReturnToMain);
    }
    private void OnEnable()
    {
        if (adventureManager != null)
        {
            adventureManager.AdventureEnded += Show;
            if (adventureManager.LastResult != null) Show(adventureManager.LastResult);
        }
    }
    private void Start()
    {
        if (adventureManager == null || resultPanel == null)
            Debug.LogError("[AdventureResultUI] Manager or ResultPanel is missing", this);
    }
    private void OnDisable()
    {
        if (adventureManager != null) adventureManager.AdventureEnded -= Show;
    }
    private void OnDestroy()
    {
        if (returnButton != null) returnButton.onClick.RemoveListener(ReturnToMain);
    }
    public void Show(AdventureResultData data)
    {
        if (data == null || resultPanel == null) return;
        displayed = true;
        returning = false;
        bool defeat = data.endReason == AdventureEndReason.Defeat;
        Set(reachedFloorText, $"{data.reachedFloor}F");
        Set(reasonText, defeat ? "전투 패배" : "탐험 종료");
        if (reasonText != null) reasonText.color = defeat ? new Color32(255, 160, 160, 255) : new Color32(151, 222, 173, 255);
        Set(rangeText, $"{Mathf.Max(1, data.startFloor)}F ~ {data.reachedFloor}F");
        Set(clearedText, $"{data.sessionClearedFloors}층");
        Set(enemiesText, $"{data.sessionDefeatedEnemies}마리");
        Set(bossesText, $"{data.sessionDefeatedBosses}마리");
        Set(eventsText, $"{data.sessionCompletedEvents}개");
        var duration = TimeSpan.FromSeconds(Math.Max(0, data.elapsedSeconds));
        Set(timeText, $"{(int)duration.TotalHours:00}:{duration.Minutes:00}:{duration.Seconds:00}");
        var stats = data.playerStats;
        Set(hpText, stats == null ? "-" : $"{stats.currentHP} / {stats.maxHP}");
        Set(stText, stats == null ? "-" : $"{stats.currentST:0.##} / {stats.maxST:0.##}");
        Fill(hpFill, stats != null && stats.maxHP > 0 ? (float)stats.currentHP / stats.maxHP : 0);
        Fill(stFill, stats != null && stats.maxST > 0 ? stats.currentST / stats.maxST : 0);
        Set(rewardText, "보상 시스템 연동 예정");
        if (returnButton != null) returnButton.interactable = CanReturn();
        resultPanel.SetActive(true);
    }
    public void SetRewardText(string value) => Set(rewardText, value);
    private bool CanReturn() => !string.IsNullOrWhiteSpace(mainSceneName) || (onReturnRequested != null && onReturnRequested.GetPersistentEventCount() > 0);
    public void ReturnToMain()
    {
        if (!displayed || returning || !CanReturn()) return;
        returning = true;
        if (returnButton != null) returnButton.interactable = false;
        // A custom navigation callback takes priority over direct scene loading.
        if (onReturnRequested != null && onReturnRequested.GetPersistentEventCount() > 0)
        {
            onReturnRequested.Invoke();
            return;
        }
        if (!Application.CanStreamedLevelBeLoaded(mainSceneName))
        {
            Debug.LogError($"[AdventureResultUI] Scene not in build: {mainSceneName}", this);
            returning = false;
            if (returnButton != null) returnButton.interactable = true;
            return;
        }
        SceneManager.LoadScene(mainSceneName);
    }
    private static void Set(TMP_Text target, string value) { if (target != null) target.text = value; }
    private static void Fill(Image target, float value) { if (target != null) { var rect = target.rectTransform; rect.anchorMax = new Vector2(Mathf.Clamp01(value), 1f); } }
}
