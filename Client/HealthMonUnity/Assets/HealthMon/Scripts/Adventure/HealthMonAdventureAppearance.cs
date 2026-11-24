using System.Collections.Generic;
using UnityEngine;

/// <summary>Carry only the visible home mesh into the exploration scene.</summary>
public sealed class HealthMonAdventureAppearance : MonoBehaviour
{
    private static HealthMonAdventureAppearance snapshot;
    private readonly List<Mesh> meshes = new List<Mesh>();
    private readonly List<Material> materials = new List<Material>();
    private readonly Dictionary<Texture, Texture> textures = new Dictionary<Texture, Texture>();

    public static void CaptureHome()
    {
        Transform anchor = null;
        foreach (var candidate in FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (candidate.name == "HomePetAnchor") { anchor = candidate; break; }
        if (anchor == null) return;
        var renderers = anchor.GetComponentsInChildren<Renderer>();
        if (renderers.Length == 0) return;
        if (snapshot != null) Destroy(snapshot.gameObject);
        var root = new GameObject("Adventure appearance snapshot");
        snapshot = root.AddComponent<HealthMonAdventureAppearance>();
        DontDestroyOnLoad(root);
        Camera homeCamera = null;
        foreach (var camera in FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (camera.name == "HomeCamera") { homeCamera = camera; break; }
        var rotation = homeCamera != null ? Quaternion.Euler(0, -homeCamera.transform.eulerAngles.y, 0) : Quaternion.identity;
        foreach (var renderer in renderers)
        {
            if (!renderer.enabled) continue;
            Mesh mesh = null;
            if (renderer is SkinnedMeshRenderer skinned)
            {
                mesh = new Mesh(); skinned.BakeMesh(mesh, true); mesh.RecalculateBounds();
            }
            else if (renderer.TryGetComponent<MeshFilter>(out var filter) && filter.sharedMesh != null)
                mesh = Instantiate(filter.sharedMesh);
            if (mesh == null) continue;
            snapshot.meshes.Add(mesh);
            var child = new GameObject(renderer.name, typeof(MeshFilter), typeof(MeshRenderer));
            child.transform.SetParent(root.transform, false);
            child.transform.localPosition = rotation * (renderer.transform.position - anchor.position);
            child.transform.localRotation = rotation * renderer.transform.rotation;
            child.transform.localScale = renderer.transform.lossyScale;
            child.GetComponent<MeshFilter>().sharedMesh = mesh;
            var copies = new Material[renderer.sharedMaterials.Length];
            for (int i = 0; i < copies.Length; i++)
            {
                copies[i] = new Material(renderer.sharedMaterials[i]);
                // The GLTF importer disposes its textures when the home scene
                // closes. A material copy alone still points at those textures.
                foreach (var property in copies[i].GetTexturePropertyNames())
                {
                    var sourceTexture = copies[i].GetTexture(property);
                    if (sourceTexture == null) continue;
                    if (!snapshot.textures.TryGetValue(sourceTexture, out var texture))
                    {
                        texture = CopyTexture(sourceTexture);
                        snapshot.textures.Add(sourceTexture, texture);
                    }
                    copies[i].SetTexture(property, texture);
                }
                snapshot.materials.Add(copies[i]);
            }
            child.GetComponent<MeshRenderer>().sharedMaterials = copies;
        }
        root.SetActive(false);
    }

    private static Texture CopyTexture(Texture source)
    {
        if (source is Texture2D image)
        {
            // glTF textures discard their CPU pixels after upload. Allocate an
            // identical GPU texture and copy it without reading CPU pixels.
            var copy = new Texture2D(image.width, image.height, image.format,
                image.mipmapCount, !image.isDataSRGB) { name = image.name + " adventure" };
            copy.filterMode = image.filterMode;
            copy.wrapModeU = image.wrapModeU; copy.wrapModeV = image.wrapModeV;
            copy.anisoLevel = image.anisoLevel;
            copy.Apply(false, true);
            Graphics.CopyTexture(image, copy);
            return copy;
        }
        return Instantiate(source);
    }

    public static bool Apply(Transform target)
    {
        if (snapshot == null || snapshot.meshes.Count == 0 || target == null) return false;
        if (target.Find("HomeAppearance") != null) return true;
        var grid = FindAnyObjectByType<EliteGridManager>();
        float footprint = grid != null ? Vector3.Distance(grid.CellToWorldPosition(new Vector2Int(0, 1)),
            grid.CellToWorldPosition(new Vector2Int(1, 1))) * .9f : 1.35f;
        foreach (var renderer in target.GetComponentsInChildren<Renderer>(true)) renderer.enabled = false;
        var root = new GameObject("HomeAppearance").transform;
        root.SetParent(target, false);
        foreach (Transform source in snapshot.transform)
        {
            var copy = Instantiate(source.gameObject, root);
            copy.SetActive(true);
        }
        var visible = root.GetComponentsInChildren<Renderer>();
        if (visible.Length == 0) return false;
        var bounds = visible[0].bounds;
        foreach (var renderer in visible) bounds.Encapsulate(renderer.bounds);
        // Match a grid cell's footprint and ground the visual at the old capsule's feet.
        float scale = footprint / Mathf.Max(bounds.size.x, bounds.size.z);
        var localFeet = root.InverseTransformPoint(new Vector3(bounds.center.x, bounds.min.y, bounds.center.z));
        root.localScale *= scale;
        var feet = target.position - Vector3.up;
        root.position += feet - root.TransformPoint(localFeet);
        return true;
    }

    private void OnDestroy()
    {
        foreach (var mesh in meshes) if (mesh != null) Destroy(mesh);
        foreach (var material in materials) if (material != null) Destroy(material);
        foreach (var texture in textures.Values) if (texture != null) Destroy(texture);
    }
}
