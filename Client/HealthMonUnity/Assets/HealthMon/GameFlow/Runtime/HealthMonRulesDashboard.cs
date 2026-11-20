using System;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using Healthmon.Common;

/// <summary>Small display/recording UI and explicitly-confirmed offline experiment reset.</summary>
[DisallowMultipleComponent]
public sealed class HealthMonRulesDashboard : MonoBehaviour
{
    public HealthMonGameRules rules;
    public UIManager uiManager;
    public GameObject rulesOverlay, resetConfirm, adminLauncher, adminPanel;
    public Button openButton, closeButton, upperButton, cardioButton, evolutionButton, resetOpenButton, resetCancelButton, resetConfirmButton;
    public TMP_InputField upperInput, cardioInput, resetPhrase;
    public TMP_Text summary, note, adminFeedback;
    private float nextRefresh;
    private bool wired;

    private void Start()
    {
        if (rules == null) rules = FindFirstObjectByType<HealthMonGameRules>(FindObjectsInactive.Include);
        if (uiManager == null) uiManager = FindFirstObjectByType<UIManager>(FindObjectsInactive.Include);
        if (!wired)
        {
            wired = true;
            if (openButton) openButton.onClick.AddListener(Open);
            if (closeButton) closeButton.onClick.AddListener(Close);
            if (upperButton) upperButton.onClick.AddListener(RecordUpper);
            if (cardioButton) cardioButton.onClick.AddListener(RecordCardio);
            if (evolutionButton) evolutionButton.onClick.AddListener(ApplyStage);
            if (resetOpenButton) resetOpenButton.onClick.AddListener(OpenReset);
            if (resetCancelButton) resetCancelButton.onClick.AddListener(CloseReset);
            if (resetConfirmButton) resetConfirmButton.onClick.AddListener(DoReset);
        }
        if (rulesOverlay) rulesOverlay.SetActive(false);
        if (resetConfirm) resetConfirm.SetActive(false);
    }
    private void Update()
    {
        if (adminLauncher != null && adminPanel != null)
        {
            bool shouldShow = adminPanel.activeInHierarchy;
            if (adminLauncher.activeSelf != shouldShow) adminLauncher.SetActive(shouldShow);
        }
        if (Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + .8f;
        Refresh();
    }
    public void Open() { if (rulesOverlay) rulesOverlay.SetActive(true); Refresh(); }
    public void Close() { if (rulesOverlay) rulesOverlay.SetActive(false); }
    private void Refresh()
    {
        bool offline = rules != null && rules.IsOffline;
        if (summary) summary.text = rules == null ? "성장 기록을 불러올 수 없음" : offline
            ? rules.GetSummary() : "서버 연결 중 · 성장 정보는 홈에서 확인\n\n이 화면은 로컬 플레이 기록 전용";
        if (upperInput) upperInput.interactable = offline;
        if (cardioInput) cardioInput.interactable = offline;
        if (upperButton) upperButton.interactable = offline;
        if (cardioButton) cardioButton.interactable = offline;
        if (evolutionButton) evolutionButton.interactable = rules != null && rules.IsOffline && rules.NextEligibleStage() > 0;
        if (resetConfirmButton) resetConfirmButton.interactable = resetPhrase != null && resetPhrase.text.Trim() == "초기화";
    }
    private void RecordUpper()
    {
        if (rules == null || !rules.IsOffline || upperInput == null) return;
        if (int.TryParse(upperInput.text, out var count) && count >= 1 && count <= 1000)
        { rules.RecordUpper(count); upperInput.text = ""; Feedback("상체 운동 " + count + "회 기록 완료"); }
        else Feedback("상체 운동량 · 1~1,000회 입력");
        Refresh();
    }
    private void RecordCardio()
    {
        if (rules == null || !rules.IsOffline || cardioInput == null) return;
        if (int.TryParse(cardioInput.text, out var count) && count >= 1 && count <= 300)
        { rules.RecordCardio(count); cardioInput.text = ""; Feedback("유산소 " + count + "분 기록 완료"); }
        else Feedback("유산소 운동량 · 1~300분 입력");
        Refresh();
    }
    private void ApplyStage()
    {
        if (rules == null || rules.NextEligibleStage() <= 0) return;
        rules.AdvanceOfflineStage();
        Feedback("성장 단계 상승 완료");
        Refresh();
    }
    private void Feedback(string message) { if (note) note.text = message; }
    public void OpenReset()
    {
        if (CommonServerConnection.UsesServerAuthority)
        { if (adminFeedback) adminFeedback.text = "서버 모드에서는 로컬 초기화를 지원하지 않습니다."; return; }
        if (resetPhrase) resetPhrase.text = "";
        if (resetConfirm) resetConfirm.SetActive(true);
    }
    public void CloseReset() { if (resetConfirm) resetConfirm.SetActive(false); }
    private void DoReset()
    {
        if (CommonServerConnection.UsesServerAuthority || resetPhrase == null || resetPhrase.text.Trim() != "초기화") return;
        HealthMonGameReset.MarkAndReset();
        if (adminFeedback) adminFeedback.text = "로컬 기록 초기화 완료 · 게임 재시작 필요";
        Debug.Log("[HealthMonRules] OFFLINE test reset: game-owned PlayerPrefs keys cleared. Server records untouched.");
        CloseReset();
        #if UNITY_EDITOR
        // A fresh Play session avoids DontDestroyOnLoad profile and current in-memory daily data.
        UnityEditor.EditorApplication.isPlaying = false;
        #else
        Application.Quit(); // launch again to trigger guaranteed post-quit cleanup
        #endif
    }
}
