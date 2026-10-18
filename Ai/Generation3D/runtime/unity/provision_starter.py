from pathlib import Path
from job_store import Store, read

runtime = Path('E:/qwen-llm/healthmon-generation3d/Ai/Generation3D')
folder = runtime / 'outputs/unity_service/work/lucan-starter'
store = Store(runtime / 'outputs/unity_service')
try:
    current = store.current('lucan-local')
except FileNotFoundError:
    if read(folder / 'reconstruction/case_result.json')['status'] != 'PASS':
        raise ValueError('Starter rig validation has not passed')
    current = store.publish('lucan-local', 'starter-v1', 0, folder / 'image.png', folder / 'reconstruction/rigging/final_rigged.glb',
        provenance=dict(kind='shared_generated_starter', synthetic_demo=True,
                        original_model='outputs/unity_service/work/lucan-starter/reconstruction/rigging/final_rigged.glb'))
print(current['revision'], current['mesh'])
