using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Keeps the selected OFFLINE character's appearance consistent in AR Dialogue,
/// PetPreviewRoot (Customization), and EvolutionPetPreviewRig.
/// HomeWorld is already driven by HealthMonCharacterRosterController.
/// Never replaces ARPlacementManager's spawned root, preview cameras, RenderTextures,
/// colliders, or gameplay scripts. Only hides the original body renderers and adds a
/// presentation-only child of the selected Cute_Slime prefab.
/// </summary>
[DisallowMultipleComponent]
[DefaultExecutionOrder(1200)]
public sealed class HealthMonCharacterAllTabsSync : MonoBehaviour
{
    [Header("Existing roster (required)")]
    public HealthMonCharacterRosterController roster;

    [Header("Existing scene references (optional when screen is not installed)")]
    public ARPlacementManager arPlacement;
    public Transform customizationPetRoot;
    public Transform evolutionPetRoot;
    public Transform originalHomePet;

    [Header("Performance")]
    [Range(0.1f, 1f)] public float refreshSeconds = 0.20f;
    public bool verboseLogs = false;

    private sealed class RendererSnapshot
    {
        public Renderer component;
        public bool enabled;
    }
    private sealed class VisualSite
    {
        public Transform source;
        public string appliedId;
        public GameObject replacement;
        public readonly List<RendererSnapshot> original = new List<RendererSnapshot>();
    }

    private readonly VisualSite ar = new VisualSite();
    private readonly VisualSite customization = new VisualSite();
    private readonly VisualSite evolution = new VisualSite();
    private float nextRefresh;
    private string previousId;

    private void Start()
    {
        if (roster == null)
            roster = FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        if (arPlacement == null)
            arPlacement = FindFirstObjectByType<ARPlacementManager>(FindObjectsInactive.Include);
        RefreshNow();
    }

    private void LateUpdate()
    {
        if (Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + Mathf.Max(0.1f, refreshSeconds);
        RefreshNow();
    }

    /// <summary>Can also be called by a UI button or other script after switching characters.</summary>
    public void RefreshNow()
    {
        if (roster == null || roster.catalog == null || roster.catalog.entries == null ||
            string.IsNullOrEmpty(roster.CurrentCharacterId)) return;

        // The current roster intentionally supports LOCAL progression. Do not overwrite
        // a model supplied by the server or an AI evolution process in online mode.
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority)
        {
            ClearSite(ar);
            ClearSite(customization);
            ClearSite(evolution);
            return;
        }

        HealthMonCharacterRosterAsset.Entry entry = null;
        int chosenIndex = -1;
        for (int i = 0; i < roster.catalog.entries.Count; i++)
        {
            var candidate = roster.catalog.entries[i];
            if (candidate != null && candidate.id == roster.CurrentCharacterId)
            {
                entry = candidate;
                chosenIndex = i;
                break;
            }
        }
        if (entry == null) return;
        bool isStarter = chosenIndex == 0;
        if (!isStarter && entry.visualPrefab == null)
        {
            if (entry.id != previousId)
                Debug.LogWarning("[HealthMon All Tabs] Selected character has no visualPrefab: " + entry.id, this);
            return;
        }
        if (entry.id != previousId)
        {
            previousId = entry.id;
            if (verboseLogs) Debug.Log("[HealthMon All Tabs] selected " + entry.title, this);
        }

        // ARPlacementManager may spawn a NEW root when a user first opens Dialogue/AR.
        // Tracking the spawned reference means newly-created AR pets also update.
        Transform arRoot = arPlacement != null && arPlacement.SpawnedHealthMon != null
            ? arPlacement.SpawnedHealthMon.transform : null;
        if (arRoot != null && !arRoot.gameObject.activeInHierarchy) arRoot = null;

        if (customizationPetRoot == null)
            customizationPetRoot = FindPreviewRoot();
        if (evolutionPetRoot == null)
        {
            var rig = FindSceneTransform("EvolutionPetPreviewRig");
            if (rig != null) evolutionPetRoot = rig.Find("PetVisualCopy_AnimationOnly");
        }
        if (originalHomePet == null && roster.originalHomePet != null)
            originalHomePet = roster.originalHomePet.transform;

        SyncSite(ar, arRoot, entry, isStarter);
        SyncSite(customization, customizationPetRoot, entry, isStarter);
        SyncSite(evolution, evolutionPetRoot, entry, isStarter);
        // The existing HomeWorld model swap is preserved. Its original rig may also
        // contain accessory meshes which an older roster version disabled en masse.
        RestoreEquippedHomeAccessories(!isStarter);
    }

