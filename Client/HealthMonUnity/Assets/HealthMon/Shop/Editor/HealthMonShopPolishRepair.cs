#if UNITY_EDITOR
using System;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

/// <summary>
/// Works with the previously installed HealthMon Shop v2. Does not replace
/// MainARScene, does not modify backend purchase or player-state scripts.
/// </summary>
public static class HealthMonShopPolishRepair
{
    const string Root = "Assets/HealthMon/Shop";
    const string DynamicFontPath = Root + "/Fonts/HealthMonShop_KoreanDynamic.asset";
    const string SourceFontPath = "Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf";
    const string CatalogPath = Root + "/HealthMonShopCatalog.asset";

    [MenuItem("Tools/HealthMon/Shop/4. 상점 폰트 · 하단 버튼 · 카드 수정 (백업)")]
    public static void ApplyAll()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "Play 모드를 종료하고 실행해 주세요.", "확인");
            return;
        }
        var canvas = FindGameCanvas();
        if (canvas == null)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "MainARScene에서 UI/Canvas/HomePanel을 찾을 수 없습니다.", "확인");
            return;
        }
        var shop = canvas.GetComponentInChildren<HealthMonShopScreen>(true);
        if (shop == null)
        {
            EditorUtility.DisplayDialog("HealthMon Shop", "먼저 기존 메뉴 '1. Shop UI 설치'로 상점을 생성하세요.", "확인");
            return;
        }
        try
        {
            SaveBackup();
            ImportSprites();
            var font = CreateOrGetKoreanFont();
            if (font == null)
            {
                EditorUtility.DisplayDialog("HealthMon Shop", "한글 TTF 파일을 찾지 못했습니다. 먼저 Project에 Maplestory Bold.ttf가 있는지 확인하거나, TMP Dynamic 폰트를 만든 후 '5. 폰트만 적용'을 실행하세요.", "확인");
                return;
            }
            FixCatalogSprites(shop);
            FixSpriteReferences(shop);
            FixTypography(shop, font);
            CreateBottomShopButton(canvas, shop, font);
            EditorUtility.SetDirty(shop);
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            AssetDatabase.SaveAssets();
            Selection.activeGameObject = shop.gameObject;
            EditorUtility.DisplayDialog("HealthMon Shop", "상점 폰트, 상품 이미지, BottomNavV2의 7번째 상점 버튼 적용 완료!\n\n씬 백업은 Assets/HealthMon/Shop/Backups에 저장됐습니다.\n\nCtrl+S를 누르고 Play에서 확인하세요.", "확인");
        }
        catch (Exception ex)
        {
            Debug.LogException(ex);
            EditorUtility.DisplayDialog("HealthMon Shop", "수정 중 오류가 발생했습니다. Console을 확인하세요. 기존 씬 백업으로 복구할 수 있습니다.\n" + ex.Message, "확인");
        }
    }

    [MenuItem("Tools/HealthMon/Shop/5. 상점 한글 폰트만 다시 적용")]
    public static void ApplyFontsOnly()
    {
        var canvas = FindGameCanvas();
        var shop = canvas != null ? canvas.GetComponentInChildren<HealthMonShopScreen>(true) : null;
        if (shop == null) { Debug.LogWarning("[Shop] HealthMonShopUI를 찾을 수 없습니다."); return; }
        var font = CreateOrGetKoreanFont();
        if (font == null) return;
        FixTypography(shop, font);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
    }

    [MenuItem("Tools/HealthMon/Shop/6. 상점 연결 진단 (Console)")]
    public static void InspectShop()
    {
        var canvas = FindGameCanvas();
        var shop = canvas != null ? canvas.GetComponentInChildren<HealthMonShopScreen>(true) : null;
        if (shop == null) { Debug.LogWarning("[Shop] 상점이 씬에 없습니다."); return; }
        int images = 0, missing = 0;
        foreach (var img in shop.GetComponentsInChildren<Image>(true))
        {
            images++;
            if (img.sprite == null && img.name != "ShopOverlay" && !img.name.EndsWith("Modal"))
            { missing++; Debug.LogWarning("[Shop] 이미지 스프라이트 없음: " + img.name, img); }
        }
        int texts = 0, notDynamic = 0;
        foreach (var label in shop.GetComponentsInChildren<TMP_Text>(true))
        {
            texts++;
            if (label.font == null || label.font.atlasPopulationMode != AtlasPopulationMode.Dynamic)
                notDynamic++;
        }
        var nav = canvas.transform.Find("BottomNavV2/BottomRow/ShopButton");
        Debug.Log($"[Shop] Image {images}개(누락 추정 {missing}), TMP {texts}개(동적 폰트 아닌 것 {notDynamic}), 하단 상점버튼: {(nav == null ? "없음" : "있음")}");
    }

    static Canvas FindGameCanvas()
    {
        foreach (var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (c.transform.Find("HomePanel") != null && c.transform.Find("BottomNavV2") != null)
                return c;
        return null;
    }

    static void EnsureFolder(string path)
    {
        var bits = path.Split('/');
        var current = bits[0];
        for (int i = 1; i < bits.Length; i++)
        {
            var next = current + "/" + bits[i];
            if (!AssetDatabase.IsValidFolder(next)) AssetDatabase.CreateFolder(current, bits[i]);
            current = next;
        }
    }

    static void SaveBackup()
    {
        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || string.IsNullOrEmpty(scene.path))
            throw new Exception("먼저 MainARScene을 저장해 주세요.");
        EditorSceneManager.SaveScene(scene);
        EnsureFolder(Root + "/Backups");
        var dest = Root + "/Backups/" + Path.GetFileNameWithoutExtension(scene.path) +
                   "_BeforeShopFontNav_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
        if (!AssetDatabase.CopyAsset(scene.path, dest)) throw new Exception("씬 백업 복사에 실패했습니다.");
        Debug.Log("[Shop] 씬 백업 생성: " + dest);
    }

    static void ImportSprites()
    {
        string folder = Root + "/Sprites";
        if (!AssetDatabase.IsValidFolder(folder)) throw new Exception("Shop/Sprites 폴더를 찾지 못했습니다.");
        foreach (string absolute in Directory.GetFiles(folder, "*.png"))
        {
            string relative = absolute.Replace('\\', '/');
            var importer = AssetImporter.GetAtPath(relative) as TextureImporter;
            if (importer == null) continue;
            bool changed = false;
            if (importer.textureType != TextureImporterType.Sprite) { importer.textureType = TextureImporterType.Sprite; changed = true; }
            if (!importer.alphaIsTransparency) { importer.alphaIsTransparency = true; changed = true; }
            if (importer.spriteImportMode != SpriteImportMode.Single) { importer.spriteImportMode = SpriteImportMode.Single; changed = true; }
            string filename = Path.GetFileNameWithoutExtension(relative);
            Vector4 border = filename.StartsWith("Shop") && filename != "ShopBackground" && filename != "ShopPill"
                ? new Vector4(34, 34, 34, 34) : Vector4.zero;
            if (importer.spriteBorder != border) { importer.spriteBorder = border; changed = true; }
            if (changed) importer.SaveAndReimport();
        }
        AssetDatabase.Refresh();
    }

    static TMP_FontAsset CreateOrGetKoreanFont()
    {
        var asset = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(DynamicFontPath);
        if (asset != null)
        {
            if (asset.atlasPopulationMode != AtlasPopulationMode.Dynamic)
            {
                asset.atlasPopulationMode = AtlasPopulationMode.Dynamic;
                EditorUtility.SetDirty(asset);
            }
            return asset;
        }
        var source = AssetDatabase.LoadAssetAtPath<Font>(SourceFontPath);
        if (source == null)
        {
            Debug.LogError("[Shop] 소스 폰트를 찾지 못했습니다: " + SourceFontPath);
            return null;
        }
        EnsureFolder(Root + "/Fonts");
        asset = TMP_FontAsset.CreateFontAsset(source, 90, 9, GlyphRenderMode.SDFAA,
            1024, 1024, AtlasPopulationMode.Dynamic, true);
        if (asset == null) return null;
        asset.name = "HealthMonShop_KoreanDynamic";
        AssetDatabase.CreateAsset(asset, DynamicFontPath);
        // TMP creates the material and atlas in memory. Save them as sub-assets
        // so the font still works after editor restarts and on Android builds.
        if (asset.material != null && !AssetDatabase.Contains(asset.material))
            AssetDatabase.AddObjectToAsset(asset.material, asset);
        if (asset.atlasTextures != null)
        {
            foreach (var atlas in asset.atlasTextures)
                if (atlas != null && !AssetDatabase.Contains(atlas))
                    AssetDatabase.AddObjectToAsset(atlas, asset);
        }
        AssetDatabase.SaveAssets();
        Debug.Log("[Shop] 한글 Dynamic TMP Font 생성: " + DynamicFontPath);
        return asset;
    }

    static Sprite Sprite(string name)
    {
        return AssetDatabase.LoadAssetAtPath<Sprite>(Root + "/Sprites/" + name + ".png");
    }

    static void FixCatalogSprites(HealthMonShopScreen shop)
    {
        if (shop.catalog == null) return;
        foreach (var item in shop.catalog.items)
        {
            string spriteName = null;
            switch (item.itemId)
            {
                case "jewelry_necklace": spriteName = "IconNecklace"; break;
                case "jewelry_earring": spriteName = "IconEarring"; break;
                case "jewelry_pendant": spriteName = "IconPendant"; break;
                case "jewelry_ring": spriteName = "IconRing"; break;
                case "pet_starter": spriteName = "IconPetStarter"; break;
                case "pet_mint": spriteName = "IconPetMint"; break;
                case "pet_lavender": spriteName = "IconPetLavender"; break;
            }
            if (spriteName == null) continue;
            var icon = Sprite(spriteName);
            if (icon == null) { Debug.LogWarning("[Shop] 카탈로그 아이콘 누락: " + spriteName); continue; }
            item.icon = icon;
        }
        EditorUtility.SetDirty(shop.catalog);
        AssetDatabase.SaveAssets();
    }

    static void SetSpriteIfMissing(Transform root, string path, string spriteName, bool sliced = true)
    {
        var t = root.Find(path);
        if (t == null) return;
        var img = t.GetComponent<Image>();
        var sprite = Sprite(spriteName);
        if (img == null || sprite == null) return;
        if (img.sprite == null) img.sprite = sprite;
        if (sliced) img.type = Image.Type.Sliced;
        img.color = Color.white;
        EditorUtility.SetDirty(img);
    }

    static void FixSpriteReferences(HealthMonShopScreen shop)
    {
        var root = shop.transform.Find("ShopOverlay");
        if (root == null) return;
        var bg = root.GetComponent<Image>();
        if (bg != null) { bg.sprite = Sprite("ShopBackground"); bg.type = Image.Type.Simple; bg.color = Color.white; }
        SetSpriteIfMissing(root, "ShopHeader", "ShopTopBar");
        SetSpriteIfMissing(root, "ShopBanner", "ShopCardRare");
        SetSpriteIfMissing(root, "AccessoryTab", "ShopTabOn");
        SetSpriteIfMissing(root, "CharacterTab", "ShopTabOff");
        SetSpriteIfMissing(root, "SelectionPanel", "ShopModal");
        SetSpriteIfMissing(root, "ProductList/Viewport/Content/_CardTemplate", "ShopCard");
        SetSpriteIfMissing(root, "PurchaseConfirmModal/ConfirmCard", "ShopModal");
        SetSpriteIfMissing(root, "PurchaseSuccessModal/SuccessCard", "ShopModal");
        SetSpriteIfMissing(root, "SelectionPanel/Purchase", "ShopButtonMint");
        for (int i=0; i<5; i++)
        {
            string[] filters={"전체", "목걸이", "귀걸이", "펜던트", "반지"};
            SetSpriteIfMissing(root, "CategoryFilters/Filter_" + filters[i], "ShopPill", false);
        }
        if (shop.cardTemplate != null)
        {
            var card = shop.cardTemplate;
            if (card.normalBackground == null) card.normalBackground = Sprite("ShopCard");
            if (card.featuredBackground == null) card.featuredBackground = Sprite("ShopCardRare");
            if (card.icon != null) { card.icon.sprite = Sprite("IconPendant"); card.icon.enabled = true; card.icon.preserveAspect = true; }
        }
    }

    static void FixTypography(HealthMonShopScreen shop, TMP_FontAsset font)
    {
        var settings = shop.GetComponent<HealthMonShopFontSettings>();
        if (settings == null) settings = shop.gameObject.AddComponent<HealthMonShopFontSettings>();
        if (settings.bodyFont == null) settings.bodyFont = font;
        if (settings.headingFont == null) settings.headingFont = font;
        settings.ApplyAllShopFonts();
        EditorUtility.SetDirty(settings);
    }

    static void CreateBottomShopButton(Canvas canvas, HealthMonShopScreen shop, TMP_FontAsset font)
    {
        var nav = canvas.transform.Find("BottomNavV2");
        var bottom = nav != null ? nav.Find("BottomRow") : null;
        var top = nav != null ? nav.Find("TopRow") : null;
        if (bottom == null || top == null) throw new Exception("BottomNavV2/BottomRow 또는 TopRow를 찾을 수 없습니다.");
        var oldFloating = canvas.transform.Find("HomePanel/HM_OpenShop_Button");
        if (oldFloating != null) UnityEngine.Object.DestroyImmediate(oldFloating.gameObject);

        var existingShopButton = bottom.Find("ShopButton");
        if (existingShopButton != null) UnityEngine.Object.DestroyImmediate(existingShopButton.gameObject);
        var wearable = bottom.Find("WearableButton");
        if (wearable == null) throw new Exception("기존 BottomRow/WearableButton을 찾지 못했습니다.");
        GameObject go = UnityEngine.Object.Instantiate(wearable.gameObject, bottom);
        go.name = "ShopButton";
        go.SetActive(true);
        go.transform.SetAsLastSibling();
        var button = go.GetComponent<Button>();
        if (button == null) throw new Exception("ShopButton에 Button 컴포넌트가 없습니다.");
        // Very important: cloned Button has existing persistent Wearable event. Replace the event object.
        button.onClick = new Button.ButtonClickedEvent();
        UnityEventTools.AddPersistentListener(button.onClick, shop.OpenShop);

        var label = go.GetComponentInChildren<TMP_Text>(true);
        if (label != null)
        {
            label.text = "상점";
            label.font = font;
            label.enableAutoSizing = true;
            label.fontSizeMax = Mathf.Min(label.fontSize, 31f);
            label.fontSizeMin = 20f;
            label.color = Color.white;
        }
        var oldIcon = go.transform.Find("NavIconV2");
        if (oldIcon != null) UnityEngine.Object.DestroyImmediate(oldIcon.gameObject);
        var iconGO = new GameObject("ShopIcon", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
        iconGO.transform.SetParent(go.transform, false);
        var irt = (RectTransform)iconGO.transform;
        irt.anchorMin = irt.anchorMax = new Vector2(.5f, 1);
        irt.pivot = new Vector2(.5f, 1);
        irt.sizeDelta = new Vector2(53, 53);
        irt.anchoredPosition = new Vector2(0, -9);
        var icon = iconGO.GetComponent<Image>();
        icon.sprite = Sprite("IconShop");
        icon.preserveAspect = true;
        icon.raycastTarget = false;

        var group = bottom.GetComponent<HorizontalLayoutGroup>();
        if (group != null) group.spacing = 8f;
        foreach (var t in bottom.GetComponentsInChildren<TMP_Text>(true))
        {
            t.enableAutoSizing = true;
            t.fontSizeMax = Mathf.Min(t.fontSize, 30f);
            t.fontSizeMin = 20f;
        }
        var navHighlighter = nav.GetComponent<HealthMonSixNavHighlighter>();
        Sprite idle = Sprite("ShopTabOff"), selected = Sprite("ShopButtonGold");
        if (navHighlighter != null)
        {
            var obj = new SerializedObject(navHighlighter);
            var normalProp = obj.FindProperty("normalSprite");
            var selectedProp = obj.FindProperty("selectedSprite");
            if (normalProp != null && normalProp.objectReferenceValue is Sprite s0) idle = s0;
            if (selectedProp != null && selectedProp.objectReferenceValue is Sprite s1) selected = s1;
        }
        var navVisual = go.GetComponent<HealthMonShopNavVisual>();
        if (navVisual == null) navVisual = go.AddComponent<HealthMonShopNavVisual>();
        navVisual.shop = shop;
        navVisual.shopBackground = go.GetComponent<Image>();
        navVisual.shopLabel = label;
        navVisual.idleSprite = idle;
        navVisual.selectedSprite = selected;
        // Keep existing button wiring intact; record their visuals only.
        string[] upper = {"HomeButton", "FoodButton", "DialogueButton"};
        string[] lower = {"QuestButton", "CollectionButton", "WearableButton"};
        navVisual.previousNavBackgrounds = new Image[6];
        navVisual.previousNavLabels = new TMP_Text[6];
        for (int i = 0; i < 6; i++)
        {
            var node = i < 3 ? top.Find(upper[i]) : bottom.Find(lower[i - 3]);
            if (node != null)
            {
                navVisual.previousNavBackgrounds[i] = node.GetComponent<Image>();
                navVisual.previousNavLabels[i] = node.GetComponentInChildren<TMP_Text>(true);
            }
        }
        if (navVisual.shopBackground != null)
        {
            navVisual.shopBackground.sprite = idle;
            navVisual.shopBackground.type = Image.Type.Sliced;
        }
        EditorUtility.SetDirty(go);
    }
}

[CustomEditor(typeof(HealthMonShopFontSettings))]
public sealed class HealthMonShopFontSettingsEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        EditorGUILayout.Space();
        if (GUILayout.Button("상점의 모든 폰트 적용 / Apply All Shop Fonts", GUILayout.Height(32)))
        {
            var settings = (HealthMonShopFontSettings)target;
            settings.ApplyAllShopFonts();
            EditorUtility.SetDirty(settings);
            if (settings.gameObject.scene.IsValid()) EditorSceneManager.MarkSceneDirty(settings.gameObject.scene);
        }
    }
}
#endif
