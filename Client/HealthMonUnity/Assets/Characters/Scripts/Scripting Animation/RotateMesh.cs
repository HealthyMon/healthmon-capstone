using System.Collections;
using System.Collections.Generic;
using UnityEngine;


namespace Infinity3DGame.ScriptingAnimationSystem
{

    public class RotateMesh : MonoBehaviour
    {
        [SerializeField]
        public float speedX = 0;
        public float speedY = 30;
        public float speedZ = 0;

        void Start()
        {

        }

        void Update()
        {
            this.transform.Rotate(speedX * Time.deltaTime, speedY * Time.deltaTime, speedZ * Time.deltaTime);
        }

    }
}