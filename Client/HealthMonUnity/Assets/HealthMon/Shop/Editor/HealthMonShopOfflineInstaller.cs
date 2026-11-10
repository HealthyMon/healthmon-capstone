#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

/// <summary>
/// Adds a real prefab-backed local shop without replacing existing MainARScene.
/// Existing Shop v2/v2.1 can be upgraded in place (no UI reset).
/// </summary>
public static class HealthMonShopOfflineInstaller
{
    const string Root = "Assets/HealthMon/Shop";
    const string CatalogPath = Root + "/HealthMonShopCatalog.asset";
    const string FontPath = Root + "/Fonts/HealthMonShop_KoreanDynamic.asset";

    [MenuItem("Tools/HealthMon/Shop/7. 오프라인 상점 + 실제 프리팹 등록 (씬 백업)")]
    public static void Setup()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        { EditorUtility.DisplayDialog("HealthMon Shop", "Play를 끄고 실행해 주세요.", "확인"); return; }
        try
        {
            var canvas = FindCanvas();
            if (canvas == null) { Debug.LogError("[ShopOffline] UI/Canvas/HomePanel을 찾을 수 없습니다."); return; }
            var shop = canvas.GetComponentInChildren<HealthMonShopScreen>(true);
            if (shop == null)
            {
                // A new installation is optional; support the previous UI package too.
                HealthMonShopInstaller.Install();
                shop = canvas.GetComponentInChildren<HealthMonShopScreen>(true);
                if (shop == null) return;
            }
            Backup();
            EnsureFolder(Root + "/Generated/Icons");
            var catalog = shop.catalog != null ? shop.catalog : AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>(CatalogPath);
            if (catalog == null)
            {
                catalog = ScriptableObject.CreateInstance<HealthMonShopCatalog>();
                AssetDatabase.CreateAsset(catalog, CatalogPath);
            }
            // Preserve the existing catalog and any hand-edited prices before adding prefabs.
            if (AssetDatabase.Contains(catalog))
            {
                string sourcePath = AssetDatabase.GetAssetPath(catalog);
                string dest = Root + "/Backups/Catalog_PreOffline_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".asset";
                AssetDatabase.CopyAsset(sourcePath, dest);
            }
            int count = SyncPrefabs(catalog);
            shop.catalog = catalog;
            var local = shop.GetComponent<HealthMonOfflineShopBackend>();
            if (local == null) local = shop.gameObject.AddComponent<HealthMonOfflineShopBackend>();
            local.catalog = catalog;
            shop.backend = local;
            var existingFont = shop.GetComponent<HealthMonShopFontSettings>();
            if (existingFont == null) existingFont = shop.gameObject.AddComponent<HealthMonShopFontSettings>();
            var dynamicFont = EnsureFont();
            if (dynamicFont != null)
            {
                existingFont.bodyFont = dynamicFont;
                existingFont.headingFont = dynamicFont;
                existingFont.ApplyAllShopFonts();
            }
            else Debug.LogWarning("[ShopOffline] 한글 폰트를 못 찾았습니다. v2.1의 폰트 수정 메뉴에서 지정해 주세요.");

            FixProductSprites(shop);
            EditorUtility.SetDirty(local);
            EditorUtility.SetDirty(shop);
            EditorUtility.SetDirty(catalog);
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            AssetDatabase.SaveAssets();
            Selection.activeObject = shop.gameObject;
            HealthMonShopPrefabIconBaker.Begin(catalog);
            Debug.Log("[ShopOffline] prefab " + count + "종 등록. 썸네일 작업이 에디터에서 진행됩니다.");
            EditorUtility.DisplayDialog("HealthMon 오프라인 상점", "프리팹 " + count + "종을 상품으로 등록했어요.\n" +
                "기존 상점 UI와 하단 버튼은 유지됩니다.\n\n" +
                "Unity 에디터가 상품 사진을 생성할 수 있도록 잠시 둔 뒤, Console에서 완료 메시지를 확인해 주세요.\n" +
                "씬 백업: Assets/HealthMon/Shop/Backups", "확인");
        }
        catch (Exception e) { Debug.LogException(e); EditorUtility.DisplayDialog("HealthMon Shop", e.Message, "확인"); }
    }

    [MenuItem("Tools/HealthMon/Shop/8. 프리팹 상품 사진 다시 생성")]
    public static void RebuildIcons()
    {
        var c = AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>(CatalogPath);
        if (c == null) { Debug.LogError("[ShopOffline] 카탈로그가 없습니다. 메뉴 7을 먼저 실행하세요."); return; }
        HealthMonShopPrefabIconBaker.Begin(c);
    }

    [MenuItem("Tools/HealthMon/Shop/9. 상품 목록 / 가격 열기")]
    public static void SelectCatalog()
    {
        Selection.activeObject = AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>(CatalogPath);
        EditorGUIUtility.PingObject(Selection.activeObject);
    }

    static Canvas FindCanvas()
    {
        foreach (var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (c.transform.Find("HomePanel") != null && c.transform.Find("DialoguePanel") != null) return c;
        return null;
    }

    static void Backup()
    {
        var scene = SceneManager.GetActiveScene();
        if (string.IsNullOrEmpty(scene.path)) throw new Exception("현재 씬을 저장하고 다시 시도하세요.");
        EditorSceneManager.SaveScene(scene);
        EnsureFolder(Root + "/Backups");
        string dest = Root + "/Backups/" + Path.GetFileNameWithoutExtension(scene.path) +
            "_PreOfflineShop_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
        if (!AssetDatabase.CopyAsset(scene.path, dest)) throw new Exception("씬 백업 실패. 변경 없이 중단합니다.");
        Debug.Log("[ShopOffline] Backup: " + dest);
    }

    static void EnsureFolder(string folder)
    {
        var bits = folder.Split('/');
        string parent = bits[0];
        for (int i = 1; i < bits.Length; i++)
        {
            string path = parent + "/" + bits[i];
            if (!AssetDatabase.IsValidFolder(path)) AssetDatabase.CreateFolder(parent, bits[i]);
            parent = path;
        }
    }

    static int SyncPrefabs(HealthMonShopCatalog catalog)
    {
        if (catalog.items == null) catalog.items = new List<HealthMonShopItem>();
        // Old fictional variants don't correspond to actual project prefabs.
        catalog.items.RemoveAll(x => x == null || x.itemId == "pet_mint" || x.itemId == "pet_lavender");
        var known = new Dictionary<string, HealthMonShopItem>();
        foreach (var x in catalog.items)
            if (x != null && !string.IsNullOrEmpty(x.itemId) && !known.ContainsKey(x.itemId)) known[x.itemId] = x;
        int n = 0;
        Scan("Assets/HealthMon/Prefabs", true);
        Scan("Assets/Suriyun/Cute_Slime/Prefab", false);
        void Scan(string folder, bool jewelry)
        {
            if (!AssetDatabase.IsValidFolder(folder)) { Debug.LogWarning("[ShopOffline] 폴더 없음: " + folder); return; }
            var paths = new List<string>();
            foreach (string guid in AssetDatabase.FindAssets("t:Prefab", new[] { folder }))
            {
                string p = AssetDatabase.GUIDToAssetPath(guid);
                string nm = Path.GetFileNameWithoutExtension(p);
                if (jewelry ? nm.StartsWith("Jewelry_", StringComparison.OrdinalIgnoreCase)
                            : nm.StartsWith("Cute_Slime_", StringComparison.OrdinalIgnoreCase)) paths.Add(p);
            }
            paths.Sort(StringComparer.OrdinalIgnoreCase);
            foreach (var path in paths)
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (prefab == null) continue;
                string name = Path.GetFileNameWithoutExtension(path);
                string id = "prefab_" + name.ToLowerInvariant().Replace(' ', '_');
                if (!known.TryGetValue(id, out var item))
                {
                    item = new HealthMonShopItem { itemId = id, includedByDefault = false };
                    catalog.items.Add(item); known[id] = item;
                }
                item.productPrefab = prefab;
                if (jewelry)
                {
                    string type = name.Contains("Chain_") ? "목걸이" :
                        name.Contains("Earring_") ? "귀걸이" :
                        name.Contains("Pendant_") ? "펜던트" : "반지";
                    item.category = HealthMonShopCategory.Accessory;
                    item.jewelryName = type;
                    item.displayName = type + " · " + name.Replace("Jewelry_", "").Replace('_', ' ');
                    item.description = "원본 3D 프리팹: " + name + "\n구매하면 꾸미기에서 " + type + " 슬롯이 해금됩니다.";
                    if (item.displayCoinPrice <= 0) item.displayCoinPrice = type == "목걸이" ? 90 : type == "귀걸이" ? 120 : type == "펜던트" ? 180 : 160;
                    item.featured = name.Contains("Type7") || name.Contains("Type9");
                }
                else
                {
                    item.category = HealthMonShopCategory.Character;
                    item.jewelryName = "";
                    item.displayName = "헬스몬 " + name.Replace("Cute_Slime_", "");
                    item.description = "새로운 3D 슬라임 프리팹: " + name + "\n구매 후 보유/선택할 수 있습니다.";
                    if (item.displayCoinPrice <= 0) item.displayCoinPrice = 300 + (n % 5) * 100;
                    item.featured = name.EndsWith("1") || name.EndsWith("6");
                }
                if (item.icon == null) item.icon = FallbackIcon(jewelry ? item.jewelryName : "헬스몬");
                n++;
            }
        }
        EditorUtility.SetDirty(catalog);
        return n;
    }

    static Sprite FallbackIcon(string type)
    {
        string img = type == "목걸이" ? "IconNecklace" : type == "귀걸이" ? "IconEarring" :
                     type == "펜던트" ? "IconPendant" : type == "반지" ? "IconRing" : "IconPetStarter";
        return AssetDatabase.LoadAssetAtPath<Sprite>(Root + "/Sprites/" + img + ".png");
    }

    static TMP_FontAsset EnsureFont()
    {
        var found = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(FontPath);
        if (found != null) return found;
        var source = AssetDatabase.LoadAssetAtPath<Font>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold.ttf");
        if (source == null) return null;
        EnsureFolder(Root + "/Fonts");
        found = TMP_FontAsset.CreateFontAsset(source, 90, 9, GlyphRenderMode.SDFAA,
            1024, 1024, AtlasPopulationMode.Dynamic, true);
        if (found == null) return null;
        found.name = "HealthMonShop_KoreanDynamic";
        AssetDatabase.CreateAsset(found, FontPath);
        if (found.material != null && !AssetDatabase.Contains(found.material)) AssetDatabase.AddObjectToAsset(found.material, found);
        foreach (var atlas in found.atlasTextures)
            if (atlas != null && !AssetDatabase.Contains(atlas)) AssetDatabase.AddObjectToAsset(atlas, found);
        AssetDatabase.SaveAssets();
        return found;
    }

    static void FixProductSprites(HealthMonShopScreen shop)
    {
        if (shop.cardTemplate != null)
        {
            var card = shop.cardTemplate;
            if (card.normalBackground == null)
                card.normalBackground = AssetDatabase.LoadAssetAtPath<Sprite>(Root + "/Sprites/ShopCard.png");
            if (card.icon != null) { card.icon.enabled = true; card.icon.preserveAspect = true; }
        }
    }
}
#endif
