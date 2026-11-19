using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class HealthMonFirstRunFlow : MonoBehaviour
{
    [Header("Panels")]
    public GameObject startPanel;
    public GameObject setupPanel;

    [Header("Buttons")]
    public Button continueButton;
    public Button newStartButton;
    public Button confirmButton;
    public Button backButton;

    [Header("Input")]
    public TMP_InputField nicknameInput;
    public TMP_Text statusText;

    [Header("Character Cards")]
    public Button[] cardButtons;
    public Image[] cardFrames;

    [Header("Style")]
    public Color normalFrameColor = new Color(1f, 1f, 1f, 0.35f);
    public Color selectedFrameColor = new Color(1f, 0.82f, 0.2f, 1f);

    [Header("Scene")]
    public string mainSceneName = "MainARScene";

    private int selectedCharacterIndex = 0;

    private void Start()
    {
        if (continueButton != null) continueButton.onClick.AddListener(OnContinue);
        if (newStartButton != null) newStartButton.onClick.AddListener(OpenSetup);
        if (confirmButton != null) confirmButton.onClick.AddListener(ConfirmSetup);
        if (backButton != null) backButton.onClick.AddListener(BackToStart);

        for (int i = 0; i < cardButtons.Length; i++)
        {
            int captured = i;
            if (cardButtons[i] != null)
                cardButtons[i].onClick.AddListener(() => SelectCharacter(captured));
        }

        SelectCharacter(0);

        if (HealthMonStarterProfile.Instance != null && HealthMonStarterProfile.Instance.IsSetupDone)
        {
            startPanel.SetActive(true);
            setupPanel.SetActive(false);
        }
        else
        {
            startPanel.SetActive(false);
            setupPanel.SetActive(true);
        }
    }

    public void OpenSetup()
    {
        startPanel.SetActive(false);
        setupPanel.SetActive(true);
        if (statusText != null)
            statusText.text = "닉네임과 캐릭터를 선택해주세요.";
    }

    public void BackToStart()
    {
        setupPanel.SetActive(false);
        startPanel.SetActive(true);
    }

    public void SelectCharacter(int index)
    {
        selectedCharacterIndex = index;

        for (int i = 0; i < cardFrames.Length; i++)
        {
            if (cardFrames[i] != null)
                cardFrames[i].color = (i == index) ? selectedFrameColor : normalFrameColor;
        }

        if (statusText != null)
        {
            string[] names = { "썬", "민트", "라벤더" };
            statusText.text = $"선택된 캐릭터: {names[Mathf.Clamp(index, 0, names.Length - 1)]}";
        }
    }

    public void ConfirmSetup()
    {
        string nickname = nicknameInput != null ? nicknameInput.text.Trim() : "";

        if (string.IsNullOrEmpty(nickname))
        {
            if (statusText != null) statusText.text = "닉네임을 입력해주세요.";
            return;
        }

        if (nickname.Length < 2 || nickname.Length > 12)
        {
            if (statusText != null) statusText.text = "닉네임은 2~12자로 입력해주세요.";
            return;
        }

        if (HealthMonStarterProfile.Instance != null)
            HealthMonStarterProfile.Instance.Save(nickname, selectedCharacterIndex);

        SceneManager.LoadScene(mainSceneName);
    }

    public void OnContinue()
    {
        if (HealthMonStarterProfile.Instance == null || !HealthMonStarterProfile.Instance.IsSetupDone)
        {
            OpenSetup();
            return;
        }

        SceneManager.LoadScene(mainSceneName);
    }
}