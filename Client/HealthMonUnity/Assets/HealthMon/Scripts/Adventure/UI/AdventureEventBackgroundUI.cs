using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Displays full-screen event artwork behind the existing adventure event panels.
/// Put the PNG files in Resources/AdventureEventBackgrounds, and place the
/// RawImage behind the interactive event canvases in Canvas sorting order.
/// </summary>
public class AdventureEventBackgroundUI : MonoBehaviour
{
    [SerializeField] private RawImage backgroundImage;

    private void Awake() => Hide();

    public void Show(AdventureEventType eventType)
    {
        string imageName;
        switch (eventType)
        {
            case AdventureEventType.Rest: imageName = "Rest"; break;
            case AdventureEventType.Reward: imageName = "Reward"; break;
            case AdventureEventType.Quiz: imageName = "Quiz"; break;
            default: Hide(); return;
        }
        Display(imageName);
    }

    public void ShowSpecial(string eventTitle)
    {
        switch (eventTitle)
        {
            case "수상한 제단": Display("SpecialAltar"); break;
            case "갈라진 광맥": Display("SpecialOre"); break;
            case "의문의 샘": Display("SpecialSpring"); break;
            default:
                // Custom events without an illustration use the regular cave background.
                Hide();
                break;
        }
    }

    public void Hide()
    {
        if (backgroundImage == null) return;
        backgroundImage.texture = null;
        backgroundImage.gameObject.SetActive(false);
    }

    private void Display(string imageName)
    {
        if (backgroundImage == null) return;
        Texture2D texture = Resources.Load<Texture2D>("AdventureEventBackgrounds/" + imageName);
        if (texture == null)
        {
            Debug.LogWarning("[AdventureEventBackgroundUI] 배경 이미지를 찾을 수 없습니다: " + imageName);
            Hide();
            return;
        }
        backgroundImage.texture = texture;
        backgroundImage.color = Color.white;
        backgroundImage.raycastTarget = false;
        backgroundImage.gameObject.SetActive(true);
    }
}
