#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Makes UI sprites from the REAL prefab previews. Uses Unity's asynchronous
/// AssetPreview API, never a screenshot of a whole UI panel. Fallback avatars
/// remain in use only if Unity cannot render a particular model preview.
/// </summary>
[InitializeOnLoad]
public static class HealthMonCharacterPrefabPortraitBaker
{
    private const string Folder = "Assets/HealthMon/MultiCharacter/Portraits";
    private sealed class Job
    {
        public HealthMonCharacterRosterAsset.Entry entry;
        public int attempts;
    }

    private static readonly List<Job> queue = new List<Job>();
    private static HealthMonCharacterRosterAsset catalog;
    private static int generated;
    private static int failed;

    static HealthMonCharacterPrefabPortraitBaker()
    {
        EditorApplication.update -= Step;
    }

    public static void Begin(HealthMonCharacterRosterAsset asset)
    {
        EditorApplication.update -= Step;
        queue.Clear();
        catalog = asset;
        generated = 0;
        failed = 0;
        if (catalog == null || catalog.entries == null) return;
        Directory.CreateDirectory(Folder);
        foreach (var entry in catalog.entries)
        {
            if (entry == null || entry.visualPrefab == null) continue;
            // A shop-baked sprite is already an image of the actual prefab.
            if (entry.portrait != null)
            {
                string oldPath = AssetDatabase.GetAssetPath(entry.portrait);
                if (oldPath.StartsWith("Assets/HealthMon/Shop/Generated/Icons/", StringComparison.Ordinal) ||
                    oldPath.StartsWith(Folder + "/", StringComparison.Ordinal)) continue;
            }
            queue.Add(new Job { entry = entry });
            AssetPreview.GetAssetPreview(entry.visualPrefab);
        }
        if (queue.Count == 0)
        {
            Debug.Log("[RosterPortrait] 이미 실제 프리팹 이미지가 연결되어 있어요.");
            return;
        }
        EditorApplication.update += Step;
        Debug.Log("[RosterPortrait] 실제 프리팹 썸네일 생성 예약: " + queue.Count + "개");
    }

    private static void Step()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            Finish(false);
            return;
        }
        for (int step = 0; step < 4 && queue.Count > 0; step++)
        {
            var job = queue[0];
            queue.RemoveAt(0);
            if (job.entry == null || job.entry.visualPrefab == null) continue;
            var image = AssetPreview.GetAssetPreview(job.entry.visualPrefab);
            if (image == null)
            {
                if (++job.attempts < 180) queue.Add(job);
                else { failed++; Debug.LogWarning("[RosterPortrait] Preview unavailable: " + job.entry.id); }
                continue;
            }
            try
            {
                string path = Folder + "/" + job.entry.id + ".png";
                File.WriteAllBytes(path, RenderPng(image));
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer != null)
                {
                    importer.textureType = TextureImporterType.Sprite;
                    importer.spriteImportMode = SpriteImportMode.Single;
                    importer.alphaIsTransparency = true;
                    importer.mipmapEnabled = false;
                    importer.filterMode = FilterMode.Bilinear;
                    importer.SaveAndReimport();
                }
                var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
                if (sprite != null) { job.entry.portrait = sprite; generated++; }
                else failed++;
            }
            catch (Exception e)
            {
                failed++;
                Debug.LogWarning("[RosterPortrait] " + job.entry.id + " 이미지 저장 실패: " + e.Message);
            }
        }
        if (queue.Count == 0) Finish(true);
    }

    private static byte[] RenderPng(Texture2D source)
    {
        const int size = 256;
        var rt = RenderTexture.GetTemporary(size, size, 0, RenderTextureFormat.ARGB32);
        var prev = RenderTexture.active;
        try
        {
            Graphics.Blit(source, rt);
            RenderTexture.active = rt;
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, size, size), 0, 0, false);
            tex.Apply();
            var bytes = tex.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(tex);
            return bytes;
        }
        finally
        {
            RenderTexture.active = prev;
            RenderTexture.ReleaseTemporary(rt);
        }
    }

    private static void Finish(bool completed)
    {
        EditorApplication.update -= Step;
        queue.Clear();
        if (catalog != null)
        {
            EditorUtility.SetDirty(catalog);
            AssetDatabase.SaveAssets();
        }
        if (completed)
            Debug.Log("[RosterPortrait] 완료. 실제 프리팹 이미지 " + generated + "개 생성 / " +
                      failed + "개 미생성. UI는 카탈로그의 이미지를 자동으로 사용합니다.");
        else Debug.LogWarning("[RosterPortrait] Play 시작으로 이미지 생성을 중지했어요. 메뉴 2로 다시 실행 가능합니다.");
    }
}
#endif
