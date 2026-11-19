// HealthMon UI Style Kit 1.0
// Editor-only import helper. Does NOT modify scenes, GameObjects, or existing project scripts.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

public static class HealthMonUIStyleImporter
{
    private const string Root = "Assets/HealthMon/UIStyleKit/Sprites/";

    // Borders are (left, bottom, right, top) in source pixels.
    private static readonly Dictionary<string, Vector4> SliceBorders =
        new Dictionary<string, Vector4>(StringComparer.OrdinalIgnoreCase)
        {
            {"Panels/Panel_Dark.png", new Vector4(52f,52f,52f,52f)},
            {"Panels/Panel_Soft.png", new Vector4(52f,52f,52f,52f)},
            {"Panels/Panel_Glass.png", new Vector4(52f,52f,52f,52f)},
            {"Panels/Panel_Quest.png", new Vector4(48f,32f,48f,32f)},
            {"Panels/Panel_ItemSlot.png", new Vector4(44f,44f,44f,44f)},
            {"Panels/Panel_ItemSelected.png", new Vector4(44f,44f,44f,44f)},
            {"Bars/Header_Main.png", new Vector4(52f,52f,52f,52f)},
            {"Bars/Header_Secondary.png", new Vector4(52f,52f,52f,52f)},
            {"Bars/BottomNav.png", new Vector4(44f,44f,44f,44f)},
            {"Bars/ProgressTrack.png", new Vector4(26f,18f,26f,18f)},
            {"Bars/ProgressFill_Mint.png", new Vector4(26f,18f,26f,18f)},
            {"Bars/ProgressFill_Gold.png", new Vector4(26f,18f,26f,18f)},
            {"Buttons/Button_Primary.png", new Vector4(60f,38f,60f,38f)},
            {"Buttons/Button_Secondary.png", new Vector4(60f,38f,60f,38f)},
            {"Buttons/Button_Selected.png", new Vector4(60f,38f,60f,38f)},
            {"Buttons/Button_Danger.png", new Vector4(60f,38f,60f,38f)},
            {"Buttons/Button_Disabled.png", new Vector4(60f,38f,60f,38f)},
            {"Buttons/Tab_Active.png", new Vector4(48f,32f,48f,32f)},
            {"Buttons/Tab_Idle.png", new Vector4(48f,32f,48f,32f)},
            {"Buttons/NavItem_Selected.png", new Vector4(48f,32f,48f,32f)},
            {"Buttons/NavItem_Idle.png", new Vector4(48f,32f,48f,32f)},
            {"Buttons/Button_IconRound.png", new Vector4(65f,65f,65f,65f)},
            {"Buttons/Button_IconClose.png", new Vector4(65f,65f,65f,65f)},
            {"Bubbles/SpeechBubble.png", new Vector4(68f,68f,68f,68f)},
            {"Bubbles/ChatBubble_User.png", new Vector4(68f,68f,68f,68f)},
            {"Bubbles/ChatBubble_Pet.png", new Vector4(68f,68f,68f,68f)},
            {"Bubbles/InputField.png", new Vector4(60f,38f,60f,38f)},
            {"Chips/InfoChip_Dark.png", new Vector4(50f,30f,50f,30f)},
            {"Chips/InfoChip_Light.png", new Vector4(50f,30f,50f,30f)},
            {"Chips/Badge_Gold.png", new Vector4(45f,26f,45f,26f)},
            {"Chips/Badge_Mint.png", new Vector4(45f,26f,45f,26f)},
        };

    [MenuItem("Tools/HealthMon/UI Style Kit/Configure Sprite Imports")]
    public static void Configure()
    {
        if (!AssetDatabase.IsValidFolder("Assets/HealthMon/UIStyleKit/Sprites"))
        {
            Debug.LogError("[HealthMon UI Style Kit] 폴더를 찾을 수 없습니다: " + Root);
            return;
        }

        string[] guids = AssetDatabase.FindAssets("t:Texture2D", new[] { "Assets/HealthMon/UIStyleKit/Sprites" });
        int updated = 0;
        foreach (string guid in guids)
        {
            string assetPath = AssetDatabase.GUIDToAssetPath(guid).Replace('\\', '/');
            if (!assetPath.StartsWith(Root, StringComparison.OrdinalIgnoreCase) ||
                !assetPath.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) continue;

            var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if (importer == null) continue;
            string relative = assetPath.Substring(Root.Length);
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = 100f;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.maxTextureSize = 2048;
            importer.spriteBorder = SliceBorders.TryGetValue(relative, out var border) ? border : Vector4.zero;
            importer.SaveAndReimport();
            updated++;
        }
        AssetDatabase.Refresh();
        Debug.Log($"[HealthMon UI Style Kit] PNG Sprite {updated}개 설정 완료. Image Type은 Sliced로 지정하세요.");
        EditorUtility.DisplayDialog("HealthMon UI Style Kit",
            $"Sprite {updated}개를 설정했습니다.\n이제 기존 Image의 Source Image를 교체하고 Image Type을 Sliced로 선택하세요.\n씬/기존 UI는 변경되지 않았습니다.", "확인");
    }
}
#endif
