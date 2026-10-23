#if UNITY_EDITOR
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Creates an optional overlay inside the existing CustomizationPanel in one click.
/// Leaves the existing four collection buttons and EquipButton untouched.
/// </summary>
public static class HealthMonJewelryUIBuilder
{
    private static readonly string[] Items = { "목걸이", "귀걸이", "펜던트", "반지" };
    private static readonly Color Surface = new Color(0.09f, 0.14f, 0.20f, 0.98f);
    private static readonly Color Cell = new Color(0.16f, 0.23f, 0.29f, 1f);
    private static readonly Color ButtonColor = new Color(0.13f, 0.58f, 0.52f, 1f);
    private static readonly Color White = Color.white;

    [MenuItem("HealthMon/Jewelry/Create Equipment Popup")]
    public static void CreatePopup()
    {
        GameObject panel = null;
        foreach (Transform candidate in Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (candidate.gameObject.name == "CustomizationPanel")
            {
                panel = candidate.gameObject;
                break;
            }
        }

        if (panel == null)
        {
            EditorUtility.DisplayDialog("HealthMon Jewelry", "현재 Scene에 CustomizationPanel이 없습니다. MainARScene을 먼저 열어 주세요.", "확인");
            return;
        }

        if (panel.transform.Find("JewelryEquipmentOverlay") != null)
        {
            EditorUtility.DisplayDialog("HealthMon Jewelry", "장신구 팝업이 이미 있습니다. 중복 생성하지 않았습니다.", "확인");
            return;
        }

        var existingTexts = panel.GetComponentsInChildren<TMP_Text>(true);
        TMP_FontAsset font = existingTexts.Length > 0 ? existingTexts[0].font : null;
        var controller = panel.GetComponent<HealthMonJewelryOverlayUI>();
        if (controller == null) controller = Undo.AddComponent<HealthMonJewelryOverlayUI>(panel);

        // Small launch button. Anchor at upper-right and reposition manually if needed.
        var launch = Rect(panel.transform, "JewelryOpenButton");
        launch.anchorMin = launch.anchorMax = new Vector2(1, 1);
        launch.pivot = new Vector2(1, 1);
        launch.anchoredPosition = new Vector2(-16, -20);
        launch.sizeDelta = new Vector2(230, 76);
        var launchBtn = Button(launch, ButtonColor);
        FullText(launch, "Label", "장신구 관리", 29, font);

        // Full panel overlay; covers old controls while active, but doesn't remove them.
        var backdrop = Rect(panel.transform, "JewelryEquipmentOverlay");
        Stretch(backdrop);
        backdrop.gameObject.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.85f);

        var card = Rect(backdrop, "EquipmentCard");
        card.anchorMin = new Vector2(.05f, .17f);
        card.anchorMax = new Vector2(.95f, .83f);
        card.offsetMin = card.offsetMax = Vector2.zero;
        card.gameObject.AddComponent<Image>().color = Surface;

        var title = Rect(card, "Title");
        title.anchorMin = new Vector2(.05f, 1f);
        title.anchorMax = new Vector2(.76f, 1f);
        title.pivot = new Vector2(0, 1);
        title.anchoredPosition = new Vector2(0, -30);
        title.sizeDelta = new Vector2(0, 65);
        Text(title, "장신구 동시 착용", 39, font, TextAlignmentOptions.MidlineLeft);

        var close = Rect(card, "CloseButton");
        close.anchorMin = close.anchorMax = new Vector2(.95f, 1f);
        close.pivot = new Vector2(1, 1);
        close.anchoredPosition = new Vector2(0, -25);
        close.sizeDelta = new Vector2(92, 68);
        var closeBtn = Button(close, Cell);
        FullText(close, "Label", "닫기", 27, font);

        var rowsParent = Rect(card, "Rows");
        rowsParent.anchorMin = new Vector2(.045f, .19f);
        rowsParent.anchorMax = new Vector2(.955f, .81f);
        rowsParent.offsetMin = rowsParent.offsetMax = Vector2.zero;
        var vertical = rowsParent.gameObject.AddComponent<VerticalLayoutGroup>();
        vertical.spacing = 12;
        vertical.padding = new RectOffset(0, 0, 0, 0);
        vertical.childAlignment = TextAnchor.MiddleCenter;
        vertical.childControlHeight = true;
        vertical.childForceExpandHeight = true;
        vertical.childControlWidth = true;
        vertical.childForceExpandWidth = true;

