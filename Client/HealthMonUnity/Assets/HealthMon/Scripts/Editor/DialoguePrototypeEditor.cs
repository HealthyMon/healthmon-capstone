using UnityEditor;
using UnityEngine;

[CustomEditor(typeof(DialoguePrototype))]
public sealed class DialoguePrototypeEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        var dialogue = (DialoguePrototype)target;
        EditorGUILayout.Space();
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority)
        {
            EditorGUILayout.HelpBox("공용 서버 모드: 실행 화면의 COMMON SERVER 패널에서 주소·사용자 토큰·펫을 설정하세요. 자격증명은 Inspector에 입력하지 않습니다.", MessageType.Info);
            return;
        }
        if (!Application.isPlaying)
        {
            EditorGUILayout.HelpBox("Play 모드에서 실제 API에 Connect합니다. 사용자 토큰은 런타임에만 사용하며 Scene에 저장하지 않습니다.", MessageType.Info);
            return;
        }
        EditorGUILayout.LabelField("Actual Server", dialogue.ServerUrl);
        dialogue.RuntimeToken = EditorGUILayout.PasswordField("Runtime User Token", dialogue.RuntimeToken ?? "");
        EditorGUILayout.LabelField("Pet ID", dialogue.PetId ?? "연결 전");
        if (GUILayout.Button("Connect")) dialogue.Connect();
        if (GUILayout.Button("Retry Pending Chat")) dialogue.RetryPendingChat();
        EditorGUILayout.LabelField("Last Request", dialogue.LastRequestId ?? "");
        EditorGUILayout.LabelField("Fallback", dialogue.LastFallback.ToString());
    }
}
