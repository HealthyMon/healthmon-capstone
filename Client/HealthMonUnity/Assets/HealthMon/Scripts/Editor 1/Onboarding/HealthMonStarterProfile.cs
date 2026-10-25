using UnityEngine;

public class HealthMonStarterProfile : MonoBehaviour
{
    public static HealthMonStarterProfile Instance;

    public string Nickname { get; private set; } = "";
    public int SelectedCharacterIndex { get; private set; } = 0;
    public bool IsSetupDone { get; private set; } = false;

    private const string NicknameKey = "HM_PLAYER_NICKNAME";
    private const string CharacterKey = "HM_PLAYER_CHARACTER_INDEX";
    private const string SetupDoneKey = "HM_PLAYER_SETUP_DONE";

    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
            Load();
        }
        else
        {
            Destroy(gameObject);
        }
    }

    public void Save(string nickname, int selectedCharacterIndex)
    {
        Nickname = nickname;
        SelectedCharacterIndex = selectedCharacterIndex;
        IsSetupDone = true;

        PlayerPrefs.SetString(NicknameKey, Nickname);
        PlayerPrefs.SetInt(CharacterKey, SelectedCharacterIndex);
        PlayerPrefs.SetInt(SetupDoneKey, 1);
        PlayerPrefs.Save();
    }

    public void Load()
    {
        Nickname = PlayerPrefs.GetString(NicknameKey, "");
        SelectedCharacterIndex = PlayerPrefs.GetInt(CharacterKey, 0);
        IsSetupDone = PlayerPrefs.GetInt(SetupDoneKey, 0) == 1;
    }

    public void ResetProfile()
    {
        PlayerPrefs.DeleteKey(NicknameKey);
        PlayerPrefs.DeleteKey(CharacterKey);
        PlayerPrefs.DeleteKey(SetupDoneKey);
        PlayerPrefs.Save();

        Nickname = "";
        SelectedCharacterIndex = 0;
        IsSetupDone = false;
    }
}