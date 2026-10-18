using TMPro;
using UnityEngine;

public class DialoguePrototype : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private TMP_InputField messageInput;
    [SerializeField] private TMP_Text userMessageText;
    [SerializeField] private TMP_Text characterResponseText;
    [SerializeField] private TMP_Text personalityText;
    [SerializeField]
    private QuestPrototype questPrototype;

    public void SendMessage()
    {
        string message = messageInput.text.Trim();

        if (string.IsNullOrEmpty(message))
            return;

        userMessageText.text = message;

        string response = GetPrototypeResponse(message);

        characterResponseText.text = response;

        messageInput.text = "";
        
        if (questPrototype != null)
        {
            questPrototype.AddDialogue();
        }
    }

    private string GetPrototypeResponse(string message)
    {
        if (message.Contains("운동"))
        {
            personalityText.text = "성격 : 다정함";
            return "오늘 조금 힘들어도 괜찮아. 가볍게 시작해볼까?";
        }

        if (message.Contains("밥") || message.Contains("음식"))
        {
            personalityText.text = "성격 : 호기심 많음";
            return "오늘은 어떤 음식을 먹었는지 궁금해!";
        }

        if (message.Contains("힘들") || message.Contains("피곤"))
        {
            personalityText.text = "성격 : 다정함";
            return "오늘은 무리하지 말고 조금 쉬어도 괜찮아.";
        }

        return "그렇구나! 오늘 있었던 일을 조금 더 이야기해줘.";
    }
}