using System.IO;
using System.Text;
using TMPro;
using UnityEditor;
using UnityEngine;

public static class DialogueVisibilityDiagnostic
{
    [MenuItem("HealthMon/Diagnostics/Dialogue visibility")]
    public static void Capture()
    {
        var report = new StringBuilder("playing=" + Application.isPlaying + "\n");
        foreach (var d in Object.FindObjectsByType<DialoguePrototype>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            var serialized = new SerializedObject(d);
            var layout = d.GetComponent<DialogueRuntimeLayout>();
            report.AppendLine("dialogue=" + d.name + " layout=" + (layout != null) + " valid=" + (layout != null && layout.HasValidLayout));
            foreach (string field in new[] { "characterResponseText", "floatingBubbleText" })
            {
                var t = serialized.FindProperty(field).objectReferenceValue as TMP_Text;
                if (t == null) { report.AppendLine(field + "=null"); continue; }
                report.AppendLine(field + " length=" + t.text.Length + " enabled=" + t.enabled + " color=" + t.color + " rect=" + t.rectTransform.rect + " culled=" + t.canvasRenderer.cull);
                for (Transform p = t.transform; p != null; p = p.parent)
                {
                    var group = p.GetComponent<CanvasGroup>();
                    report.AppendLine(p.name + " active=" + p.gameObject.activeSelf + " scale=" + p.localScale + " position=" + p.position + (group == null ? "" : " alpha=" + group.alpha));
                }
            }
        }
        string path = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.runtime/dialogue-visibility.txt"));
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(path, report.ToString());
    }
}
