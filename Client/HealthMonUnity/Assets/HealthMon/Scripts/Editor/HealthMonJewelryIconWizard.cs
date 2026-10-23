#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Makes REAL jewelry-asset preview sprites and places them in the existing
/// CollectionPanel, JewelryEquipmentOverlay and selected item info panels.
/// Does not replace the working customization / quest / save scripts.
/// </summary>
public class HealthMonJewelryIconWizard : EditorWindow
{
    private static readonly string[] Names = { "목걸이", "귀걸이", "펜던트", "반지" };
    private static readonly string[] Stems = { "necklace", "earring", "pendant", "ring" };
    private static readonly string[][] Keywords =
    {
        new[] { "Necklace", "Chain", "목걸이", "Badge" },
        new[] { "Earring", "귀걸이", "Ribbon" },
        new[] { "Pendant", "펜던트", "Glasses" },
        new[] { "Ring", "반지", "Cap" },
    };
    private static readonly string[][] Callbacks =
    {
        new[] { "SelectNecklace", "SelectBadge" },
        new[] { "SelectEarring", "SelectRibbon" },
        new[] { "SelectPendant", "SelectGlasses" },
        new[] { "SelectRing", "SelectCap" },
    };

    private const string OutputFolder = "Assets/HealthMon/Art/UI/JewelryIcons";
    [SerializeField] private GameObject[] prefabs = new GameObject[4];
    private readonly Sprite[] sprites = new Sprite[4];
    private bool working;
    private int cursor;
    private double started;
    private readonly List<string> warnings = new List<string>();

    [MenuItem("HealthMon/Jewelry/Generate Item Icons and Apply")]
    public static void ShowWindow()
    {
        GetWindow<HealthMonJewelryIconWizard>("헬스몬 장신구 아이콘").minSize = new Vector2(490, 310);
    }

