using UnityEditor;
using UnityEngine;

// AssetPreview chooses a diagonal editor thumbnail. Game portraits instead use
// the prefab's +Z face, level camera and full renderer bounds, including ears.
public static class HealthMonFrontPortrait
{
    public static Texture2D Render(GameObject prefab, int size = 512)
    {
        var preview = new PreviewRenderUtility();
        try
        {
            var model = Object.Instantiate(prefab);
            preview.AddSingleGO(model);
            model.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            bool character = prefab.name.StartsWith("Cute_Slime", System.StringComparison.Ordinal);
            foreach (var child in model.GetComponentsInChildren<Transform>(true))
                if (character && (child.name.StartsWith("Jewelry_", System.StringComparison.OrdinalIgnoreCase) ||
                    child.name.IndexOf("AccessoryAnchor", System.StringComparison.OrdinalIgnoreCase) >= 0))
                    child.gameObject.SetActive(false);
            foreach (var animator in model.GetComponentsInChildren<Animator>(true)) animator.enabled = false;
            var renderers = model.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) throw new System.InvalidOperationException("No portrait mesh: " + prefab.name);
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers) bounds.Encapsulate(renderer.bounds);
            var camera = preview.camera;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.clear;
            camera.orthographic = true;
            camera.orthographicSize = Mathf.Max(bounds.extents.x, bounds.extents.y) * 1.17f;
            float distance = Mathf.Max(3, bounds.size.magnitude * 3);
            camera.transform.position = bounds.center + (character ? Vector3.forward : new Vector3(1, .85f, 1).normalized) * distance;
            camera.transform.LookAt(bounds.center, Vector3.up);
            camera.nearClipPlane = .01f;
            camera.farClipPlane = distance * 3;
            preview.lights[0].intensity = 1.2f;
            preview.lights[0].transform.rotation = Quaternion.Euler(30, 200, 0);
            preview.lights[1].intensity = .8f;
            preview.lights[1].transform.rotation = Quaternion.Euler(330, 140, 0);
            preview.ambientColor = new Color(.55f, .55f, .55f);
            preview.BeginStaticPreview(new Rect(0, 0, size, size));
            preview.Render(true);
            var color = preview.EndStaticPreview();
            // URP's editor static preview forces opaque alpha. Render a separate
            // unlit silhouette so UI portraits retain a transparent background.
            var silhouette = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
            silhouette.SetColor("_BaseColor", Color.white);
            foreach (var renderer in renderers)
            {
                var materials = renderer.sharedMaterials;
                for (int i = 0; i < materials.Length; i++) materials[i] = silhouette;
                renderer.sharedMaterials = materials;
            }
            Texture2D mask = null;
            try
            {
                preview.BeginStaticPreview(new Rect(0, 0, size, size));
                preview.Render(true);
                mask = preview.EndStaticPreview();
                var pixels = color.GetPixels(); var coverage = mask.GetPixels();
                for (int i = 0; i < pixels.Length; i++)
                {
                    float alpha = coverage[i].r;
                    pixels[i] = alpha < .001f ? Color.clear : new Color(pixels[i].r / alpha, pixels[i].g / alpha, pixels[i].b / alpha, alpha);
                }
                var transparent = new Texture2D(size, size, TextureFormat.RGBA32, false);
                transparent.SetPixels(pixels); transparent.Apply();
                Object.DestroyImmediate(color);
                return transparent;
            }
            finally { if (mask != null) Object.DestroyImmediate(mask); Object.DestroyImmediate(silhouette); }
        }
        finally { preview.Cleanup(); }
    }
}
