using System;
using System.IO;
using System.Collections.Generic;
using System.Security.Cryptography;
using GLTFast.Export;
using UnityEditor;
using UnityEngine;

// Export the actual game starter so server evolution and the Unity home share
// the same parent. No generated or historical animal is used as a substitute.
public static class HealthMonStarterExport
{
    public static async void VerifyRoundTrip()
    {
        GameObject imported = null;
        Texture2D portrait = null;
        GLTFast.GltfImport importer = null;
        int code = 1;
        try
        {
            importer = new GLTFast.GltfImport(deferAgent: new GLTFast.UninterruptedDeferAgent());
            string repo = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
            string file = Path.Combine(repo, "Server/assets/starter/slime/model.glb");
            string output = Environment.GetEnvironmentVariable("HEALTHMON_STARTER_REVIEW_OUTPUT");
            if (string.IsNullOrEmpty(output)) throw new InvalidOperationException("Review output path required");
            Directory.CreateDirectory(output);
            imported = new GameObject("Cute_Slime_Imported");
            if (!await importer.Load(File.ReadAllBytes(file), new Uri(file)) ||
                !await importer.InstantiateMainSceneAsync(imported.transform))
                throw new InvalidOperationException("Starter GLB round-trip import failed");
            portrait = HealthMonFrontPortrait.Render(imported);
            File.WriteAllBytes(Path.Combine(output, "starter-glb-front.png"), portrait.EncodeToPNG());
            File.WriteAllText(Path.Combine(output, "starter-glb-sha256.txt"), Hash(file));
            Debug.Log("STARTER_ROUNDTRIP_PASS " + output);
            code = 0;
        }
        catch (Exception error) { Debug.LogException(error); }
        finally
        {
            if (imported != null) UnityEngine.Object.DestroyImmediate(imported);
            if (portrait != null) UnityEngine.Object.DestroyImmediate(portrait);
            importer?.Dispose();
        }
        EditorApplication.Exit(code);
    }

