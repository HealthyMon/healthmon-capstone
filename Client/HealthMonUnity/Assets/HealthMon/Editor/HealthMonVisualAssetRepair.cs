using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class HealthMonVisualAssetRepair
{
    public static void Run()
    {
        // The highlight reaches 95px below the top. A 41px border stretched the
        // lower half of that highlight into a long diagonal across tall panels.
        foreach (string path in Directory.GetFiles("Assets/HealthMon/UIStyleKit/UIStyleKitV3/Sprites/Cards", "*.png"))
        {
            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            importer.spriteBorder = new Vector4(46, 41, 46, 100);
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.SaveAndReimport();
        }
        var catalog = AssetDatabase.LoadAssetAtPath<HealthMonShopCatalog>("Assets/HealthMon/Shop/HealthMonShopCatalog.asset");
        foreach (var item in catalog.items.Where(i => i.category == HealthMonShopCategory.Accessory && i.productPrefab != null))
            Save(item.productPrefab, AssetDatabase.GetAssetPath(item.icon));
        // These four category icons are used by the collection and outfit screens.
        string[] slots = { "목걸이", "귀걸이", "펜던트", "반지" };
        string[] stems = { "necklace", "earring", "pendant", "ring" };
        for (int i = 0; i < slots.Length; i++)
        {
            var item = catalog.items.First(p => p.jewelryName == slots[i] && p.productPrefab != null);
            Save(item.productPrefab, "Assets/HealthMon/Art/UI/JewelryIcons/icon_" + stems[i] + ".png");
        }
        Debug.Log("VISUAL_ASSETS_REPAIRED");
        HealthMonAspectVerification.Run();
    }

    private static void Save(GameObject prefab, string path)
    {
        if (string.IsNullOrEmpty(path)) throw new System.InvalidOperationException("Missing icon for " + prefab.name);
        var texture = HealthMonFrontPortrait.Render(prefab);
        try { File.WriteAllBytes(path, texture.EncodeToPNG()); }
        finally { Object.DestroyImmediate(texture); }
        AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
        var importer = (TextureImporter)AssetImporter.GetAtPath(path);
        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Single;
        importer.alphaIsTransparency = true;
        importer.mipmapEnabled = false;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.SaveAndReimport();
    }
}