        Button[] buttons = new Button[4];
        TMP_Text[] statuses = new TMP_Text[4];
        TMP_Text[] actions = new TMP_Text[4];

        for (int i = 0; i < Items.Length; i++)
        {
            var row = Rect(rowsParent, Items[i] + "Row");
            row.gameObject.AddComponent<Image>().color = Cell;
            var horizontal = row.gameObject.AddComponent<HorizontalLayoutGroup>();
            horizontal.spacing = 6;
            horizontal.padding = new RectOffset(16, 16, 8, 8);
            horizontal.childAlignment = TextAnchor.MiddleCenter;
            horizontal.childControlWidth = true;
            horizontal.childForceExpandWidth = false;
            horizontal.childControlHeight = true;
            horizontal.childForceExpandHeight = true;

            var name = Rect(row, "ItemName");
            Text(name, Items[i], 32, font, TextAlignmentOptions.MidlineLeft);
            Flexible(name, 1.15f, 80);

            var status = Rect(row, "Status");
            statuses[i] = Text(status, "미착용", 26, font, TextAlignmentOptions.Center);
            Flexible(status, 1f, 70);

            var button = Rect(row, "ToggleButton");
            buttons[i] = Button(button, ButtonColor);
            Flexible(button, 1f, 90);
            actions[i] = FullText(button, "Label", "장착", 27, font);
        }

        var footer = Rect(card, "EquippedSummary");
        footer.anchorMin = new Vector2(.06f, .02f);
        footer.anchorMax = new Vector2(.94f, .15f);
        footer.offsetMin = footer.offsetMax = Vector2.zero;
        var summary = Text(footer, "장착 중 0 / 4", 25, font, TextAlignmentOptions.Center);

        controller.Configure(backdrop.gameObject, launchBtn, closeBtn, buttons, statuses, actions, summary);
        backdrop.gameObject.SetActive(false);
        Undo.RegisterCreatedObjectUndo(launch.gameObject, "Create Jewelry Open Button");
        Undo.RegisterCreatedObjectUndo(backdrop.gameObject, "Create Jewelry Overlay");
        EditorUtility.SetDirty(controller);
        EditorSceneManager.MarkSceneDirty(panel.scene);
        Selection.activeGameObject = panel;
        EditorUtility.DisplayDialog("HealthMon Jewelry", "장신구 4종 관리 팝업 생성 완료! Scene을 저장하고 Play로 테스트하세요.", "확인");
    }

    private static RectTransform Rect(Transform parent, string name)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        var rect = go.GetComponent<RectTransform>();
        rect.localScale = Vector3.one;
        return rect;
    }

    private static void Stretch(RectTransform r)
    {
        r.anchorMin = Vector2.zero;
        r.anchorMax = Vector2.one;
        r.offsetMin = r.offsetMax = Vector2.zero;
    }

    private static Button Button(RectTransform r, Color color)
    {
        var img = r.gameObject.AddComponent<Image>();
        img.color = color;
        var btn = r.gameObject.AddComponent<Button>();
        btn.targetGraphic = img;
        return btn;
    }

    private static TMP_Text FullText(RectTransform parent, string name, string str, int size, TMP_FontAsset font)
    {
        var r = Rect(parent, name);
        Stretch(r);
        return Text(r, str, size, font, TextAlignmentOptions.Center);
    }

    private static TMP_Text Text(RectTransform r, string str, int size, TMP_FontAsset font, TextAlignmentOptions align)
    {
        var tmp = r.gameObject.AddComponent<TextMeshProUGUI>();
        if (font != null) tmp.font = font;
        tmp.text = str;
        tmp.fontSize = size;
        tmp.fontSizeMin = 15;
        tmp.fontSizeMax = size;
        tmp.enableAutoSizing = true;
        tmp.color = White;
        tmp.alignment = align;
        tmp.raycastTarget = false;
        tmp.margin = new Vector4(5, 0, 5, 0);
        return tmp;
    }

    private static void Flexible(RectTransform r, float flex, float min)
    {
        var layout = r.gameObject.AddComponent<LayoutElement>();
        layout.flexibleWidth = flex;
        layout.minWidth = min;
    }
}
#endif
