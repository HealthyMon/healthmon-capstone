using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class AdventureSpecialEventUI : MonoBehaviour
{
    [SerializeField] private GameObject specialPanel;
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text descriptionText;
    [SerializeField] private Button[] choiceButtons = new Button[3];
    [SerializeField] private TMP_Text[] choiceLabels = new TMP_Text[3];
    [SerializeField] private Button skipButton;
    [SerializeField] private GameObject resultPanel;
    [SerializeField] private TMP_Text resultText;
    [SerializeField] private Button confirmButton;

    private Action<int> onChoice;
    private Action onConfirm;
    private bool pending;
    private bool choosing;

    private void Awake()
    {
        if (specialPanel != null) specialPanel.SetActive(false);
        if (choiceButtons != null)
            for (int i = 0; i < choiceButtons.Length; i++)
            {
                int index = i;
                if (choiceButtons[i] != null) choiceButtons[i].onClick.AddListener(() => Select(index));
            }
        if (skipButton != null) skipButton.onClick.AddListener(() => Select(-1));
        if (confirmButton != null) confirmButton.onClick.AddListener(Confirm);
    }

    public bool Begin(int floor, AdventureSpecialEvent evt, Action<int> callback)
    {
        if (pending || specialPanel == null || evt == null || callback == null || evt.choices == null ||
            evt.choices.Count < 1 || evt.choices.Count > 3 || choiceButtons == null ||
            choiceLabels == null || choiceButtons.Length < 3 || choiceLabels.Length < 3) return false;
        pending = true;
        choosing = true;
        onChoice = callback;
        onConfirm = null;
        if (titleText != null) titleText.text = $"{floor}층 · {evt.title}";
        if (descriptionText != null) descriptionText.text = evt.description;
        if (resultPanel != null) resultPanel.SetActive(false);
        for (int i = 0; i < 3; i++)
        {
            bool show = i < evt.choices.Count;
            if (choiceButtons[i] == null || choiceLabels[i] == null) { Close(); return false; }
            choiceButtons[i].gameObject.SetActive(show);
            choiceButtons[i].interactable = show;
            if (show) choiceLabels[i].text = evt.choices[i].text;
        }
        if (skipButton != null) { skipButton.gameObject.SetActive(true); skipButton.interactable = true; }
        specialPanel.SetActive(true);
        return true;
    }

    private void Select(int index)
    {
        if (!pending || !choosing || onChoice == null) return;
        choosing = false;
        foreach (var button in choiceButtons)
            if (button != null) button.interactable = false;
        if (skipButton != null) skipButton.interactable = false;
        onChoice(index);
    }

    public void ShowResult(string message, Action callback)
    {
        if (!pending) return;
        onChoice = null;
        onConfirm = callback;
        if (resultText != null) resultText.text = message;
        foreach (var button in choiceButtons)
            if (button != null) button.gameObject.SetActive(false);
        if (skipButton != null) skipButton.gameObject.SetActive(false);
        if (resultPanel != null) resultPanel.SetActive(true);
    }

    private void Confirm()
    {
        if (!pending || onConfirm == null) return;
        var callback = onConfirm;
        onConfirm = null;
        callback();
    }

    public void Close()
    {
        pending = false;
        choosing = false;
        onChoice = null;
        onConfirm = null;
        if (specialPanel != null) specialPanel.SetActive(false);
    }
}
