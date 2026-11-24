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
            {
                if (previewCamera.transform.Find("EvolutionFrontLight") == null)
                {
                    var lightObject = new GameObject("EvolutionFrontLight", typeof(Light));
                    lightObject.transform.SetParent(previewCamera.transform, false);
                    var light = lightObject.GetComponent<Light>();
                    light.type = LightType.Directional;
                    light.color = Color.white;
                    light.intensity = 1.4f;
                    light.shadows = LightShadows.None;
                    light.cullingMask = previewCamera.cullingMask;
                }
                var target = previewCamera.transform.parent.Find("PetVisualCopy_AnimationOnly");
                if (target != null)
                {
                    var framing = previewCamera.GetComponent<HealthMonPreviewFraming>() ?? previewCamera.gameObject.AddComponent<HealthMonPreviewFraming>();
                    framing.target = target;
                }
                previewCamera.enabled = controller != null &&
                    controller.evolutionOverlay != null && controller.evolutionOverlay.activeInHierarchy;
            }
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
