
using UnityEngine;
using UnityEngine.UI;

public class UISpriteSequence : MonoBehaviour
{
    [SerializeField] private Image targetImage;
    [SerializeField] private Sprite[] frames;

    [Min(0.01f)]
    [SerializeField] private float frameDuration = 0.225f;

    private float timer;
    private int currentFrame;

    private void OnEnable()
    {
        timer = 0f;
        currentFrame = 0;

        if (targetImage != null && frames.Length > 0)
            targetImage.sprite = frames[0];
    }

    private void Update()
    {
        if (targetImage == null ||
            frames == null ||
            frames.Length == 0)
            return;

        if (currentFrame >= frames.Length - 1)
            return;

        timer += Time.deltaTime;

        while (timer >= frameDuration &&
               currentFrame < frames.Length - 1)
        {
            timer -= frameDuration;
            currentFrame++;

            targetImage.sprite = frames[currentFrame];
        }
    }
}
