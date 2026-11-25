using System.Collections;
using Healthmon.Beta;
using Healthmon.Common;
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
    private bool saving;

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

        var profile = HealthMonStarterProfile.Instance;
        SelectCharacter(profile != null ? profile.SelectedCharacterIndex : 0);
        if (nicknameInput != null && profile != null) nicknameInput.text = profile.Nickname;

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
        if (saving) return;
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
        if (saving) return;
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

        if (CommonServerConnection.UsesServerAuthority)
            StartCoroutine(SaveOnServer(nickname, selectedCharacterIndex));
        else
            CompleteSetup(nickname, selectedCharacterIndex);
    }

    public void OnContinue()
    {
        if (saving) return;
        if (HealthMonStarterProfile.Instance == null || !HealthMonStarterProfile.Instance.IsSetupDone)
        {
            OpenSetup();
            return;
        }

        if (CommonServerConnection.UsesServerAuthority)
            StartCoroutine(SaveOnServer(HealthMonStarterProfile.Instance.Nickname,
                HealthMonStarterProfile.Instance.SelectedCharacterIndex, true));
        else
            SceneManager.LoadScene(mainSceneName);
    }

    private void CompleteSetup(string nickname, int characterIndex)
    {
        HealthMonStarterProfile.Instance?.Save(nickname, characterIndex);
        SceneManager.LoadScene(mainSceneName);
    }

    private IEnumerator SaveOnServer(string nickname, int characterIndex, bool continuing = false)
    {
        saving = true;
        if (confirmButton != null) confirmButton.interactable = false;
        if (continueButton != null) continueButton.interactable = false;
        if (backButton != null) backButton.interactable = false;
        if (newStartButton != null) newStartButton.interactable = false;
        if (statusText != null) statusText.text = "서버 프로필 확인 중…";

        var connection = CommonServerConnection.Instance;
        float deadline = Time.realtimeSinceStartup + 10;
        while (connection != null &&
               (!connection.IsConnected || connection.Api.IsBusy || connection.LatestState?.settings == null) &&
               Time.realtimeSinceStartup < deadline)
            yield return null;

        bool ready = connection != null && connection.IsConnected && !connection.Api.IsBusy &&
            connection.LatestState?.settings != null;
        if (continuing && (!ready || !CanRestoreLocalProfile(connection)))
        {
            SceneManager.LoadScene(mainSceneName);
            yield break;
        }

        bool saved = false;
        if (ready)
        {
            bool completed = false;
            connection.Api.SetStarterProfile(new StarterProfileRequest {
                name = nickname, starter_color = HealthMonStarterProfile.ColorId(characterIndex)
            }, _ => { saved = true; completed = true; }, _ => completed = true);
            while (!completed) yield return null;
        }
        if (saved)
        {
            CompleteSetup(nickname, characterIndex);
            yield break;
        }
        saving = false;
        if (confirmButton != null) confirmButton.interactable = true;
        if (continueButton != null) continueButton.interactable = true;
        if (backButton != null) backButton.interactable = true;
        if (newStartButton != null) newStartButton.interactable = true;
        if (continuing) OpenSetup();
        if (statusText != null) statusText.text = "프로필 저장 실패 · 서버 연결을 확인하고 다시 시도해주세요.";
    }

    private static bool CanRestoreLocalProfile(CommonServerConnection connection)
    {
        // Only the unchanged starter bound by the local launcher is eligible for migration.
        var state = connection.LatestState;
        return connection.EnvironmentName == "test" && state.published_model_stage == 0 &&
            (state.settings.name == "몽글이" || state.settings.name == "헬스몬") &&
            string.IsNullOrEmpty(state.settings.starter_color) &&
            LocalConnectionProfile.TryRead(out var local) &&
            local.server_instance_id == connection.ServerInstanceId && local.owner_id == connection.OwnerId &&
            local.pet_id == state.pet_id;
    }
}
