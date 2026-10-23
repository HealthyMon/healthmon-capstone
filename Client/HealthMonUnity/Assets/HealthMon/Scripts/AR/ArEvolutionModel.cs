using System;
using System.Threading.Tasks;
using GLTFast;
using UnityEngine;

namespace Healthmon.Evolution
{
    public sealed class ArEvolutionModel : MonoBehaviour
    {
        public string DisplayedRevision { get; private set; }
        public string LastError { get; private set; }
        private GameObject displayed;
        private GltfImport displayedImport;
        private Renderer[] placeholderRenderers;
        private bool loading;
        private ModelManifest desired;

        public static ArEvolutionModel Attach(GameObject arCharacter)
        {
            var view = arCharacter.GetComponent<ArEvolutionModel>();
            return view != null ? view : arCharacter.AddComponent<ArEvolutionModel>();
        }

        private void Start()
        {
            var accessories = GetComponent<HealthMonAccessoryView>();
            placeholderRenderers = System.Array.FindAll(GetComponentsInChildren<Renderer>(true),
                renderer => accessories == null || !accessories.ContainsAccessory(renderer.transform));
            if (EvolutionClient.Instance != null)
            {
                EvolutionClient.Instance.ModelChanged += Changed;
                if (EvolutionClient.Instance.Current != null) Changed(EvolutionClient.Instance.Current);
            }
        }

        public void Changed(ModelManifest manifest)
        {
            desired = manifest;
            if (manifest == null)
            {
                if (displayed != null) Destroy(displayed);
                displayed = null; displayedImport?.Dispose(); displayedImport = null; DisplayedRevision = null;
                if (placeholderRenderers != null) foreach (var renderer in placeholderRenderers) renderer.enabled = true;
                return;
            }
            if (!loading && manifest.revision != DisplayedRevision) _ = ApplyDesired();
        }

        private async Task ApplyDesired()
        {
            loading = true;
            while (this != null && desired != null && desired.revision != DisplayedRevision)
            {
                var manifest = desired;
                var importer = new GltfImport();
                GameObject candidate = null;
                try
                {
                    byte[] bytes = await EvolutionClient.Instance.DownloadModel(manifest);
                    if (this == null) { importer.Dispose(); return; }
                    candidate = new GameObject((manifest.species ?? "HealthMon") + " " + manifest.revision);
                    candidate.transform.SetParent(transform, false);
                    candidate.SetActive(false);
                    if (!await importer.Load(bytes, new Uri(EvolutionClient.Instance.ResolveUrl(manifest.model_url))) ||
                        !await importer.InstantiateMainSceneAsync(candidate.transform))
                        throw new InvalidOperationException("GLB import/instantiation failed.");
                    if (this == null) { Destroy(candidate); importer.Dispose(); return; }
                    if (desired == null || desired.revision != manifest.revision) { Destroy(candidate); importer.Dispose(); continue; }
                    FitOnPlane(candidate, EvolutionClient.Instance.Settings.display_height_m);
                    var skinned = candidate.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                    if (skinned.Length == 0) throw new InvalidOperationException("Imported model has no skin.");
                    foreach (var renderer in skinned)
                        if (renderer.bones == null || renderer.bones.Length == 0) throw new InvalidOperationException("Imported skin has no bones.");
                    // The existing AR object/pose/collider survives. Only its visual child changes.
                    if (displayed != null) { displayed.SetActive(false); Destroy(displayed); }
                    displayedImport?.Dispose();
                    displayed = candidate;
                    displayedImport = importer;
                    foreach (var renderer in placeholderRenderers) renderer.enabled = false;
                    GetComponent<HealthMonTouchReaction>()?.UseVisual(candidate.transform);
                    GetComponent<HealthMonMovement>()?.UseAnimator(candidate.GetComponentInChildren<Animator>());
                    candidate.SetActive(true);
                    DisplayedRevision = manifest.revision;
                    LastError = null;
                    Debug.Log("[HealthMon Evolution] AR model ready: stage " + manifest.stage + " revision " + manifest.revision);
                }
                catch (Exception error)
                {
                    if (candidate != null) Destroy(candidate);
                    importer.Dispose();
                    LastError = error.Message;
                    Debug.LogWarning("[HealthMon Evolution] Keeping previous AR model: " + error.Message);
                    break;
                }
            }
            loading = false;
        }

        private void FitOnPlane(GameObject model, float heightMetres)
        {
            model.transform.localRotation = Quaternion.Euler(0, EvolutionClient.Instance.Settings.model_yaw_degrees, 0);
            var renderers = model.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0) throw new InvalidOperationException("Model has no renderers.");
            bool initialized = false;
            Bounds bounds = new Bounds();
            foreach (var renderer in renderers)
            {
                Mesh baked = null;
                var skin = renderer as SkinnedMeshRenderer;
                Bounds local;
                if (skin != null)
                {
                    // Imported skin culling bounds can be loose; fit the actual rest geometry.
                    baked = new Mesh();
                    skin.BakeMesh(baked);
                    local = baked.bounds;
                    skin.localBounds = local;
                }
                else local = renderer.GetComponent<MeshFilter>().sharedMesh.bounds;
                for (int x = -1; x <= 1; x += 2)
                    for (int y = -1; y <= 1; y += 2)
                        for (int z = -1; z <= 1; z += 2)
                        {
                            var point = renderer.transform.TransformPoint(local.center + Vector3.Scale(local.extents, new Vector3(x, y, z)));
                            if (!initialized) { bounds = new Bounds(point, Vector3.zero); initialized = true; }
                            else bounds.Encapsulate(point);
                        }
                if (baked != null) Destroy(baked);
            }
            if (bounds.size.y < 0.0001f) throw new InvalidOperationException("Model bounds are empty.");
            float scale = Mathf.Clamp(heightMetres, 0.05f, 2f) / bounds.size.y;
            Vector3 localFeet = transform.InverseTransformPoint(new Vector3(bounds.center.x, bounds.min.y, bounds.center.z));
            model.transform.localScale = Vector3.one * scale;
            model.transform.localPosition = -localFeet * scale;
        }

        private void OnDestroy()
        {
            if (EvolutionClient.Instance != null) EvolutionClient.Instance.ModelChanged -= Changed;
            displayedImport?.Dispose();
        }
    }
}
