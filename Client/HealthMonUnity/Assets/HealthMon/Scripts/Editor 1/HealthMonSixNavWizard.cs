#if UNITY_EDITOR
using System;
using System.IO;
using System.Collections.Generic;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class HealthMonSixNavWizard
{
    private const string OutputFolder = "Assets/HealthMon/GeneratedUI/SixNav";

    private static readonly string[] ButtonNames =
    {
        "HomeButton", "FoodButton", "DialogueButton",
        "QuestButton", "CollectionButton", "WearableButton"
    };
    private static readonly string[] Labels =
    {
        "홈", "촬영", "대화", "퀘스트", "도감", "웨어러블"
    };
    private static readonly string[] PanelNames =
    {
        "HomePanel", "FoodScanPanel", "DialoguePanel",
        "QuestPanel", "CollectionPanel", "WearablePanel"
    };

    [MenuItem("HealthMon/UI/Build Six-Button Bottom Nav")]
    public static void Build()
    {
        if (Application.isPlaying)
        {
            EditorUtility.DisplayDialog("HealthMon", "Play 모드를 종료하고 실행하세요.", "확인");
            return;
        }

        Canvas canvas = FindCanvasWithOriginalNav();
        if (canvas == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "현재 씬에서 Canvas/BottomNav를 찾지 못했습니다. MainARScene을 열어주세요.", "확인");
            return;
        }

        Transform oldNav = canvas.transform.Find("BottomNav");
        if (oldNav == null)
        {
            EditorUtility.DisplayDialog("HealthMon", "Canvas 바로 아래 BottomNav가 없습니다.", "확인");
            return;
        }
        if (canvas.transform.Find("BottomNavV2") != null)
        {
            EditorUtility.DisplayDialog("HealthMon", "BottomNavV2가 이미 있습니다. 중복 생성하지 않았습니다.", "확인");
            return;
        }

        Button[] originalButtons = new Button[6];
        GameObject[] panels = new GameObject[6];
        for (int i = 0; i < 6; i++)
        {
            Transform t = oldNav.Find(ButtonNames[i]);
            originalButtons[i] = t != null ? t.GetComponent<Button>() : null;
            Transform panel = canvas.transform.Find(PanelNames[i]);
            panels[i] = panel != null ? panel.gameObject : null;
            if (originalButtons[i] == null || panels[i] == null)
            {
                EditorUtility.DisplayDialog("HealthMon",
                    "필수 오브젝트를 찾지 못했습니다: " + (originalButtons[i] == null ? ButtonNames[i] : PanelNames[i]) +
                    "\n기존 Hierarchy 이름을 확인하세요.", "확인");
                return;
            }
            if (originalButtons[i].onClick.GetPersistentEventCount() == 0)
            {
                if (!EditorUtility.DisplayDialog("버튼 연결 확인",
                    ButtonNames[i] + "의 OnClick에 연결된 함수가 없습니다. UI는 만들지만 해당 버튼은 자동으로 화면을 열지 못할 수 있습니다. 계속할까요?",
                    "계속", "취소")) return;
            }
        }

        EnsureFolder("Assets/HealthMon");
        EnsureFolder("Assets/HealthMon/GeneratedUI");
        EnsureFolder(OutputFolder);
        Sprite navSprite = GenerateRoundedSprite("NavBackdrop", 34, 4,
            new Color32(33, 67, 99, 255), new Color32(13, 37, 61, 255), new Color32(84, 153, 185, 255));
        Sprite buttonSprite = GenerateRoundedSprite("NavButton", 23, 3,
            new Color32(58, 118, 155, 255), new Color32(26, 66, 103, 255), new Color32(115, 181, 215, 255));
        Sprite selectedSprite = GenerateRoundedSprite("NavButtonSelected", 23, 3,
            new Color32(255, 224, 132, 255), new Color32(225, 163, 51, 255), new Color32(255, 242, 193, 255));

        GameObject newNav = UnityEngine.Object.Instantiate(oldNav.gameObject, canvas.transform);
        Undo.RegisterCreatedObjectUndo(newNav, "Create HealthMon six-button navigation");
        newNav.name = "BottomNavV2";
        newNav.SetActive(true);
        newNav.transform.SetAsLastSibling();

        RectTransform navRT = newNav.GetComponent<RectTransform>();
        SetRect(navRT, new Vector2(0, 0), new Vector2(1, 0),
            new Vector2(0.5f, 0), new Vector2(0, 24), new Vector2(-48, 260));

        foreach (var oldLayout in newNav.GetComponents<HorizontalLayoutGroup>())
            Undo.DestroyObjectImmediate(oldLayout);
        foreach (var oldFitter in newNav.GetComponents<ContentSizeFitter>())
            Undo.DestroyObjectImmediate(oldFitter);
        foreach (var oldGrid in newNav.GetComponents<GridLayoutGroup>())
            Undo.DestroyObjectImmediate(oldGrid);

        Image navBG = newNav.GetComponent<Image>();
        if (navBG == null) navBG = Undo.AddComponent<Image>(newNav);
        navBG.sprite = navSprite;
        navBG.type = Image.Type.Sliced;
        navBG.color = Color.white;
        navBG.raycastTarget = false;

        Transform topRow = NewRow("TopRow", newNav.transform, -18);
        Transform bottomRow = NewRow("BottomRow", newNav.transform, -133);

        Image[] newImages = new Image[6];
        TMP_Text[] newLabels = new TMP_Text[6];
        for (int i = 0; i < 6; i++)
        {
            Transform child = newNav.transform.Find(ButtonNames[i]);
            if (child == null)
            {
                EditorUtility.DisplayDialog("HealthMon", "복제 버튼을 찾지 못했습니다: " + ButtonNames[i], "확인");
                return;
            }
            Image buttonImage = child.GetComponent<Image>();
            Sprite originalIcon = buttonImage != null ? buttonImage.sprite : null;
            Undo.SetTransformParent(child, i < 3 ? topRow : bottomRow, "Arrange HealthMon nav buttons");
            RectTransform childRT = child as RectTransform;
            childRT.localScale = Vector3.one;
            childRT.localRotation = Quaternion.identity;

            // Keep existing GameObjects and persistent UIManager Show...() calls.
            var oldLe = child.GetComponent<LayoutElement>();
            if (oldLe != null) Undo.DestroyObjectImmediate(oldLe);
            LayoutElement element = Undo.AddComponent<LayoutElement>(child.gameObject);
            element.minHeight = 100;
            element.preferredHeight = 100;
            element.flexibleWidth = 1;

            if (buttonImage == null) buttonImage = Undo.AddComponent<Image>(child.gameObject);
            buttonImage.sprite = buttonSprite;
            buttonImage.type = Image.Type.Sliced;
            buttonImage.color = Color.white;
            buttonImage.raycastTarget = true;
            newImages[i] = buttonImage;

            Button button = child.GetComponent<Button>();
            button.targetGraphic = buttonImage;
            button.transition = Selectable.Transition.ColorTint;
            ColorBlock cb = button.colors;
            cb.normalColor = Color.white;
            cb.highlightedColor = new Color(0.95f, 0.97f, 1f);
            cb.pressedColor = new Color(0.75f, 0.85f, 0.95f);
            cb.selectedColor = Color.white;
            cb.disabledColor = new Color(0.65f, 0.65f, 0.65f, 0.6f);
            button.colors = cb;

            Transform iconTf = child.Find("NavIconV2");
            if (iconTf == null)
            {
                GameObject iconObj = new GameObject("NavIconV2", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
                Undo.RegisterCreatedObjectUndo(iconObj, "Create nav icon");
                iconObj.transform.SetParent(child, false);
                iconTf = iconObj.transform;
            }
            iconTf.SetAsFirstSibling();
            RectTransform iconRT = iconTf as RectTransform;
            SetRect(iconRT, new Vector2(0.5f, 1), new Vector2(0.5f, 1),
                new Vector2(0.5f, 1), new Vector2(0, -9), new Vector2(50, 52));
            Image icon = iconTf.GetComponent<Image>();
            icon.sprite = originalIcon;
            icon.color = Color.white;
            icon.preserveAspect = true;
            icon.raycastTarget = false;

            TMP_Text label = child.GetComponentInChildren<TMP_Text>(true);
            if (label == null)
            {
                GameObject textGo = new GameObject("Text (TMP)", typeof(RectTransform), typeof(CanvasRenderer), typeof(TextMeshProUGUI));
                Undo.RegisterCreatedObjectUndo(textGo, "Create nav label");
                textGo.transform.SetParent(child, false);
                label = textGo.GetComponent<TMP_Text>();
            }
            label.text = Labels[i];
            label.fontSize = 27;
            label.enableAutoSizing = true;
            label.fontSizeMin = 21;
            label.fontSizeMax = 27;
            label.alignment = TextAlignmentOptions.Center;
            label.color = new Color(0.98f, 0.98f, 1f, 1f);
            label.raycastTarget = false;
            newLabels[i] = label;
            RectTransform labelRT = label.rectTransform;
            SetRect(labelRT, new Vector2(0, 0), new Vector2(1, 0),
                new Vector2(0.5f, 0), new Vector2(0, 7), new Vector2(-12, 38));

            EditorUtility.SetDirty(button);
        }

        HealthMonSixNavHighlighter selection = newNav.GetComponent<HealthMonSixNavHighlighter>();
        if (selection == null) selection = Undo.AddComponent<HealthMonSixNavHighlighter>(newNav);
        selection.Configure(newImages, newLabels, panels, buttonSprite, selectedSprite);

        Undo.RecordObject(oldNav.gameObject, "Disable original navigation (backup)");
        oldNav.gameObject.SetActive(false);

        EditorUtility.SetDirty(newNav);
        EditorSceneManager.MarkSceneDirty(canvas.gameObject.scene);
        Selection.activeGameObject = newNav;
        EditorUtility.DisplayDialog("HealthMon", "6개 버튼의 새 하단 메뉴를 만들었습니다.\n기존 BottomNav는 비활성화된 채 보관됩니다.\nCtrl+S로 MainARScene을 저장하세요.", "확인");
    }

    private static Canvas FindCanvasWithOriginalNav()
    {
        Canvas[] canvases = UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (Canvas canvas in canvases)
        {
            if (!canvas.gameObject.scene.IsValid() || !canvas.gameObject.scene.isLoaded) continue;
            if (canvas.transform.Find("BottomNav") != null) return canvas;
        }
        return null;
    }

    private static Transform NewRow(string name, Transform parent, float yFromTop)
    {
        GameObject go = new GameObject(name, typeof(RectTransform), typeof(HorizontalLayoutGroup));
        Undo.RegisterCreatedObjectUndo(go, "Create nav row");
        go.transform.SetParent(parent, false);
        RectTransform rt = go.GetComponent<RectTransform>();
        SetRect(rt, new Vector2(0, 1), new Vector2(1, 1),
            new Vector2(0.5f, 1), new Vector2(0, yFromTop), new Vector2(-28, 103));
        var layout = go.GetComponent<HorizontalLayoutGroup>();
        layout.padding = new RectOffset(0, 0, 0, 0);
        layout.spacing = 12;
        layout.childAlignment = TextAnchor.MiddleCenter;
        layout.childControlWidth = true;
        layout.childControlHeight = true;
        layout.childScaleWidth = false;
        layout.childScaleHeight = false;
        layout.childForceExpandWidth = true;
        layout.childForceExpandHeight = true;
        return go.transform;
    }

    private static void SetRect(RectTransform t, Vector2 min, Vector2 max, Vector2 pivot,
        Vector2 pos, Vector2 size)
    {
        t.anchorMin = min;
        t.anchorMax = max;
        t.pivot = pivot;
        t.anchoredPosition = pos;
        t.sizeDelta = size;
        t.localScale = Vector3.one;
        t.localRotation = Quaternion.identity;
    }

    private static void EnsureFolder(string folder)
    {
        if (AssetDatabase.IsValidFolder(folder)) return;
        string parent = Path.GetDirectoryName(folder).Replace('\\', '/');
        string name = Path.GetFileName(folder);
        if (!AssetDatabase.IsValidFolder(parent)) EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent, name);
    }

    private static Sprite GenerateRoundedSprite(string name, float radius, float stroke,
        Color top, Color bottom, Color border)
    {
        string assetPath = OutputFolder + "/" + name + ".png";
        if (!File.Exists(Path.GetFullPath(assetPath)))
        {
            const int size = 128;
            Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, false);
            Color[] pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    Vector2 p = new Vector2(x + 0.5f - size / 2f, y + 0.5f - size / 2f);
                    Vector2 q = new Vector2(Mathf.Abs(p.x), Mathf.Abs(p.y)) - new Vector2(size / 2f - radius, size / 2f - radius);
                    float distance = Mathf.Min(Mathf.Max(q.x, q.y), 0f) + new Vector2(Mathf.Max(q.x, 0f), Mathf.Max(q.y, 0f)).magnitude - radius;
                    float alpha = Mathf.Clamp01(0.5f - distance);
                    Color c = distance > -stroke ? border : Color.Lerp(bottom, top, y / (float)(size - 1));
                    c.a *= alpha;
                    pixels[y * size + x] = c;
                }
            }
            texture.SetPixels(pixels);
            texture.Apply();
            File.WriteAllBytes(Path.GetFullPath(assetPath), texture.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(texture);
        }

        AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceSynchronousImport);
        TextureImporter importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer != null)
        {
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = 100;
            importer.spriteBorder = new Vector4(40, 40, 40, 40);
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
            importer.SaveAndReimport();
        }
        return AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
    }
}
#endif
