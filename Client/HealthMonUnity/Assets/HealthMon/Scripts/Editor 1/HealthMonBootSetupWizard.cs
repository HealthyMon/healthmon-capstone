#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using TMPro;

public class HealthMonBootSetupWizard
{
    private static TMP_FontAsset cachedFont;

    [MenuItem("HealthMon/Start/Rebuild Boot Start UI")]
    public static void RebuildBootStartUI()
    {
        DeleteOldGeneratedObjects();
        EnsureEventSystem();
        EnsureStarterProfile();

        GameObject canvasGo = new GameObject("HealthMonFirstRunCanvas",
            typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        Canvas canvas = canvasGo.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        CanvasScaler scaler = canvasGo.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1080, 1920);
        scaler.matchWidthOrHeight = 0.5f;

        Transform root = canvasGo.transform;

        GameObject startPanel = CreateUI("StartPanel", root);
        StretchFull(startPanel.GetComponent<RectTransform>());
        BuildStartPanel(startPanel.transform);

        GameObject setupPanel = CreateUI("FirstSetupPanel", root);
        StretchFull(setupPanel.GetComponent<RectTransform>());
        BuildSetupPanel(setupPanel.transform);

        GameObject runtimeRoot = new GameObject("HealthMonStartRuntime");
        BuildPreviewWorld(runtimeRoot.transform, setupPanel.transform);

        WireFlow(canvasGo, startPanel, setupPanel);

        EditorUtility.DisplayDialog("HealthMon", "Boot 시작 UI를 다시 생성했습니다.", "확인");
    }

    [MenuItem("HealthMon/Start/Reset First Run Profile")]
    public static void ResetProfile()
    {
        PlayerPrefs.DeleteKey("HM_PLAYER_NICKNAME");
        PlayerPrefs.DeleteKey("HM_PLAYER_CHARACTER_INDEX");
        PlayerPrefs.DeleteKey("HM_PLAYER_SETUP_DONE");
        PlayerPrefs.Save();

        EditorUtility.DisplayDialog("HealthMon", "최초 시작 프로필 초기화 완료", "확인");
    }

    static void DeleteOldGeneratedObjects()
    {
        string[] names =
        {
            "HealthMonFirstRunCanvas",
            "HealthMonStartRuntime",
            "HealthMonStarterProfile"
        };

        foreach (string n in names)
        {
            GameObject go = GameObject.Find(n);
            if (go != null) Object.DestroyImmediate(go);
        }
    }

    static void EnsureEventSystem()
    {
        if (Object.FindObjectOfType<EventSystem>() == null)
        {
            new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
        }
    }

    static void EnsureStarterProfile()
    {
        if (Object.FindObjectOfType<HealthMonStarterProfile>() == null)
        {
            new GameObject("HealthMonStarterProfile", typeof(HealthMonStarterProfile));
        }
    }

    static void BuildStartPanel(Transform parent)
    {
        CreateImage("Dim", parent, new Color(0, 0, 0, 0.25f), true);

        GameObject title = CreateText("Title", parent, "HEALTHMON", 86, FontStyles.Bold);
        SetRect(title.GetComponent<RectTransform>(), 0.5f, 1f, 0, -170, 800, 100);

        GameObject sub = CreateText("SubTitle", parent, "나의 기록과 함께\n자라는 캐릭터", 34, FontStyles.Normal);
        SetRect(sub.GetComponent<RectTransform>(), 0.5f, 1f, 0, -290, 600, 110);

        GameObject continueBtn = CreateButton("ContinueButton", parent, "이어서 시작하기", new Color(0.97f, 0.76f, 0.28f));
        SetRect(continueBtn.GetComponent<RectTransform>(), 0.5f, 0f, 0, 260, 720, 110);

        GameObject newBtn = CreateButton("NewStartButton", parent, "새로 시작", new Color(0.22f, 0.52f, 0.86f));
        SetRect(newBtn.GetComponent<RectTransform>(), 0.5f, 0f, 0, 120, 720, 110);
    }

