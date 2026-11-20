using UnityEngine;

namespace HealthMon.Evolution
{
    /// <summary>
    /// Enable the isolated RenderTexture camera only while the evolution UI is open.
    /// Does not change the original pet, HomeCamera, PetPreviewCamera or AI logic.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class EvolutionLivePetCameraGate : MonoBehaviour
    {
        [SerializeField] private EvolutionUIController controller;
        [SerializeField] private Camera previewCamera;

        public void Configure(EvolutionUIController ui, Camera camera)
        {
            controller = ui;
            previewCamera = camera;
        }

        private void Awake()
        {
            if (previewCamera != null)
                previewCamera.enabled = controller != null &&
                    controller.evolutionOverlay != null && controller.evolutionOverlay.activeInHierarchy;
        }

        private void OnEnable()
        {
            if (controller == null) return;
            controller.onEvolutionOpened.AddListener(EnableCamera);
            controller.onEvolutionClosed.AddListener(DisableCamera);
        }

        private void OnDisable()
        {
            if (controller == null) return;
            controller.onEvolutionOpened.RemoveListener(EnableCamera);
            controller.onEvolutionClosed.RemoveListener(DisableCamera);
        }

        private void EnableCamera()
        {
            if (previewCamera != null) previewCamera.enabled = true;
        }

        private void DisableCamera()
        {
            if (previewCamera != null) previewCamera.enabled = false;
        }
    }
}
