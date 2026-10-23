"""Non-destructive white-background matte for near-opaque decoder alpha."""
from pathlib import Path
import hashlib, json, os

def prepare(source, output):
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    source,output=Path(source),Path(output)
    im=Image.open(source).convert('RGBA'); a=np.array(im)
    alpha=a[:,:,3]
    if (alpha<128).mean()>=.001 and (alpha>204).any():
        mode='existing_meaningful_alpha'
    else:
        import subprocess,sys
        output.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([os.environ.get('HEALTHMON_MATTING_PYTHON', '/workspace/healthmon-evolution/.venvs/matting/bin/python'),str(Path(__file__).with_name('background_matte.py')),
                        str(source),str(output)],check=True)
        a=np.array(Image.open(output).convert('RGBA'))
        mode='existing_cached_BRIA_RMBG_ONNX_CPU'
        if not .03 <= (a[:,:,3]>128).mean() <= .95:
            raise ValueError('Implausible foreground mask; inspect the uploaded image')
    output.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(a).save(output)
    record=dict(method=mode,original_modified=False,
        input=str(source.resolve()),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        output=str(output.resolve()),output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        transparent_fraction=float((a[:,:,3]<128).mean()),rgb_modified=False)
    if output.with_suffix('.segmentation.json').exists():
        record['segmentation']=json.loads(output.with_suffix('.segmentation.json').read_text())
    output.with_suffix('.matte.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