    static void BuildSetupPanel(Transform parent)
    {
        CreateImage("Dim", parent, new Color(0, 0, 0, 0.45f), true);

        GameObject card = CreateImage("SetupCard", parent, new Color(0.08f, 0.20f, 0.35f, 0.94f), false);
        SetRect(card.GetComponent<RectTransform>(), 0.5f, 0.5f, 0, 0, 900, 1320);

        GameObject title = CreateText("SetupTitle", card.transform, "내 헬스몬 만들기", 54, FontStyles.Bold);
        SetRect(title.GetComponent<RectTransform>(), 0.5f, 1f, 0, -90, 600, 70);

        GameObject desc = CreateText("SetupDesc", card.transform, "닉네임과 첫 캐릭터를 선택해주세요.", 26, FontStyles.Normal);
        SetRect(desc.GetComponent<RectTransform>(), 0.5f, 1f, 0, -150, 700, 45);

        GameObject nicknameLabel = CreateText("NicknameLabel", card.transform, "01 닉네임", 30, FontStyles.Bold);
        SetRect(nicknameLabel.GetComponent<RectTransform>(), 0.5f, 1f, 0, -240, 720, 45);
        nicknameLabel.GetComponent<TextMeshProUGUI>().alignment = TextAlignmentOptions.Left;
        nicknameLabel.GetComponent<RectTransform>().anchoredPosition += new Vector2(-20, 0);

        GameObject inputBG = CreateImage("NicknameInputBG", card.transform, Color.white, false);
        SetRect(inputBG.GetComponent<RectTransform>(), 0.5f, 1f, 0, -315, 720, 88);

        TMP_InputField input = CreateInputField("NicknameInput", inputBG.transform, "닉네임 입력 (2~12자)");
        StretchInset(input.GetComponent<RectTransform>(), 18, 18, 12, 12);

        GameObject charLabel = CreateText("CharacterLabel", card.transform, "02 캐릭터 선택", 30, FontStyles.Bold);
        SetRect(charLabel.GetComponent<RectTransform>(), 0.5f, 1f, 0, -430, 720, 45);
        charLabel.GetComponent<TextMeshProUGUI>().alignment = TextAlignmentOptions.Left;
        charLabel.GetComponent<RectTransform>().anchoredPosition += new Vector2(-20, 0);

        float startX = -250f;
        string[] names = { "썬", "민트", "라벤더" };

        for (int i = 0; i < 3; i++)
        {
            GameObject charCard = CreateImage($"CharacterCard_{i}", card.transform, new Color(1f, 1f, 1f, 0.35f), false);
            SetRect(charCard.GetComponent<RectTransform>(), 0.5f, 1f, startX + (i * 250f), -730, 220, 390);

            Button cardBtn = charCard.AddComponent<Button>();
            ColorBlock cb = cardBtn.colors;
            cb.normalColor = Color.white;
            cb.highlightedColor = Color.white;
            cb.pressedColor = Color.white;
            cb.selectedColor = Color.white;
            cardBtn.colors = cb;

            GameObject previewBG = CreateImage($"PreviewBG_{i}", charCard.transform, new Color(0.90f, 0.92f, 0.96f, 1f), false);
            SetRect(previewBG.GetComponent<RectTransform>(), 0.5f, 1f, 0, -18, 176, 210);

            RawImage raw = previewBG.AddComponent<RawImage>();
            Object.DestroyImmediate(previewBG.GetComponent<Image>());

            GameObject label = CreateText($"Name_{i}", charCard.transform, names[i], 28, FontStyles.Bold);
            SetRect(label.GetComponent<RectTransform>(), 0.5f, 1f, 0, -255, 160, 40);

            GameObject selectHint = CreateText($"Hint_{i}", charCard.transform, "터치하여 선택", 20, FontStyles.Normal);
            SetRect(selectHint.GetComponent<RectTransform>(), 0.5f, 1f, 0, -300, 160, 30);

            GameObject selectBtn = CreateButton($"SelectButton_{i}", charCard.transform, "선택", new Color(0.24f, 0.54f, 0.88f));
            SetRect(selectBtn.GetComponent<RectTransform>(), 0.5f, 0f, 0, 24, 150, 58);
        }

        GameObject status = CreateText("StatusText", card.transform, "닉네임과 캐릭터를 선택해주세요.", 26, FontStyles.Normal);
        SetRect(status.GetComponent<RectTransform>(), 0.5f, 0f, 0, 185, 760, 45);

        GameObject confirm = CreateButton("ConfirmSetupButton", card.transform, "시작하기", new Color(0.97f, 0.76f, 0.28f));
        SetRect(confirm.GetComponent<RectTransform>(), 0.5f, 0f, 0, 95, 320, 86);

        GameObject back = CreateButton("BackButton", card.transform, "뒤로", new Color(0.40f, 0.48f, 0.60f));
        SetRect(back.GetComponent<RectTransform>(), 0.5f, 0f, 0, 15, 220, 70);

        parent.gameObject.SetActive(false);
    }

