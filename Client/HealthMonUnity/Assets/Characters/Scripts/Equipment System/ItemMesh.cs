using System;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Infinity3DGame.EquipmentSystem
{
    [CreateAssetMenu(fileName = "New Item Mesh", menuName = "Infinity3D/Equipment System/Item Mesh")]
    public class ItemMesh : ScriptableObject
    {
        public Vector3 offset;
        public GameObject[] GameObject;

        private void OnValidate()
        {

        }
    }
}