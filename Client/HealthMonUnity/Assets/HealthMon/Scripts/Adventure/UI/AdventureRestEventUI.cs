using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// 일반층의 Rest 이벤트 전용 UI. 10층마다 발생하는 체크포인트 휴식과는 별개.
public class AdventureRestEventUI : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private GameObject restPanel;
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text recoveryDescriptionText;
    [SerializeField] private TMP_Text statDescriptionText;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private Button recoveryButton;
    [SerializeField] private Button statButton;

    private Action<bool> chooseCallback;
    private bool pending;

    private void Awake()
    {
        if (restPanel != null) restPanel.SetActive(false);
        if (recoveryButton != null) recoveryButton.onClick.AddListener(ChooseRecovery);
        if (statButton != null) statButton.onClick.AddListener(ChooseStat);
    }

    private void OnDestroy()
    {
        if (recoveryButton != null) recoveryButton.onClick.RemoveListener(ChooseRecovery);
        if (statButton != null) statButton.onClick.RemoveListener(ChooseStat);
    }

    public bool BeginRest(int floor, string recoveryText, string statText, Action<bool> onChoose)
    {
        if (pending || restPanel == null || recoveryButton == null || statButton == null || onChoose == null)
            return false;

        chooseCallback = onChoose;
        pending = true;
        if (titleText != null) titleText.text = $"{floor}층 · 휴식 이벤트";
        if (recoveryDescriptionText != null) recoveryDescriptionText.text = recoveryText;
        if (statDescriptionText != null) statDescriptionText.text = statText;
        if (statusText != null) statusText.text = "두 선택지 중 하나를 선택하세요.";
        recoveryButton.interactable = true;
        statButton.interactable = true;
        restPanel.SetActive(true);
        return true;
    }

    private void ChooseRecovery() => Choose(true);
    private void ChooseStat() => Choose(false);

    private void Choose(bool recovery)
    {
        if (!pending || chooseCallback == null) return;
        recoveryButton.interactable = false;
        statButton.interactable = false;
        chooseCallback.Invoke(recovery);
        // 정상 처리 시 AdventureManager가 FinishRest()를 호출한다.
        if (pending)
        {
            if (statusText != null) statusText.text = "처리에 실패했습니다. 다시 선택해 주세요.";
            recoveryButton.interactable = true;
            statButton.interactable = true;
        }
    }

    public void FinishRest()
    {
        pending = false;
        chooseCallback = null;
        if (restPanel != null) restPanel.SetActive(false);
    }
}