    private void SyncSite(VisualSite site, Transform root, HealthMonCharacterRosterAsset.Entry character, bool starter)
    {
        if (root != site.source)
        {
            ClearSite(site);
            site.source = root;
            if (root != null)
            {
                foreach (Renderer r in root.GetComponentsInChildren<Renderer>(true))
                {
                    if (r == null || IsAccessoryOrGenerated(r.transform, root)) continue;
                    site.original.Add(new RendererSnapshot { component = r, enabled = r.enabled });
                }
            }
        }
        if (root == null) return;

        if (starter)
        {
            if (site.replacement != null || site.appliedId != character.id)
                RestoreSite(site);
            site.appliedId = character.id;
            return;
        }

        if (site.appliedId == character.id && site.replacement != null) return;
        RestoreSite(site);

        if (site.original.Count == 0)
        {
            Debug.LogWarning("[HealthMon All Tabs] No original body renderer under " + root.name, this);
            site.appliedId = character.id;
            return;
        }

        Bounds originalBounds;
        bool hasOriginal = TryBounds(site.original, out originalBounds);
        GameObject clone = null;
        try
        {
            // Clone UNDER the original root, so AR placement visibility, world position,
            // render layers, and existing pet touch/interaction scripts remain intact.
            clone = Instantiate(character.visualPrefab, root, false);
            clone.name = "HM_AllTabsVisual_" + character.id;
            clone.transform.localPosition = Vector3.zero;
            clone.transform.localRotation = Quaternion.identity;
            clone.transform.localScale = Vector3.one;
            clone.SetActive(true);

            int layer = RootRenderLayer(site, root.gameObject.layer);
            PrepareVisualOnly(clone.transform, layer);

            Bounds newBounds;
            if (!TryBounds(clone.GetComponentsInChildren<Renderer>(true), out newBounds))
                throw new InvalidOperationException("Prefab has no visible mesh renderers");

            if (hasOriginal)
            {
                // Uniformly fit models of different sizes into the existing camera framing.
                float sizeFactor = Mathf.Clamp(
                    originalBounds.size.y / Mathf.Max(0.001f, newBounds.size.y), 0.35f, 3.0f);
                clone.transform.localScale *= sizeFactor;
                if (TryBounds(clone.GetComponentsInChildren<Renderer>(true), out newBounds))
                    clone.transform.position += originalBounds.center - newBounds.center;
            }

            site.replacement = clone;
            for (int i = 0; i < site.original.Count; i++)
                if (site.original[i].component != null)
                    site.original[i].component.enabled = false;
            site.appliedId = character.id;
        }
        catch (Exception ex)
        {
            if (clone != null) Destroy(clone);
            RestoreSite(site);
            site.appliedId = character.id; // avoid repeatedly spawning a bad prefab
            Debug.LogWarning("[HealthMon All Tabs] " + root.name + " visual swap skipped: " + ex.Message, this);
        }
    }

    private static int RootRenderLayer(VisualSite site, int fallback)
    {
        foreach (var snapshot in site.original)
            if (snapshot.component != null) return snapshot.component.gameObject.layer;
        return fallback;
    }

