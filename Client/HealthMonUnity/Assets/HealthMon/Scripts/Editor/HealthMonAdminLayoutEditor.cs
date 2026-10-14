#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public static class HealthMonAdminLayoutEditor
{
    private static readonly Color Background = new Color(0.075f, .12f, .19f, 1f);
    private static readonly Color TextColor = new Color(.94f, .97f, 1f, 1f);
    private static readonly Color Muted = new Color(.68f, .76f, .85f, 1f);
    private static readonly Color Accent = new Color(.24f, .73f, .56f, 1f);

    [MenuItem("Tools/HealthMon/관리자 UI 자동 배치")]
    public static void BuildLayout()
    {
        RectTransform admin = FindSceneRect("AdminPanel");
        if (admin == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "현재 열린 씬의 Canvas 아래 AdminPanel을 먼저 만들어 주세요.", "확인");
            return;
        }

        Undo.RegisterFullObjectHierarchyUndo(admin.gameObject, "HealthMon Admin UI Layout");
        Stretch(admin, 0, 0, 0, 0);
        Image bg = admin.GetComponent<Image>();
        if (bg == null) bg = Undo.AddComponent<Image>(admin.gameObject);
        bg.color = Background;

        RectTransform title = GetOrCreateText(admin, "TitleText", "헬스몬 관리자 모드", 27, TextAlignmentOptions.Center, TextColor);
        PlaceTop(title, 0, 0, 90, 0, 0); // stretch horizontally

        RectTransform close = GetOrCreateButton(admin, "CloseButton", "닫기");
        PlaceTopRight(close, 15, 23, 65, 42);
        SetButtonColor(close, new Color(.26f, .33f, .43f));

        RectTransform content = GetOrCreateRect(admin, "ContentPanel");
        Stretch(content, 18, 18, 108, 22);
        // Existing Image on ContentPanel can obscure children or be left transparent.
        Image contentImage = content.GetComponent<Image>();
        if (contentImage != null) contentImage.color = new Color(0, 0, 0, 0);

        RectTransform level = FindRecursive(content, "LevelInput");
        RectTransform coin = FindRecursive(content, "CoinInput");
        if (level == null || coin == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "ContentPanel 아래 LevelInput과 CoinInput을 먼저 만들어 주세요.", "확인");
            return;
        }
        SetupInput(level, "1");
        SetupInput(coin, "0");
        PlaceTopRange(level, 0, .48f, 40, 52, 0, 0);
        PlaceTopRange(coin, .52f, 1, 40, 52, 0, 0);
        PlaceTopRange(GetOrCreateText(content, "LevelLabel", "레벨", 18, TextAlignmentOptions.Left, TextColor), 0, .48f, 5, 28, 0, 0);
        PlaceTopRange(GetOrCreateText(content, "CoinLabel", "코인", 18, TextAlignmentOptions.Left, TextColor), .52f, 1, 5, 28, 0, 0);

        string[] names = { "Intimacy", "Activity", "Kindness", "Curiosity" };
        string[] korean = { "친밀도", "활동성", "다정함", "호기심" };
        int[] initial = { 45, 32, 40, 20 };
        RectTransform sliderTemplate = FindRecursive(content, "IntimacySlider");
        if (sliderTemplate == null || sliderTemplate.GetComponent<Slider>() == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "ContentPanel 아래 IntimacySlider (UI > Slider)를 먼저 만들어 주세요.", "확인");
            return;
        }
        for (int i = 0; i < names.Length; i++)
        {
            int top = 121 + i * 78;
            string sliderName = names[i] + "Slider";
            RectTransform slider = FindRecursive(content, sliderName);
            if (slider == null)
            {
                GameObject copy = Object.Instantiate(sliderTemplate.gameObject, content);
                Undo.RegisterCreatedObjectUndo(copy, "Create " + sliderName);
                copy.name = sliderName;
                slider = copy.GetComponent<RectTransform>();
            }
            Slider control = slider.GetComponent<Slider>();
            control.minValue = 0;
            control.maxValue = 100;
            control.wholeNumbers = true;
            control.SetValueWithoutNotify(initial[i]);
            if (control.fillRect != null)
            {
                Image fill = control.fillRect.GetComponent<Image>();
                if (fill != null) fill.color = Accent;
            }
            PlaceTop(slider, 0, 0, top + 28, 25, 0);
            PlaceTopRange(GetOrCreateText(content, names[i] + "Label", korean[i], 18, TextAlignmentOptions.Left, TextColor), 0, .7f, top, 26, 0, 0);
            PlaceTopRange(GetOrCreateText(content, names[i] + "ValueText", initial[i] + " / 100", 17, TextAlignmentOptions.Right, Muted), .7f, 1, top, 26, 0, 0);
        }

        RectTransform apply = GetOrCreateButton(content, "ApplyButton", "변경 적용");
        PlaceTop(apply, 0, 0, 455, 55, 0);
        SetButtonColor(apply, Accent);

        admin.gameObject.SetActive(true); // preview in editor; UIManager will control activation in Play mode after wiring
        admin.SetAsLastSibling();
        EditorUtility.SetDirty(admin.gameObject);
        UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(admin.gameObject.scene);
        Selection.activeGameObject = admin.gameObject;
        EditorUtility.DisplayDialog("HealthMon", "관리자 UI 배치 완료! Game 창에서 위치를 확인해 주세요. 버튼 기능은 아직 연결되지 않았습니다.", "확인");
    }

    private static RectTransform FindSceneRect(string name)
    {
        RectTransform[] all = Object.FindObjectsByType<RectTransform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (var rect in all)
            if (rect.name == name && rect.gameObject.scene.IsValid() && rect.GetComponentInParent<Canvas>(true) != null) return rect;
        return null;
    }
    private static RectTransform FindRecursive(Transform parent, string name)
    {
        foreach (RectTransform r in parent.GetComponentsInChildren<RectTransform>(true))
            if (r.name == name) return r;
        return null;
    }
    private static RectTransform GetOrCreateRect(Transform parent, string name)
    {
        var existing = FindRecursive(parent, name);
        if (existing != null) return existing;
        GameObject go = new GameObject(name, typeof(RectTransform));
        Undo.RegisterCreatedObjectUndo(go, "Create " + name);
        go.transform.SetParent(parent, false);
        return go.GetComponent<RectTransform>();
    }
    private static RectTransform GetOrCreateText(Transform parent, string name, string value, float fontSize, TextAlignmentOptions alignment, Color color)
    {
        RectTransform r = GetOrCreateRect(parent, name);
        var text = r.GetComponent<TextMeshProUGUI>();
        if (text == null) text = Undo.AddComponent<TextMeshProUGUI>(r.gameObject);
        text.text = value;
        text.fontSize = fontSize;
        text.color = color;
        text.alignment = alignment;
        text.raycastTarget = false;
        text.enableAutoSizing = true;
        text.fontSizeMin = 12;
        text.fontSizeMax = fontSize;
        return r;
    }
    private static RectTransform GetOrCreateButton(Transform parent, string name, string text)
    {
        RectTransform r = GetOrCreateRect(parent, name);
        if (r.GetComponent<Image>() == null) Undo.AddComponent<Image>(r.gameObject);
        if (r.GetComponent<Button>() == null) Undo.AddComponent<Button>(r.gameObject);
        RectTransform txt = GetOrCreateText(r, "Text (TMP)", text, 20, TextAlignmentOptions.Center, Color.white);
        Stretch(txt, 3, 3, 0, 0);
        return r;
    }
    private static void SetButtonColor(RectTransform r, Color color)
    {
        Image image = r.GetComponent<Image>();
        if (image != null) image.color = color;
    }
    private static void SetupInput(RectTransform root, string placeholder)
    {
        TMP_InputField input = root.GetComponent<TMP_InputField>();
        if (input == null) return;
        input.contentType = TMP_InputField.ContentType.IntegerNumber;
        input.characterLimit = 8;
        if (string.IsNullOrEmpty(input.text)) input.SetTextWithoutNotify(placeholder);
        Image image = root.GetComponent<Image>();
        if (image != null) image.color = new Color(.92f, .96f, .98f);
    }
    private static void Stretch(RectTransform r, float left, float right, float top, float bottom)
    {
        r.anchorMin = Vector2.zero; r.anchorMax = Vector2.one;
        r.offsetMin = new Vector2(left, bottom);
        r.offsetMax = new Vector2(-right, -top);
        r.localScale = Vector3.one;
    }
    private static void PlaceTop(RectTransform r, float left, float right, float top, float height, float unused)
    {
        r.anchorMin = new Vector2(0, 1); r.anchorMax = new Vector2(1, 1);
        r.pivot = new Vector2(.5f, 1);
        r.offsetMin = new Vector2(left, -top - height);
        r.offsetMax = new Vector2(-right, -top);
        r.localScale = Vector3.one;
    }
    private static void PlaceTopRange(RectTransform r, float xMin, float xMax, float top, float height, float leftInset, float rightInset)
    {
        r.anchorMin = new Vector2(xMin, 1); r.anchorMax = new Vector2(xMax, 1);
        r.pivot = new Vector2(.5f, 1);
        r.offsetMin = new Vector2(leftInset, -top - height);
        r.offsetMax = new Vector2(-rightInset, -top);
        r.localScale = Vector3.one;
    }
    private static void PlaceTopRight(RectTransform r, float right, float top, float width, float height)
    {
        r.anchorMin = Vector2.one; r.anchorMax = Vector2.one;
        r.pivot = new Vector2(1, 1);
        r.anchoredPosition = new Vector2(-right, -top);
        r.sizeDelta = new Vector2(width, height);
        r.localScale = Vector3.one;
    }
}
#endif
