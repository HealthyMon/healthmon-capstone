using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class AdventureQuizEventUI : MonoBehaviour
{
    [SerializeField] private GameObject quizPanel;
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text questionText;
    [SerializeField] private Button[] answerButtons = new Button[4];
    [SerializeField] private TMP_Text[] answerLabels = new TMP_Text[4];
    [SerializeField] private TMP_Text feedbackText;
    [SerializeField] private GameObject rewardPanel;
    [SerializeField] private TMP_Text itemRewardText;
    [SerializeField] private TMP_Text statRewardText;
    [SerializeField] private Button itemButton;
    [SerializeField] private Button statButton;
    [SerializeField] private Button finishButton;

    private Action<int> onAnswer;
    private Action<bool> onReward;
    private Action onFinish;
    private bool pending;

    private void Awake()
    {
        if (quizPanel != null) quizPanel.SetActive(false);
        for (int i = 0; i < answerButtons.Length; i++)
        {
            int index = i;
            if (answerButtons[i] != null) answerButtons[i].onClick.AddListener(() => Answer(index));
        }
        if (itemButton != null) itemButton.onClick.AddListener(() => Reward(true));
        if (statButton != null) statButton.onClick.AddListener(() => Reward(false));
        if (finishButton != null) finishButton.onClick.AddListener(Finish);
    }

    public bool Begin(int floor, AdventureQuizQuestion q, Action<int> answerCallback)
    {
        if (pending || quizPanel == null || q == null || answerCallback == null ||
            answerButtons.Length != 4 || answerLabels.Length != 4) return false;
        for (int i = 0; i < 4; i++)
            if (answerButtons[i] == null || answerLabels[i] == null) return false;
        pending = true;
        onAnswer = answerCallback;
        onReward = null;
        onFinish = null;
        if (titleText != null) titleText.text = $"{floor}층 · 건강 퀴즈";
        if (questionText != null) questionText.text = q.question;
        if (feedbackText != null) feedbackText.text = "정답을 하나 선택하세요.";
        if (rewardPanel != null) rewardPanel.SetActive(false);
        if (finishButton != null) finishButton.gameObject.SetActive(false);
        for (int i = 0; i < 4; i++)
        {
            answerLabels[i].text = $"{i + 1}. {q.choices[i]}";
            answerButtons[i].gameObject.SetActive(true);
            answerButtons[i].interactable = true;
        }
        quizPanel.SetActive(true);
        return true;
    }

    private void Answer(int index)
    {
        if (!pending || onAnswer == null) return;
        foreach (var button in answerButtons) button.interactable = false;
        onAnswer(index);
    }

    public void ShowCorrect(string explanation, string itemLabel, string statLabel, bool canItem, Action<bool> callback)
    {
        onAnswer = null;
        onReward = callback;
        foreach (var button in answerButtons) button.gameObject.SetActive(false);
        if (feedbackText != null) feedbackText.text = "정답! " + explanation;
        if (rewardPanel != null) rewardPanel.SetActive(true);
        if (itemRewardText != null) itemRewardText.text = itemLabel;
        if (statRewardText != null) statRewardText.text = statLabel;
        if (itemButton != null) itemButton.interactable = canItem;
        if (statButton != null) statButton.interactable = true;
    }

    public void ShowIncorrect(string explanation, Action callback)
    {
        onAnswer = null;
        onFinish = callback;
        foreach (var button in answerButtons) button.gameObject.SetActive(false);
        if (feedbackText != null) feedbackText.text = "오답. " + explanation;
        if (rewardPanel != null) rewardPanel.SetActive(false);
        if (finishButton != null) finishButton.gameObject.SetActive(true);
    }

    private void Reward(bool item)
    {
        if (!pending || onReward == null) return;
        if (itemButton != null) itemButton.interactable = false;
        if (statButton != null) statButton.interactable = false;
        onReward(item);
        if (pending)
        {
            if (itemButton != null) itemButton.interactable = true;
            if (statButton != null) statButton.interactable = true;
        }
    }

    private void Finish() { if (pending && onFinish != null) onFinish(); }

    public void Close()
    {
        pending = false;
        onAnswer = null;
        onReward = null;
        onFinish = null;
        if (quizPanel != null) quizPanel.SetActive(false);
    }
}
