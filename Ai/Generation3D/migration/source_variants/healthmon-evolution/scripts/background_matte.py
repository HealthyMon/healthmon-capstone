"""CPU-only segmentation with the already cached BRIA RMBG ONNX checkpoint."""
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
from PIL import Image
import onnxruntime as ort

source,output=map(Path,sys.argv[1:3])
weights=Path('/workspace/3d_model_comparison/20261005/cache/u2net/models/bria-rmbg/bria-rmbg.onnx')
if not weights.is_file():raise FileNotFoundError('Existing background-removal checkpoint missing; no download is attempted')
start=time.monotonic()
options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
session=ort.InferenceSession(str(weights),sess_options=options,providers=['CPUExecutionProvider'])
im=Image.open(source).convert('RGBA')
rgb=np.asarray(im.convert('RGB').resize((1024,1024),Image.Resampling.LANCZOS)).astype(np.float32)/255
rgb=(rgb-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
input_array=rgb.transpose(2,0,1)[None]
pred=session.run(None,{session.get_inputs()[0].name:input_array})[0][0,0]
if not np.isfinite(pred).all() or pred.max()<=pred.min():raise ValueError('Invalid predicted segmentation mask')
pred=(pred-pred.min())/(pred.max()-pred.min())
mask=Image.fromarray((pred*255).astype('uint8')).resize(im.size,Image.Resampling.LANCZOS)
# A firm matte prevents low-opacity decoder/background remnants becoming 3D planes.
a=np.asarray(mask);alpha=np.where(a>=128,255,0).astype('uint8')
im.putalpha(Image.fromarray(alpha));im.save(output)
record=dict(method='existing_cached_BRIA_RMBG_ONNX_CPU',weights=str(weights),
 weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),providers=session.get_providers(),
 actual_segmentation_called=True,threshold=128,rgb_modified=False,seconds=time.monotonic()-start)
output.with_suffix('.segmentation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