    private static bool IsAccessoryOrGenerated(Transform mesh, Transform root)
    {
        for (Transform t = mesh; t != null && t != root; t = t.parent)
        {
            string n = t.name;
            if (n.StartsWith("HM_AllTabsVisual_", StringComparison.Ordinal) ||
                n.StartsWith("Jewelry_", StringComparison.OrdinalIgnoreCase) ||
                n.IndexOf("AccessoryAnchor", StringComparison.OrdinalIgnoreCase) >= 0)
                return true;
        }
        return false;
    }

    private static void PrepareVisualOnly(Transform root, int layer)
    {
        foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
        {
            t.gameObject.layer = layer;
            t.gameObject.tag = "Untagged";
        }
        foreach (var script in root.GetComponentsInChildren<MonoBehaviour>(true))
            if (script != null) script.enabled = false;
        foreach (var collider in root.GetComponentsInChildren<Collider>(true))
            collider.enabled = false;
        foreach (var rb in root.GetComponentsInChildren<Rigidbody>(true))
        {
            rb.isKinematic = true;
            rb.useGravity = false;
        }
        foreach (var audio in root.GetComponentsInChildren<AudioSource>(true))
            audio.enabled = false;
        foreach (var animator in root.GetComponentsInChildren<Animator>(true))
        {
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
        }
        foreach (var skinned in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            skinned.updateWhenOffscreen = true;
    }

    private static bool TryBounds(IEnumerable<RendererSnapshot> snaps, out Bounds bounds)
    {
        bounds = new Bounds();
        bool found = false;
        foreach (var s in snaps)
        {
            Renderer renderer = s.component;
            if (renderer == null || !(renderer is MeshRenderer || renderer is SkinnedMeshRenderer)) continue;
            if (!found) { bounds = renderer.bounds; found = true; }
            else bounds.Encapsulate(renderer.bounds);
        }
        return found;
    }

    private static bool TryBounds(Renderer[] renderers, out Bounds bounds)
    {
        bounds = new Bounds();
        bool found = false;
        foreach (var r in renderers)
        {
            if (r == null || !(r is MeshRenderer || r is SkinnedMeshRenderer)) continue;
            if (!found) { bounds = r.bounds; found = true; }
            else bounds.Encapsulate(r.bounds);
        }
        return found;
    }

    private void RestoreSite(VisualSite site)
    {
        if (site.replacement != null)
        {
            Destroy(site.replacement);
            site.replacement = null;
        }
        foreach (var snapshot in site.original)
            if (snapshot.component != null)
                snapshot.component.enabled = snapshot.enabled;
        site.appliedId = null;
    }

    private void ClearSite(VisualSite site)
    {
        RestoreSite(site);
        site.original.Clear();
        site.source = null;
    }

    private void RestoreEquippedHomeAccessories(bool otherCharacterActive)
    {
        if (!otherCharacterActive || originalHomePet == null) return;
        foreach (var renderer in originalHomePet.GetComponentsInChildren<Renderer>(true))
        {
            if (renderer == null || !IsAccessoryOrGenerated(renderer.transform, originalHomePet)) continue;
            // The accessories are managed by the existing customization system.
            // Only enable renderers belonging to currently active jewelry objects.
            if (renderer.gameObject.activeInHierarchy) renderer.enabled = true;
        }
    }

    private void OnDisable()
    {
        ClearSite(ar);
        ClearSite(customization);
        ClearSite(evolution);
    }

    private static Transform FindSceneTransform(string name)
    {
        foreach (var t in FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (t.name == name && t.gameObject.scene.IsValid()) return t;
        return null;
    }

    private static Transform FindPreviewRoot()
    {
        var preview = FindSceneTransform("PetPreviewRoot");
        if (preview == null) return null;
        var jewelry = preview.GetComponentInChildren<HealthMon3DJewelryRig>(true);
        if (jewelry != null) return jewelry.transform;
        for (int i = 0; i < preview.childCount; i++)
        {
            var child = preview.GetChild(i);
            if (child.GetComponentsInChildren<Renderer>(true).Length > 0) return child;
        }
        return null;
    }
}
