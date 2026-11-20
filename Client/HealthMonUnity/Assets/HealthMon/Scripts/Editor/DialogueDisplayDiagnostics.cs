using System;
using System.IO;
using System.Text;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class DialogueDisplayDiagnostics
{
    static DialogueDisplayDiagnostics() { EditorApplication.delayCall += Capture; }

    [MenuItem("HealthMon/Diagnostics/Capture Dialogue Display")]
    public static void Capture()
    {
        if (!EditorApplication.isPlaying) return;
        var result = new StringBuilder();
        foreach (var dialogue in UnityEngine.Object.FindObjectsByType<DialoguePrototype>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            result.AppendLine("Dialogue active=" + dialogue.gameObject.activeInHierarchy);
            var fields = new SerializedObject(dialogue);
            foreach (var name in new[] { "characterResponseText", "floatingBubbleText", "userMessageText" })
            {
                var text = fields.FindProperty(name).objectReferenceValue as TMP_Text;
                result.AppendLine(name + " assigned=" + (text != null));
                if (text == null) continue;
                result.AppendLine($"enabled={text.enabled} chars={text.text.Length} color={text.color} rect={text.rectTransform.rect} culled={text.canvasRenderer.cull} vertices={text.textInfo.characterCount}");
                for (var at = text.transform; at != null; at = at.parent)
                {
                    var rect = at as RectTransform;
                    var group = at.GetComponent<CanvasGroup>();
                    result.AppendLine($"  {at.name} active={at.gameObject.activeSelf} scale={at.localScale} pos={at.position} rect={(rect != null ? rect.rect.ToString() : "-")} alpha={(group != null ? group.alpha.ToString() : "-")} mask={at.GetComponent<RectMask2D>() != null}");
                }
            }
            var layout = dialogue.GetComponent<DialogueRuntimeLayout>();
            result.AppendLine("layout=" + (layout != null) + " valid=" + (layout != null && layout.HasValidLayout));
        }
        string root = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
        Directory.CreateDirectory(Path.Combine(root, ".runtime"));
        File.WriteAllText(Path.Combine(root, ".runtime/dialogue-display.txt"), result.ToString());
    }
}
