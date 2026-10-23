using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Updates the selected jewelry image without modifying CustomizationPrototype.
/// The Editor icon wizard configures this component on CustomizationManager.
/// </summary>
public class HealthMonJewelryIconBinder : MonoBehaviour
{
    [SerializeField] private Button[] collectionButtons = new Button[4];
    [SerializeField] private Button[] overlayButtons = new Button[4];
    [SerializeField] private Sprite[] itemSprites = new Sprite[4];
    [SerializeField] private Image[] selectedItemImages = new Image[2];

    // Set by HealthMonJewelryIconWizard while editing the scene.
    public void Configure(Button[] collection, Button[] overlay, Sprite[] sprites, Image[] targets)
    {
        collectionButtons = collection;
        overlayButtons = overlay;
        itemSprites = sprites;
        selectedItemImages = targets;
    }

    private void Awake()
    {
        Register(collectionButtons);
        Register(overlayButtons);
    }

    private void Start()
    {
        // CustomizationPrototype.Start() selects the initial necklace.
        ShowItem(0);
    }

    private void Register(Button[] buttons)
    {
        if (buttons == null) return;
        for (int i = 0; i < Mathf.Min(buttons.Length, 4); i++)
        {
            int index = i;
            if (buttons[i] != null)
                buttons[i].onClick.AddListener(() => ShowItem(index));
        }
    }

    public void ShowItem(int index)
    {
        if (itemSprites == null || index < 0 || index >= itemSprites.Length) return;
        Sprite sprite = itemSprites[index];
        if (selectedItemImages == null) return;
        foreach (Image target in selectedItemImages)
        {
            if (target == null) continue;
            target.sprite = sprite;
            target.enabled = sprite != null;
            target.preserveAspect = true;
        }
    }
}
