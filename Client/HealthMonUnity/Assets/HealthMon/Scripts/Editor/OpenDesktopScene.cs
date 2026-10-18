using UnityEditor;
using UnityEditor.SceneManagement;

public static class OpenDesktopScene
{
    public static void Open()
    {
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        var dialogue = UnityEngine.Object.FindAnyObjectByType<DialoguePrototype>();
        if (dialogue != null) Selection.activeGameObject = dialogue.gameObject;
    }
}
