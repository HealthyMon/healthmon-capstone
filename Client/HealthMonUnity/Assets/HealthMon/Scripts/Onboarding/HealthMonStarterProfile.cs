using UnityEngine;

public class HealthMonStarterProfile : MonoBehaviour
{
    public static HealthMonStarterProfile Instance;
    private static readonly string[] Colors = { "sun", "mint", "lavender" };
    private static readonly Color[] Tints = {
        new Color(1f, .63f, .35f), new Color(.38f, .95f, .75f), new Color(.78f, .65f, 1f)
    };
    private static readonly int[] ColorProperties = { Shader.PropertyToID("_BaseColor"), Shader.PropertyToID("_Color") };

    public static string ColorId(int index) => Colors[Mathf.Clamp(index, 0, Colors.Length - 1)];
    public static Color DefaultTint(int index) => Tints[Mathf.Clamp(index, 0, Tints.Length - 1)];
    public static bool TryGetTint(string color, out Color tint)
    {
        int index = System.Array.IndexOf(Colors, color);
        tint = index < 0 ? Color.white : Tints[index];
        return index >= 0;
    }

    public static void SetTint(Renderer renderer, MaterialPropertyBlock block, Color? tint)
    {
        var material = renderer.sharedMaterial;
        if (material == null) return;
        renderer.GetPropertyBlock(block);
        foreach (int property in ColorProperties)
            if (material.HasProperty(property))
                block.SetColor(property, tint ?? material.GetColor(property));
        renderer.SetPropertyBlock(block);
    }

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