    private void OnGUI()
    {
        EditorGUILayout.Space(10);
        EditorGUILayout.LabelField("구매한 GanzSe Jewelry 모델을 그대로 UI 아이콘으로 사용", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox("Project 창의 Jewelry 프리팹 4개를 아래 칸에 드래그하세요.\n아이콘 PNG 생성 → 도감 카드 → 장신구 팝업 → 선택 아이템 이미지까지 한 번에 적용합니다.", MessageType.Info);
        EditorGUILayout.Space(8);
        if (prefabs == null || prefabs.Length != 4) Array.Resize(ref prefabs, 4);
        for (int i = 0; i < 4; i++)
        {
            prefabs[i] = (GameObject)EditorGUILayout.ObjectField(Names[i] + "  3D 모델", prefabs[i], typeof(GameObject), false);
        }
        EditorGUILayout.Space(10);
        EditorGUI.BeginDisabledGroup(working);
        if (GUILayout.Button("① 아이콘 PNG 생성 + 기존 UI 자동 배치", GUILayout.Height(44)))
            BeginGeneration();
        EditorGUI.EndDisabledGroup();
        if (working) EditorGUILayout.HelpBox("Unity 에셋 미리보기 생성 중: " + (cursor + 1) + " / 4", MessageType.Info);
        EditorGUILayout.HelpBox("기존 CustomizationPrototype.cs, HealthMonJewelryOverlayUI.cs, HealthMonAccessoryView.cs를 변경하지 않습니다.\n생성한 아이콘은 " + OutputFolder + "에 저장됩니다.", MessageType.None);
    }

    private void BeginGeneration()
    {
        for (int i = 0; i < 4; i++)
        {
            if (prefabs[i] == null)
            {
                EditorUtility.DisplayDialog("장신구 선택 필요", Names[i] + "의 3D 프리팹을 넣어주세요.", "확인");
                return;
            }
        }
        if (!UnityEngine.SceneManagement.SceneManager.GetActiveScene().IsValid())
        {
            EditorUtility.DisplayDialog("씬 확인", "MainARScene을 먼저 열어주세요.", "확인");
            return;
        }
        Directory.CreateDirectory(OutputFolder);
        warnings.Clear();
        cursor = 0;
        working = true;
        started = EditorApplication.timeSinceStartup;
        AssetPreview.SetPreviewTextureCacheSize(128);
        EditorApplication.update -= Tick;
        EditorApplication.update += Tick;
        Repaint();
    }

    private void Tick()
    {
        if (!working) return;
        if (cursor >= 4)
        {
            StopTick();
            ApplyToScene();
            return;
        }
        GameObject prefab = prefabs[cursor];
        Texture2D preview = AssetPreview.GetAssetPreview(prefab);
        // AssetPreview loads 3D thumbnails asynchronously. Don't save the generic
        // small Unity cube icon as a final thumbnail.
        if (preview == null && EditorApplication.timeSinceStartup - started < 20.0)
        {
            Repaint();
            return;
        }
        if (preview != null)
        {
            try
            {
                SaveAsSprite(preview, cursor);
            }
            catch (Exception ex)
            {
                warnings.Add(Names[cursor] + " 이미지 저장 실패: " + ex.Message);
            }
        }
        else
        {
            warnings.Add(Names[cursor] + " 프리팹 미리보기 생성 실패. PNG를 수동 등록해 주세요.");
        }
        cursor++;
        started = EditorApplication.timeSinceStartup;
        Repaint();
    }

    private void StopTick()
    {
        working = false;
        EditorApplication.update -= Tick;
        Repaint();
    }

    private void OnDisable() { StopTick(); }

    private void SaveAsSprite(Texture2D source, int i)
    {
        RenderTexture temp = RenderTexture.GetTemporary(512, 512, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Default);
        RenderTexture previous = RenderTexture.active;
        Texture2D target = null;
        try
        {
            Graphics.Blit(source, temp);
            RenderTexture.active = temp;
            target = new Texture2D(512, 512, TextureFormat.RGBA32, false);
            target.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
            target.Apply();
            string assetPath = OutputFolder + "/icon_" + Stems[i] + ".png";
            File.WriteAllBytes(assetPath, target.EncodeToPNG());
            AssetDatabase.ImportAsset(assetPath, ImportAssetOptions.ForceUpdate);
            var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if (importer != null)
            {
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.mipmapEnabled = false;
                importer.alphaIsTransparency = true;
                importer.filterMode = FilterMode.Bilinear;
                importer.SaveAndReimport();
            }
            sprites[i] = AssetDatabase.LoadAssetAtPath<Sprite>(assetPath);
            if (sprites[i] == null) warnings.Add(Names[i] + " Sprite import 확인 필요");
        }
        finally
        {
            if (target != null) DestroyImmediate(target);
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(temp);
        }
    }

    private void ApplyToScene()
    {
        Transform collectionPanel = FindSceneTransform("CollectionPanel");
        Transform customizationPanel = FindSceneTransform("CustomizationPanel");
        Transform managerObject = FindCustomizationManager();
        if (collectionPanel == null || customizationPanel == null || managerObject == null)
        {
            EditorUtility.DisplayDialog("아이콘 저장 완료 · UI 연결 확인", "아이콘 PNG는 저장했습니다. MainARScene에 CollectionPanel / CustomizationPanel / CustomizationManager가 있는지 확인해 주세요.", "확인");
            return;
        }
        Transform grid = collectionPanel.Find("ItemGrid");
        if (grid == null)
        {
            EditorUtility.DisplayDialog("ItemGrid 없음", "CollectionPanel의 ItemGrid를 확인하세요. PNG는 이미 저장했습니다.", "확인");
            return;
        }

        Button[] cards = MatchCards(grid.GetComponentsInChildren<Button>(true));
        for (int i = 0; i < 4; i++)
        {
            if (sprites[i] == null || cards[i] == null) continue;
            Image cardIcon = EnsureImage(cards[i].transform, "JewelryItemIcon", sprites[i]);
            CardIconPlacement(cardIcon.rectTransform);
            // Put existing card text beneath the icon, without changing button OnClick.
            var texts = cards[i].GetComponentsInChildren<TMP_Text>(true);
            foreach (TMP_Text t in texts)
            {
                if (t.transform == cardIcon.transform) continue;
                RectTransform rt = t.rectTransform;
                // Move only labels that occupy a large part of the card.
                if (rt.anchorMax.y - rt.anchorMin.y >= .7f || rt.sizeDelta.y >= 45f)
                {
                    Undo.RecordObject(rt, "Move jewelry card text below icon");
                    rt.anchorMin = new Vector2(.04f, .02f);
                    rt.anchorMax = new Vector2(.96f, .38f);
                    rt.offsetMin = rt.offsetMax = Vector2.zero;
                }
            }
        }

        Button[] popupButtons = new Button[4];
        Transform rows = customizationPanel.Find("JewelryEquipmentOverlay/EquipmentCard/Rows");
        if (rows != null)
        {
            for (int i = 0; i < 4; i++)
            {
                Transform row = rows.Find(Names[i] + "Row");
                if (row == null || sprites[i] == null) continue;
                Image icon = EnsureImage(row, "JewelryItemIcon", sprites[i]);
                icon.transform.SetSiblingIndex(0);
                var layout = icon.GetComponent<LayoutElement>();
                if (layout == null) layout = Undo.AddComponent<LayoutElement>(icon.gameObject);
                layout.minWidth = 50;
                layout.preferredWidth = 60;
                layout.flexibleWidth = 0;
                layout.minHeight = 50;
                layout.preferredHeight = 60;
                layout.flexibleHeight = 0;
                popupButtons[i] = row.Find("ToggleButton")?.GetComponent<Button>();
            }
        }
        else warnings.Add("JewelryEquipmentOverlay Rows를 찾지 못해 팝업 아이콘은 건너뛰었습니다.");

        var selectedImages = new List<Image>();
        Transform collectionInfo = collectionPanel.Find("SelectedItemPanel");
        Transform customizationInfo = customizationPanel.Find("ItemInfoPanel");
        if (collectionInfo != null)
        {
            Image selected = EnsureImage(collectionInfo, "SelectedItemJewelryIcon", sprites[0]);
            SelectedIconPlacement(selected.rectTransform);
            selectedImages.Add(selected);
        }
        if (customizationInfo != null)
        {
            Image selected = EnsureImage(customizationInfo, "SelectedItemJewelryIcon", sprites[0]);
            SelectedIconPlacement(selected.rectTransform);
            selectedImages.Add(selected);
        }
        var binder = managerObject.GetComponent<HealthMonJewelryIconBinder>();
        if (binder == null) binder = Undo.AddComponent<HealthMonJewelryIconBinder>(managerObject.gameObject);
        Undo.RecordObject(binder, "Configure Jewelry Icon Binder");
        binder.Configure(cards, popupButtons, sprites.ToArray(), selectedImages.ToArray());
        EditorUtility.SetDirty(binder);
        EditorSceneManager.MarkSceneDirty(collectionPanel.gameObject.scene);
        AssetDatabase.SaveAssets();

        string message = "아이콘 4종 저장 및 UI 연결 완료!\n" + OutputFolder + "\n\n";
        message += warnings.Count == 0 ? "도감 · 팝업 · 선택 상세 이미지 연결 완료" : string.Join("\n", warnings);
        EditorUtility.DisplayDialog("HealthMon Jewelry", message, "확인");
        Selection.activeGameObject = collectionPanel.gameObject;
    }

    private static Transform FindSceneTransform(string name)
    {
        foreach (Transform t in UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (t.name == name && t.gameObject.scene.IsValid()) return t;
        return null;
    }

    private static Transform FindCustomizationManager()
    {
        foreach (CustomizationPrototype component in UnityEngine.Object.FindObjectsByType<CustomizationPrototype>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (component.gameObject.scene.IsValid()) return component.transform;
        return null;
    }

    private static Button[] MatchCards(Button[] buttons)
    {
        var result = new Button[4];
        var used = new HashSet<Button>();
        for (int i = 0; i < 4; i++)
        {
            foreach (Button b in buttons)
            {
                if (b == null || used.Contains(b)) continue;
                string text = b.name + " " + string.Join(" ", b.GetComponentsInChildren<TMP_Text>(true).Select(t => t.text));
                bool found = Keywords[i].Any(keyword => text.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0);
                if (!found)
                {
                    for (int n = 0; n < b.onClick.GetPersistentEventCount(); n++)
                        if (Callbacks[i].Contains(b.onClick.GetPersistentMethodName(n))) found = true;
                }
                if (!found) continue;
                result[i] = b;
                used.Add(b);
                break;
            }
        }
        // Existing ItemGrid normally contains exactly four item buttons. Keep its order
        // if names/text are custom UI labels and cannot be inferred.
        if (buttons.Length == 4)
        {
            for (int i = 0; i < 4; i++)
                if (result[i] == null && !used.Contains(buttons[i]))
                {
                    result[i] = buttons[i];
                    used.Add(buttons[i]);
                }
        }
        return result;
    }

    private static Image EnsureImage(Transform parent, string name, Sprite sprite)
    {
        Transform found = parent.Find(name);
        GameObject go;
        if (found == null)
        {
            go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            Undo.RegisterCreatedObjectUndo(go, "Add Jewelry Icon");
            go.transform.SetParent(parent, false);
        }
        else go = found.gameObject;
        Image image = go.GetComponent<Image>();
        if (image == null) image = Undo.AddComponent<Image>(go);
        Undo.RecordObject(image, "Set Jewelry Icon");
        image.sprite = sprite;
        image.color = Color.white;
        image.preserveAspect = true;
        image.raycastTarget = false;
        return image;
    }

    private static void CardIconPlacement(RectTransform icon)
    {
        Undo.RecordObject(icon, "Place Jewelry Card Icon");
        icon.anchorMin = new Vector2(.20f, .43f);
        icon.anchorMax = new Vector2(.80f, .95f);
        icon.offsetMin = icon.offsetMax = Vector2.zero;
        icon.localScale = Vector3.one;
    }

    private static void SelectedIconPlacement(RectTransform icon)
    {
        Undo.RecordObject(icon, "Place Selected Jewelry Icon");
        icon.anchorMin = icon.anchorMax = new Vector2(.90f, .80f);
        icon.pivot = new Vector2(1, 1);
        icon.anchoredPosition = Vector2.zero;
        icon.sizeDelta = new Vector2(105, 105);
        icon.localScale = Vector3.one;
    }
}
#endif
