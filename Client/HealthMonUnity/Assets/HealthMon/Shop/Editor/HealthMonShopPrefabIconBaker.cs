#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Bakes the real Unity prefab's AssetPreview into an importable PNG for UI.
/// AssetPreview loads asynchronously, so the queue runs across editor update frames.
/// No external renderer, server, or paid asset required.
/// </summary>
[InitializeOnLoad]
public static class HealthMonShopPrefabIconBaker
{
    const string IconFolder = "Assets/HealthMon/Shop/Generated/Icons";
    private sealed class Job
    {
        public HealthMonShopItem item;
        public int attempts;
    }
    private static readonly List<Job> jobs = new List<Job>();
    private static HealthMonShopCatalog catalog;
    private static int made, missed;
    private static bool running;

    static HealthMonShopPrefabIconBaker() { EditorApplication.update -= OnUpdate; }

    public static void Begin(HealthMonShopCatalog c)
    {
        EditorApplication.update -= OnUpdate;
        jobs.Clear();
        catalog = c;
        made = 0; missed = 0;
        if (catalog == null) return;
        Directory.CreateDirectory(IconFolder);
        foreach (var item in catalog.items)
        {
            if (item == null || item.productPrefab == null) continue;
            jobs.Add(new Job { item = item });
            // Schedule an async preview request for every model.
            AssetPreview.GetAssetPreview(item.productPrefab);
        }
        if (jobs.Count == 0) { Debug.LogWarning("[ShopIcons] 프리팹 상품 없음"); return; }
        running = true;
        EditorApplication.update += OnUpdate;
        Debug.Log("[ShopIcons] 프리팹 사진 생성 시작: " + jobs.Count + "개. Play 모드는 잠시 실행하지 마세요.");
    }

    private static void OnUpdate()
    {
        if (!running) return;
        if (EditorApplication.isPlayingOrWillChangePlaymode) { Stop(); return; }
        // Process a handful each editor frame, to avoid freezing the UI.
        for (int step = 0; step < 6 && jobs.Count > 0; step++)
        {
            var job = jobs[0];
            jobs.RemoveAt(0);
            if (job.item == null || job.item.productPrefab == null) continue;
            Texture2D preview = AssetPreview.GetAssetPreview(job.item.productPrefab);
            if (preview == null)
            {
                job.attempts++;
                if (job.attempts < 150)
                {
                    jobs.Add(job);
                    continue;
                }
                // Some prefabs have no preview on certain URP/editor versions.
                // Never overwrite the colorful fallback icon with a generic cube.
                missed++;
                Debug.LogWarning("[ShopIcons] 프리팹 사진 생성 실패: " + job.item.productPrefab.name +
                    " (에디터에서 메뉴 8을 다시 실행하거나 Catalog의 Icon을 직접 설정하세요)");
                continue;
            }
            try
            {
                string safe = job.item.itemId.Replace('/', '_').Replace(' ', '_').Replace(':','_');
                string path = IconFolder + "/" + safe + ".png";
                byte[] png = ToPng(preview, 256);
                File.WriteAllBytes(path, png);
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
                Sprite icon = AssetDatabase.LoadAssetAtPath<Sprite>(path);
                if (icon != null) { job.item.icon = icon; made++; }
                else missed++;
            }
            catch (Exception e)
            {
                missed++;
                Debug.LogWarning("[ShopIcons] " + job.item.itemId + " 아이콘 저장 오류: " + e.Message);
            }
        }
        if (jobs.Count == 0)
        {
            EditorUtility.SetDirty(catalog);
            AssetDatabase.SaveAssets();
            Stop();
            Debug.Log("[ShopIcons] 완료: " + made + "개 생성, " + missed + "개 기본 아이콘 유지. " +
                "Play 중 상점을 다시 열면 상품 사진이 보입니다.");
        }
    }

    private static byte[] ToPng(Texture source, int size)
    {
        RenderTexture rt = RenderTexture.GetTemporary(size, size, 0, RenderTextureFormat.ARGB32);
        RenderTexture before = RenderTexture.active;
        try
        {
            Graphics.Blit(source, rt);
            RenderTexture.active = rt;
            Texture2D tex = new Texture2D(size, size, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0,0,size,size), 0,0, false);
            tex.Apply();
            var png = tex.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(tex);
            return png;
        }
        finally { RenderTexture.active = before; RenderTexture.ReleaseTemporary(rt); }
    }

    private static void Stop()
    {
        EditorApplication.update -= OnUpdate;
        jobs.Clear(); running = false;
    }
}
#endif
