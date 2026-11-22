using UnityEngine;

/// <summary>Keep the real character inside its square render texture after swaps.</summary>
public sealed class HealthMonPreviewFraming : MonoBehaviour
{
    public Transform target;
    private Camera preview;
    private int signature;
    private float nextCheck;

    private void Awake() { preview = GetComponent<Camera>(); }
    private void LateUpdate()
    {
        if (target == null || preview == null || Time.unscaledTime < nextCheck) return;
        nextCheck = Time.unscaledTime + .25f;
        var renderers = target.GetComponentsInChildren<Renderer>();
        Bounds bounds = default;
        bool found = false;
        int current = 17;
        foreach (var renderer in renderers)
        {
            if (!renderer.enabled || renderer is ParticleSystemRenderer) continue;
            current = unchecked(current * 31 + renderer.GetInstanceID());
            var tight = MeshBounds(renderer);
            if (!found) { bounds = tight; found = true; }
            else bounds.Encapsulate(tight);
        }
        if (!found || current == signature) return;
        signature = current;
        preview.orthographic = true;
        if (preview.targetTexture != null) preview.aspect = (float)preview.targetTexture.width / preview.targetTexture.height;
        preview.orthographicSize = Mathf.Max(bounds.extents.y, bounds.extents.x / preview.aspect) * 1.20f;
        float distance = Mathf.Max(3, bounds.size.magnitude * 3);
        // The existing preview's direction is already the prefab's front.
        preview.transform.position = bounds.center - preview.transform.forward * distance;
        preview.nearClipPlane = .01f;
        preview.farClipPlane = distance * 3;
        if (System.Environment.GetEnvironmentVariable("HEALTHMON_VISUAL_REVIEW") == "1")
            Debug.Log($"PREVIEW_FRAME bounds={bounds} aspect={preview.aspect} size={preview.orthographicSize} texture={preview.targetTexture?.width}x{preview.targetTexture?.height}");
    }

    private static Bounds MeshBounds(Renderer renderer)
    {
        Mesh baked = null;
        Mesh mesh = null;
        try
        {
            if (renderer is SkinnedMeshRenderer skin)
            {
                // Match ArEvolutionModel: compensate for the skin transform
                // before TransformPoint applies its scale to the vertices.
                baked = new Mesh(); skin.BakeMesh(baked, true); mesh = baked;
            }
            else mesh = renderer.GetComponent<MeshFilter>()?.sharedMesh;
            if (mesh == null || mesh.vertexCount == 0) return renderer.bounds;
            if (!mesh.isReadable)
            {
                var local = mesh.bounds;
                var world = new Bounds(renderer.transform.TransformPoint(local.center), Vector3.zero);
                for (int i = 0; i < 8; i++) world.Encapsulate(renderer.transform.TransformPoint(local.center + Vector3.Scale(local.extents,
                    new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1))));
                return world;
            }
            var vertices = mesh.vertices;
            var bounds = new Bounds(renderer.transform.TransformPoint(vertices[0]), Vector3.zero);
            foreach (var vertex in vertices) bounds.Encapsulate(renderer.transform.TransformPoint(vertex));
            return bounds;
        }
        finally { if (baked != null) Destroy(baked); }
    }
}