    public static async void Run()
    {
        GameObject instance = null;
        Texture2D portrait = null;
        var meshes = new List<Mesh>();
        var materials = new List<Material>();
        try
        {
            string repo = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
            string output = Path.Combine(repo, "Server/assets/starter/slime");
            Directory.CreateDirectory(output);
            var roster = AssetDatabase.LoadMainAssetAtPath(
                "Assets/HealthMon/MultiCharacter/HealthMonCharacterRoster.asset");
            var entries = new SerializedObject(roster).FindProperty("entries");
            GameObject prefab = null;
            for (int i = 0; i < entries.arraySize; i++)
            {
                var item = entries.GetArrayElementAtIndex(i);
                if (item.FindPropertyRelative("id").stringValue == "pet_starter")
                    prefab = (GameObject)item.FindPropertyRelative("visualPrefab").objectReferenceValue;
            }
            if (prefab == null) throw new InvalidOperationException("Game starter prefab is missing");
            instance = UnityEngine.Object.Instantiate(prefab);
            instance.name = "HealthMonStarterSlime";
            instance.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            foreach (var child in instance.GetComponentsInChildren<Transform>(true))
                if (child.name.StartsWith("Jewelry_", StringComparison.OrdinalIgnoreCase) ||
                    child.name.IndexOf("AccessoryAnchor", StringComparison.OrdinalIgnoreCase) >= 0)
                    child.gameObject.SetActive(false);
            foreach (var animator in instance.GetComponentsInChildren<Animator>(true)) animator.enabled = false;
            foreach (var skin in instance.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                // glTF requires four components per JOINTS/WEIGHTS accessor.
                // The optimized imported FBX stores only two; expand a copy,
                // preserving the asset and its exact bone influence values.
                var copy = UnityEngine.Object.Instantiate(skin.sharedMesh);
                copy.boneWeights = skin.sharedMesh.boneWeights;
                meshes.Add(copy); skin.sharedMesh = copy;
                int dimension = copy.GetVertexAttributeDimension(UnityEngine.Rendering.VertexAttribute.BlendWeight);
                if (dimension != 4) throw new InvalidOperationException("Export requires four bone weight components: " + dimension);
            }
            // The portrait helper uses +Z for slime prefabs, including this game wrapper.
            instance.name = "Cute_Slime_Starter";
            portrait = HealthMonFrontPortrait.Render(instance);
            var pixels = portrait.GetPixels();
            for (int i = 0; i < pixels.Length; i++) pixels[i] = Color.Lerp(Color.white, pixels[i], pixels[i].a);
            portrait.SetPixels(pixels); portrait.Apply();
            File.WriteAllBytes(Path.Combine(output, "image.png"), portrait.EncodeToPNG());
            // Unity Toon has unused URP properties, so the generic exporter selects
            // its empty _BaseMap instead of the actual _MainTex. Normalize only
            // the export clone; never rewrite the game's original materials.
            foreach (var renderer in instance.GetComponentsInChildren<Renderer>())
            {
                var converted = renderer.sharedMaterials;
                for (int i = 0; i < converted.Length; i++)
                {
                    var source = converted[i];
                    if (source == null) continue;
                    var material = new Material(Shader.Find("Standard")) { name = source.name };
                    string textureKey = source.HasProperty("_MainTex") && source.GetTexture("_MainTex") != null
                        ? "_MainTex" : "_BaseMap";
                    if (source.HasProperty(textureKey))
                    {
                        material.SetTexture("_MainTex", source.GetTexture(textureKey));
                        material.SetTextureScale("_MainTex", source.GetTextureScale(textureKey));
                        material.SetTextureOffset("_MainTex", source.GetTextureOffset(textureKey));
                    }
                    material.color = source.HasProperty("_Color") ? source.GetColor("_Color") : Color.white;
                    material.SetFloat("_Metallic", 0); material.SetFloat("_Glossiness", .15f);
                    string renderType = source.GetTag("RenderType", false);
                    bool transparent = renderType == "Transparent" || source.renderQueue >= 3000;
                    bool cutout = renderType == "TransparentCutout" || source.IsKeywordEnabled("_ALPHATEST_ON");
                    material.SetFloat("_Mode", transparent ? 2 : cutout ? 1 : 0);
                    if (transparent) { material.EnableKeyword("_ALPHABLEND_ON"); material.SetOverrideTag("RenderType", "Transparent"); }
                    if (cutout) { material.EnableKeyword("_ALPHATEST_ON"); material.SetOverrideTag("RenderType", "TransparentCutout"); }
                    Debug.Log("STARTER_MATERIAL " + renderer.name + " " + source.name + " shader=" + source.shader.name +
                        " texture=" + material.mainTexture?.name + " mode=" + material.GetFloat("_Mode"));
                    materials.Add(material); converted[i] = material;
                }
                renderer.sharedMaterials = converted;
            }
            var export = new GameObjectExport(new ExportSettings {
                Format = GltfFormat.Binary, ImageDestination = ImageDestination.MainBuffer,
                FileConflictResolution = FileConflictResolution.Overwrite, Deterministic = true
            });
            if (!export.AddScene(new[] { instance }, "HealthMon starter slime") ||
                !await export.SaveToFileAndDispose(Path.Combine(output, "model.glb")))
                throw new InvalidOperationException("Actual slime prefab export failed");
            string contract = File.ReadAllText(Path.Combine(repo, "Ai/Generation3D/configs/species/slime.json"));
            string modelHash = Hash(Path.Combine(output, "model.glb"));
            string imageHash = Hash(Path.Combine(output, "image.png"));
            File.WriteAllText(Path.Combine(output, "manifest.json"),
                "{\n  \"stage\": 0,\n  \"species\": \"slime\",\n  \"revision\": \"slime-starter-v1\",\n" +
                "  \"source_kind\": \"verified_existing_stage0_game_asset\",\n  \"new_generation\": false,\n" +
                "  \"source_prefab\": \"" + AssetDatabase.GetAssetPath(prefab) + "\",\n" +
                "  \"model_sha256\": \"" + modelHash + "\",\n  \"image_sha256\": \"" + imageHash + "\",\n" +
                "  \"species_contract\": " + contract.Trim() + "\n}\n");
            Debug.Log("STARTER_SLIME_EXPORT_PASS " + output);
            EditorApplication.Exit(0);
        }
        catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(1); }
        finally
        {
            if (instance != null) UnityEngine.Object.DestroyImmediate(instance);
            if (portrait != null) UnityEngine.Object.DestroyImmediate(portrait);
            foreach (var mesh in meshes) UnityEngine.Object.DestroyImmediate(mesh);
            foreach (var material in materials) UnityEngine.Object.DestroyImmediate(material);
        }
    }

    private static string Hash(string path)
    {
        using (var sha = SHA256.Create())
        using (var file = File.OpenRead(path))
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
    }
}
