#if UNITY_EDITOR
using System;
using System.Linq;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

/// <summary>
/// One-click builder for the ORIGINAL CustomizationPanel's real-3D jewelry editor.
/// Reuses a partially created JewelryAdjustPanel and existing preview/palette objects.
/// Does not modify HomePanel, CollectionPanel, character prefabs or server scripts.
/// </summary>
public static class HealthMonJewelryAdjustUIWizard
{
    private const string MenuPath = "HealthMon/Jewelry/Auto Build 3D Rotate & Scale Panel";
    private const string UndoName = "Build HealthMon 3D Jewelry Adjust UI";

    private static readonly Color Background = new Color(0.96f, 0.72f, 0.34f, 0.99f);
    private static readonly Color Header = new Color(1.00f, 0.88f, 0.61f, 1.00f);
    private static readonly Color Brown = new Color(0.32f, 0.22f, 0.12f, 1.00f);
    private static readonly Color Track = new Color(0.56f, 0.36f, 0.22f, 0.65f);
    private static readonly Color Fill = new Color(0.16f, 0.60f, 0.69f, 1.00f);
    private static readonly Color Handle = new Color(1.00f, 0.97f, 0.87f, 1.00f);

    [MenuItem(MenuPath)]
    public static void Build()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("HealthMon", "Play 모드를 종료하고 실행해 주세요.", "확인");
            return;
        }

        Scene scene = SceneManager.GetActiveScene();
        RectTransform customization = Resources.FindObjectsOfTypeAll<RectTransform>()
            .FirstOrDefault(x => x.name == "CustomizationPanel" &&
                                 x.gameObject.scene.IsValid() && x.gameObject.scene == scene &&
                                 x.GetComponentInParent<Canvas>(true) != null);

        if (customization == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "현재 씬에서 UI/Canvas/CustomizationPanel을 찾지 못했어요. MainARScene을 열어 주세요.", "확인");
            return;
        }

        Transform previewRoot = FindSceneObject(scene, "PetPreviewRoot");
        var rig = previewRoot != null ? previewRoot.GetComponentInChildren<HealthMon3DJewelryRig>(true) : null;
        var petImageTransform = FindDescendant(customization, "PetPreviewImage");
        var petImage = petImageTransform != null ? petImageTransform.GetComponent<RawImage>() : null;
        Transform cameraTransform = FindSceneObject(scene, "PetPreviewCamera");
        Camera previewCamera = cameraTransform != null ? cameraTransform.GetComponent<Camera>() : null;

        // Fall back to serialized references already configured on a drag button.
        Transform palette = FindDescendant(customization, "Jewelry3DPalette");
        if (rig == null && palette != null)
        {
            var known = palette.GetComponentInChildren<HealthMon3DPreviewDragButton>(true);
            if (known != null)
            {
                var so = new SerializedObject(known);
                var prop = so.FindProperty("previewRig");
                if (prop != null) rig = prop.objectReferenceValue as HealthMon3DJewelryRig;
            }
        }

        int group = Undo.GetCurrentGroup();
        Undo.SetCurrentGroupName(UndoName);
        Undo.RegisterFullObjectHierarchyUndo(customization.gameObject, UndoName);

        TMP_FontAsset font = FindKoreanFont(customization);
        GameObject popup = EnsureObject(customization, "JewelryAdjustPanel", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
        popup.transform.SetAsLastSibling();
        RectTransform popupRect = popup.GetComponent<RectTransform>();
        // Sits BELOW the 3D PetPreviewImage and palette, ABOVE the bottom navigation.
        SetRect(popupRect, 0.5f, 0f, new Vector2(0f, 475f), new Vector2(900f, 510f));
        var bg = popup.GetComponent<Image>();
        bg.sprite = null;
        bg.color = Background;
        bg.raycastTarget = true;
        var shadow = popup.GetComponent<Shadow>() ?? Undo.AddComponent<Shadow>(popup);
        shadow.effectColor = new Color(0.28f, 0.17f, 0.07f, 0.30f);
        shadow.effectDistance = new Vector2(0f, -8f);

        GameObject headerBg = EnsureObject(popup.transform, "AdjustHeader", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
        SetRect(headerBg.GetComponent<RectTransform>(), 0.5f, 0.5f, new Vector2(0f, 204f), new Vector2(860f, 70f));
        var headerImage = headerBg.GetComponent<Image>();
        headerImage.sprite = null;
        headerImage.color = Header;
        headerImage.raycastTarget = false;

        var selectedName = CreateText(headerBg.transform, "SelectedNameText", "목걸이 · 회전 / 크기 조절", font,
            new Vector2(0f, 0f), new Vector2(790f, 62f), 43f, TextAlignmentOptions.Center);

        CreateText(popup.transform, "YawLabel", "좌우 회전", font,
            new Vector2(-332f, 101f), new Vector2(178f, 55f), 33f, TextAlignmentOptions.Center);
        var yawSlider = CreateSlider(popup.transform, "YawSlider", new Vector2(2f, 101f), -180f, 180f, 0f);
        var yawText = CreateText(popup.transform, "YawValueText", "0°", font,
            new Vector2(338f, 101f), new Vector2(110f, 56f), 34f, TextAlignmentOptions.Center);

        CreateText(popup.transform, "RollLabel", "기울기", font,
            new Vector2(-332f, 8f), new Vector2(178f, 55f), 33f, TextAlignmentOptions.Center);
        var rollSlider = CreateSlider(popup.transform, "RollSlider", new Vector2(2f, 8f), -180f, 180f, 0f);
        var rollText = CreateText(popup.transform, "RollValueText", "0°", font,
            new Vector2(338f, 8f), new Vector2(110f, 56f), 34f, TextAlignmentOptions.Center);

        CreateText(popup.transform, "ScaleLabel", "크기", font,
            new Vector2(-332f, -85f), new Vector2(178f, 55f), 33f, TextAlignmentOptions.Center);
        var scaleSlider = CreateSlider(popup.transform, "ScaleSlider", new Vector2(2f, -85f), 0.4f, 2f, 1f);
        var scaleText = CreateText(popup.transform, "ScaleValueText", "1.00x", font,
            new Vector2(338f, -85f), new Vector2(110f, 56f), 34f, TextAlignmentOptions.Center);

        Button save = CreateButton(popup.transform, "SaveButton", "저장", font, new Vector2(-283f, -194f),
            new Color(0.14f, 0.60f, 0.61f, 1f));
        Button reset = CreateButton(popup.transform, "ResetButton", "초기화", font, new Vector2(0f, -194f),
            new Color(0.91f, 0.53f, 0.17f, 1f));
        Button close = CreateButton(popup.transform, "CloseButton", "닫기", font, new Vector2(283f, -194f),
            new Color(0.58f, 0.43f, 0.29f, 1f));

        var controller = popup.GetComponent<HealthMon3DJewelryAdjustPanel>()
            ?? Undo.AddComponent<HealthMon3DJewelryAdjustPanel>(popup);
        AssignReference(controller, "previewRig", rig);
        AssignReference(controller, "yawSlider", yawSlider);
        AssignReference(controller, "rollSlider", rollSlider);
        AssignReference(controller, "scaleSlider", scaleSlider);
        AssignReference(controller, "selectedNameText", selectedName);
        AssignReference(controller, "yawValueText", yawText);
        AssignReference(controller, "rollValueText", rollText);
        AssignReference(controller, "scaleValueText", scaleText);

        WireButton(save, controller, 0);
        WireButton(reset, controller, 1);
        WireButton(close, controller, 2);

        int wired = 0;
        if (palette != null)
        {
            string[] names = { "NecklaceDrag", "EarringDrag", "PendantDrag", "RingDrag" };
            for (int i = 0; i < names.Length; i++)
            {
                Transform buttonTransform = FindDescendant(palette, names[i]);
                if (buttonTransform == null) continue;
                var drag = buttonTransform.GetComponent<HealthMon3DPreviewDragButton>();
                if (drag == null) continue;
                AssignReference(drag, "adjustPanel", controller);
                if (rig != null) AssignReference(drag, "previewRig", rig);
                if (petImage != null) AssignReference(drag, "petPreviewImage", petImage);
                if (previewCamera != null) AssignReference(drag, "petPreviewCamera", previewCamera);
                // Always keep all four slots aligned with the existing palette order.
                AssignInt(drag, "slotIndex", i);
                wired++;
            }
        }

        if (petImage != null)
        {
            var surface = petImage.GetComponent<HealthMonPreviewJewelrySurface>();
            if (surface != null)
            {
                AssignReference(surface, "adjustPanel", controller);
                if (rig != null) AssignReference(surface, "previewRig", rig);
                AssignReference(surface, "petPreviewImage", petImage);
                if (previewCamera != null) AssignReference(surface, "petPreviewCamera", previewCamera);
            }
        }

        // Hide by default; the existing four palette drag buttons will open it.
        Undo.RecordObject(popup, UndoName);
        popup.SetActive(false);
        Undo.CollapseUndoOperations(group);
        EditorSceneManager.MarkSceneDirty(scene);
        Selection.activeGameObject = popup;
        EditorGUIUtility.PingObject(popup);

        string info = "회전·크기 편집 패널 자동 생성 완료!\n\n" +
                      "· 기존 CustomizationPanel 안에 구성했습니다.\n" +
                      "· 드래그 버튼 연결: " + wired + "/4\n" +
                      "· Preview Rig: " + (rig != null ? "연결됨" : "연결 확인 필요") + "\n" +
                      "· PetPreviewImage: " + (petImage != null ? "확인" : "확인 필요") + "\n" +
                      "· PetPreviewCamera: " + (previewCamera != null ? "확인" : "확인 필요") + "\n\n" +
                      "Ctrl+S로 저장하고 ▶ Play → 꾸미기 → 목걸이 버튼을 눌러 확인하세요.";
        EditorUtility.DisplayDialog("HealthMon 3D Jewelry", info, "확인");
        Debug.Log("[HealthMon Jewelry UI] 자동 생성 완료. Drag buttons wired=" + wired + "/4");
    }

    [MenuItem(MenuPath, true)]
    private static bool ValidateBuild() => !EditorApplication.isPlayingOrWillChangePlaymode;

    private static Transform FindSceneObject(Scene scene, string name)
    {
        return Resources.FindObjectsOfTypeAll<Transform>().FirstOrDefault(t =>
            t.name == name && t.gameObject.scene.IsValid() && t.gameObject.scene == scene);
    }

    private static Transform FindDescendant(Transform parent, string name)
    {
        if (parent == null) return null;
        foreach (Transform t in parent.GetComponentsInChildren<Transform>(true))
            if (t != parent && t.name == name) return t;
        return null;
    }

    private static GameObject EnsureObject(Transform parent, string name, params Type[] types)
    {
        Transform found = parent.Find(name);
        if (found == null)
        {
            var created = new GameObject(name, types);
            Undo.RegisterCreatedObjectUndo(created, UndoName);
            created.transform.SetParent(parent, false);
            return created;
        }

        foreach (Type type in types)
        {
            if (type == typeof(RectTransform) || type == typeof(Transform)) continue;
            if (found.GetComponent(type) == null) Undo.AddComponent(found.gameObject, type);
        }
        return found.gameObject;
    }

    private static void SetRect(RectTransform rect, float anchorX, float anchorY, Vector2 pos, Vector2 size)
    {
        Undo.RecordObject(rect, UndoName);
        rect.anchorMin = new Vector2(anchorX, anchorY);
        rect.anchorMax = new Vector2(anchorX, anchorY);
        rect.pivot = new Vector2(0.5f, 0.5f);
        rect.sizeDelta = size;
        rect.anchoredPosition = pos;
        rect.localRotation = Quaternion.identity;
        rect.localScale = Vector3.one;
    }

    private static void SetStretch(RectTransform rect, Vector2 min, Vector2 max)
    {
        Undo.RecordObject(rect, UndoName);
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = min;
        rect.offsetMax = max;
        rect.localRotation = Quaternion.identity;
        rect.localScale = Vector3.one;
    }

    private static TMP_Text CreateText(Transform parent, string name, string initialText,
        TMP_FontAsset font, Vector2 pos, Vector2 size, float fontSize, TextAlignmentOptions alignment)
    {
        GameObject go = EnsureObject(parent, name, typeof(RectTransform), typeof(CanvasRenderer), typeof(TextMeshProUGUI));
        SetRect(go.GetComponent<RectTransform>(), 0.5f, 0.5f, pos, size);
        var text = go.GetComponent<TextMeshProUGUI>();
        Undo.RecordObject(text, UndoName);
        if (font != null) text.font = font;
        text.text = initialText;
        text.fontSize = fontSize;
        text.enableAutoSizing = true;
        text.fontSizeMin = 22f;
        text.fontSizeMax = fontSize;
        text.color = Brown;
        text.alignment = alignment;
        text.raycastTarget = false;
        return text;
    }

    private static Slider CreateSlider(Transform parent, string name, Vector2 pos, float min, float max, float value)
    {
        GameObject go = EnsureObject(parent, name, typeof(RectTransform), typeof(Slider));
        SetRect(go.GetComponent<RectTransform>(), 0.5f, 0.5f, pos, new Vector2(420f, 56f));
        var slider = go.GetComponent<Slider>();
        Undo.RecordObject(slider, UndoName);

        if (slider.fillRect == null || slider.handleRect == null)
        {
            var background = EnsureObject(go.transform, "Background", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            SetRect(background.GetComponent<RectTransform>(), 0.5f, 0.5f, Vector2.zero, new Vector2(410f, 20f));
            Image backImage = background.GetComponent<Image>();
            backImage.sprite = null;
            backImage.color = Track;
            backImage.raycastTarget = false;

            GameObject fillArea = EnsureObject(go.transform, "Fill Area", typeof(RectTransform));
            SetStretch(fillArea.GetComponent<RectTransform>(), new Vector2(19f, 15f), new Vector2(-19f, -15f));
            GameObject fill = EnsureObject(fillArea.transform, "Fill", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            SetStretch(fill.GetComponent<RectTransform>(), Vector2.zero, Vector2.zero);
            Image fillImage = fill.GetComponent<Image>();
            fillImage.sprite = null;
            fillImage.color = Fill;
            fillImage.raycastTarget = false;

            GameObject handleArea = EnsureObject(go.transform, "Handle Slide Area", typeof(RectTransform));
            SetStretch(handleArea.GetComponent<RectTransform>(), new Vector2(18f, 0f), new Vector2(-18f, 0f));
            GameObject handle = EnsureObject(handleArea.transform, "Handle", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            SetRect(handle.GetComponent<RectTransform>(), 0.5f, 0.5f, Vector2.zero, new Vector2(45f, 50f));
            var handleImage = handle.GetComponent<Image>();
            handleImage.sprite = null;
            handleImage.color = Handle;
            handleImage.raycastTarget = true;

            slider.fillRect = fill.GetComponent<RectTransform>();
            slider.handleRect = handle.GetComponent<RectTransform>();
            slider.targetGraphic = handleImage;
        }
        else
        {
            // Also style sliders the user created manually in STEP 3.
            if (slider.fillRect.GetComponent<Image>() is Image fill) fill.color = Fill;
            if (slider.handleRect.GetComponent<Image>() is Image handle) { handle.color = Handle; slider.targetGraphic = handle; }
            Transform background = go.transform.Find("Background");
            if (background != null && background.GetComponent<Image>() is Image back) back.color = Track;
        }

        slider.minValue = min;
        slider.maxValue = max;
        slider.wholeNumbers = false;
        slider.SetValueWithoutNotify(value);
        return slider;
    }

    private static Button CreateButton(Transform parent, string name, string label,
        TMP_FontAsset font, Vector2 pos, Color backgroundColor)
    {
        GameObject go = EnsureObject(parent, name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image), typeof(Button));
        SetRect(go.GetComponent<RectTransform>(), 0.5f, 0.5f, pos, new Vector2(244f, 68f));
        var image = go.GetComponent<Image>();
        image.sprite = null;
        image.color = backgroundColor;
        image.raycastTarget = true;
        var button = go.GetComponent<Button>();
        button.targetGraphic = image;
        button.interactable = true;
        var colors = button.colors;
        colors.normalColor = Color.white;
        colors.highlightedColor = new Color(1.0f, 0.95f, 0.85f);
        colors.pressedColor = new Color(0.88f, 0.84f, 0.78f);
        colors.selectedColor = Color.white;
        button.colors = colors;

        var txt = CreateText(go.transform, "Text (TMP)", label, font, Vector2.zero,
            new Vector2(224f, 64f), 36f, TextAlignmentOptions.Center);
        txt.color = Color.white;
        return button;
    }

    private static void WireButton(Button button, HealthMon3DJewelryAdjustPanel controller, int kind)
    {
        Undo.RecordObject(button, UndoName);
        // This builder owns only the three adjust-panel buttons. Replace stale callbacks,
        // keeping repeated menu runs idempotent.
        for (int i = button.onClick.GetPersistentEventCount() - 1; i >= 0; i--)
            UnityEventTools.RemovePersistentListener(button.onClick, i);
        if (kind == 0) UnityEventTools.AddPersistentListener(button.onClick, controller.SaveSelected);
        else if (kind == 1) UnityEventTools.AddPersistentListener(button.onClick, controller.ResetSelected);
        else UnityEventTools.AddPersistentListener(button.onClick, controller.Close);
        EditorUtility.SetDirty(button);
    }

    private static void AssignReference(Component component, string fieldName, UnityEngine.Object value)
    {
        if (component == null || value == null) return;
        var obj = new SerializedObject(component);
        SerializedProperty prop = obj.FindProperty(fieldName);
        if (prop == null || prop.propertyType != SerializedPropertyType.ObjectReference) return;
        if (prop.objectReferenceValue == value) return;
        obj.Update();
        prop.objectReferenceValue = value;
        obj.ApplyModifiedProperties();
    }

    private static void AssignInt(Component component, string fieldName, int value)
    {
        if (component == null) return;
        var obj = new SerializedObject(component);
        SerializedProperty prop = obj.FindProperty(fieldName);
        if (prop == null || prop.propertyType != SerializedPropertyType.Integer) return;
        obj.Update();
        prop.intValue = value;
        obj.ApplyModifiedProperties();
    }

    private static TMP_FontAsset FindKoreanFont(RectTransform root)
    {
        string[] guids = AssetDatabase.FindAssets("Maplestory t:TMP_FontAsset");
        foreach (string guid in guids)
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(path);
            if (font != null && font.name.Contains("Bold")) return font;
        }
        foreach (string guid in guids)
        {
            var font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(AssetDatabase.GUIDToAssetPath(guid));
            if (font != null) return font;
        }
        return root.GetComponentsInChildren<TMP_Text>(true)
            .Where(t => t.font != null && t.text.Any(c => c >= '\uAC00' && c <= '\uD7A3'))
            .Select(t => t.font).FirstOrDefault();
    }
}
#endif