    static void BuildPreviewWorld(Transform runtimeRoot, Transform setupPanel)
    {
        GameObject slimePrefab = FindPrefab("HealthMon_Slime");
        if (slimePrefab == null)
        {
            Debug.LogWarning("HealthMon_Slime 프리팹을 찾지 못했습니다.");
            return;
        }

        Color[] colors =
        {
            new Color(1f, 0.63f, 0.35f),
            new Color(0.38f, 0.95f, 0.75f),
            new Color(0.78f, 0.65f, 1f)
        };

        for (int i = 0; i < 3; i++)
        {
            GameObject root = new GameObject($"CharacterPreviewRoot_{i}");
            root.transform.SetParent(runtimeRoot, false);
            root.transform.position = new Vector3(i * 6f, 0f, 0f);

            GameObject model = (GameObject)PrefabUtility.InstantiatePrefab(slimePrefab);
            model.transform.SetParent(root.transform, false);
            model.transform.localPosition = Vector3.zero;
            model.transform.localRotation = Quaternion.Euler(0f, 180f, 0f);
            model.transform.localScale = Vector3.one;

            TintModel(model, colors[i]);

            GameObject camGo = new GameObject($"PreviewCamera_{i}", typeof(Camera));
            camGo.transform.SetParent(root.transform, false);
            camGo.transform.localPosition = new Vector3(0f, 0.15f, -2.5f);
            camGo.transform.localRotation = Quaternion.identity;

            Camera cam = camGo.GetComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.95f, 0.96f, 0.98f, 1f);
            cam.fieldOfView = 28f;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 50f;

            RenderTexture rt = new RenderTexture(512, 512, 16);
            rt.name = $"RT_Character_{i}";
            cam.targetTexture = rt;

            Transform preview = setupPanel.Find($"SetupCard/CharacterCard_{i}/PreviewBG_{i}");
            if (preview != null)
            {
                RawImage raw = preview.GetComponent<RawImage>();
                if (raw != null) raw.texture = rt;
            }
        }
    }

    static void WireFlow(GameObject canvasGo, GameObject startPanel, GameObject setupPanel)
    {
        HealthMonFirstRunFlow flow = canvasGo.AddComponent<HealthMonFirstRunFlow>();

        flow.startPanel = startPanel;
        flow.setupPanel = setupPanel;

        flow.continueButton = startPanel.transform.Find("ContinueButton").GetComponent<Button>();
        flow.newStartButton = startPanel.transform.Find("NewStartButton").GetComponent<Button>();
        flow.confirmButton = setupPanel.transform.Find("SetupCard/ConfirmSetupButton").GetComponent<Button>();
        flow.backButton = setupPanel.transform.Find("SetupCard/BackButton").GetComponent<Button>();

        flow.nicknameInput = setupPanel.transform.Find("SetupCard/NicknameInputBG/NicknameInput").GetComponent<TMP_InputField>();
        flow.statusText = setupPanel.transform.Find("SetupCard/StatusText").GetComponent<TextMeshProUGUI>();

        flow.cardButtons = new Button[3];
        flow.cardFrames = new Image[3];

        for (int i = 0; i < 3; i++)
        {
            flow.cardFrames[i] = setupPanel.transform.Find($"SetupCard/CharacterCard_{i}").GetComponent<Image>();
            flow.cardButtons[i] = setupPanel.transform.Find($"SetupCard/CharacterCard_{i}/SelectButton_{i}").GetComponent<Button>();
        }

        EditorUtility.SetDirty(canvasGo);
    }

    static GameObject CreateUI(string name, Transform parent)
    {
        GameObject go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        return go;
    }

    static GameObject CreateImage(string name, Transform parent, Color color, bool fullStretch)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);
        go.GetComponent<Image>().color = color;
        if (fullStretch) StretchFull(go.GetComponent<RectTransform>());
        return go;
    }

    static GameObject CreateText(string name, Transform parent, string text, float size, FontStyles style)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(TextMeshProUGUI));
        go.transform.SetParent(parent, false);

        TextMeshProUGUI tmp = go.GetComponent<TextMeshProUGUI>();
        tmp.text = text;
        tmp.fontSize = size;
        tmp.fontStyle = style;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.color = Color.white;

        TMP_FontAsset font = FindKoreanTMPFont();
        if (font != null) tmp.font = font;

        return go;
    }

    static GameObject CreateButton(string name, Transform parent, string label, Color color)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button));
        go.transform.SetParent(parent, false);

        Image img = go.GetComponent<Image>();
        img.color = color;

        Button btn = go.GetComponent<Button>();
        ColorBlock cb = btn.colors;
        cb.normalColor = color;
        cb.highlightedColor = color * 1.05f;
        cb.pressedColor = color * 0.92f;
        cb.selectedColor = color;
        btn.colors = cb;

        GameObject txt = CreateText("Text", go.transform, label, 30, FontStyles.Bold);
        StretchFull(txt.GetComponent<RectTransform>());

        return go;
    }

    static TMP_InputField CreateInputField(string name, Transform parent, string placeholder)
    {
        GameObject root = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(TMP_InputField));
        root.transform.SetParent(parent, false);
        root.GetComponent<Image>().color = Color.clear;

        GameObject textArea = new GameObject("TextArea", typeof(RectTransform));
        textArea.transform.SetParent(root.transform, false);
        StretchFull(textArea.GetComponent<RectTransform>());

        GameObject placeholderObj = new GameObject("Placeholder", typeof(RectTransform), typeof(TextMeshProUGUI));
        placeholderObj.transform.SetParent(textArea.transform, false);
        StretchFull(placeholderObj.GetComponent<RectTransform>());
        TextMeshProUGUI placeholderText = placeholderObj.GetComponent<TextMeshProUGUI>();
        placeholderText.text = placeholder;
        placeholderText.fontSize = 28;
        placeholderText.color = new Color(0.45f, 0.45f, 0.45f, 0.8f);
        placeholderText.alignment = TextAlignmentOptions.MidlineLeft;
        placeholderText.margin = new Vector4(8, 0, 0, 0);

        GameObject textObj = new GameObject("Text", typeof(RectTransform), typeof(TextMeshProUGUI));
        textObj.transform.SetParent(textArea.transform, false);
        StretchFull(textObj.GetComponent<RectTransform>());
        TextMeshProUGUI inputText = textObj.GetComponent<TextMeshProUGUI>();
        inputText.text = "";
        inputText.fontSize = 30;
        inputText.color = new Color(0.15f, 0.15f, 0.15f, 1f);
        inputText.alignment = TextAlignmentOptions.MidlineLeft;
        inputText.margin = new Vector4(8, 0, 0, 0);

        TMP_FontAsset font = FindKoreanTMPFont();
        if (font != null)
        {
            placeholderText.font = font;
            inputText.font = font;
        }

        TMP_InputField input = root.GetComponent<TMP_InputField>();
        input.textViewport = textArea.GetComponent<RectTransform>();
        input.textComponent = inputText;
        input.placeholder = placeholderText;
        input.lineType = TMP_InputField.LineType.SingleLine;
        return input;
    }

    static TMP_FontAsset FindKoreanTMPFont()
    {
        if (cachedFont != null) return cachedFont;

        string[] preferred = { "Noto", "Pretendard", "Nanum", "Malgun", "Maplestory", "Korean" };
        string[] guids = AssetDatabase.FindAssets("t:TMP_FontAsset");

        foreach (string keyword in preferred)
        {
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                TMP_FontAsset f = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path);
                if (f != null && f.name.ToLower().Contains(keyword.ToLower()))
                {
                    cachedFont = f;
                    return cachedFont;
                }
            }
        }

        if (guids.Length > 0)
        {
            cachedFont = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(AssetDatabase.GUIDToAssetPath(guids[0]));
        }

        return cachedFont;
    }

    static GameObject FindPrefab(string prefabName)
    {
        string[] guids = AssetDatabase.FindAssets(prefabName + " t:Prefab");
        if (guids.Length == 0) return null;
        return AssetDatabase.LoadAssetAtPath<GameObject>(AssetDatabase.GUIDToAssetPath(guids[0]));
    }

    static void TintModel(GameObject root, Color tint)
    {
        Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
        foreach (Renderer r in renderers)
        {
            Material[] mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                if (mats[i] == null) continue;

                Material m = new Material(mats[i]);
                if (m.HasProperty("_Color"))
                    m.color = tint;
                mats[i] = m;
            }
            r.sharedMaterials = mats;
        }
    }

    static void StretchFull(RectTransform rt)
    {
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = Vector2.zero;
        rt.offsetMax = Vector2.zero;
        rt.localScale = Vector3.one;
    }

    static void StretchInset(RectTransform rt, float left, float right, float top, float bottom)
    {
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = new Vector2(left, bottom);
        rt.offsetMax = new Vector2(-right, -top);
        rt.localScale = Vector3.one;
    }

    static void SetRect(RectTransform rt, float anchorX, float anchorY, float x, float y, float w, float h)
    {
        rt.anchorMin = new Vector2(anchorX, anchorY);
        rt.anchorMax = new Vector2(anchorX, anchorY);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.anchoredPosition = new Vector2(x, y);
        rt.sizeDelta = new Vector2(w, h);
        rt.localScale = Vector3.one;
    }
}
#endif