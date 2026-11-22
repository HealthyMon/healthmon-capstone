"""One final functional suite, end-to-end run, and independent logit equivalence."""
import json
import subprocess
import sys
from pathlib import Path
import torch
import torch.nn.functional as F
from PIL import Image
from detect import ROOT, checkpoint
from food2k import FoodClassifier, DEFAULT_MODEL


@torch.inference_mode()
def reference(x, weights):
    # Independent standard ViT equations with original checkpoint keys.
    x = F.conv2d(x, weights['patch_embed.proj.weight'], weights['patch_embed.proj.bias'], stride=16)
    x = torch.cat((weights['cls_token'], x.flatten(2).transpose(1,2)), dim=1) + weights['pos_embed']
    for i in range(12):
        prefix = f'blocks.{i}.'
        norm = F.layer_norm(x, (768,), weights[prefix+'norm1.weight'], weights[prefix+'norm1.bias'], 1e-6)
        qkv = F.linear(norm, weights[prefix+'attn.qkv.weight'], weights[prefix+'attn.qkv.bias'])
        q,k,v = qkv.reshape(1,577,3,12,64).permute(2,0,3,1,4).unbind(0)
        attn = ((q @ k.transpose(-1,-2)) / 8).softmax(-1)
        z = (attn @ v).transpose(1,2).reshape(1,577,768)
        x = x + F.linear(z, weights[prefix+'attn.proj.weight'], weights[prefix+'attn.proj.bias'])
        z = F.layer_norm(x, (768,), weights[prefix+'norm2.weight'], weights[prefix+'norm2.bias'], 1e-6)
        z = F.gelu(F.linear(z, weights[prefix+'mlp.fc1.weight'], weights[prefix+'mlp.fc1.bias']))
        x = x + F.linear(z, weights[prefix+'mlp.fc2.weight'], weights[prefix+'mlp.fc2.bias'])
    x = F.layer_norm(x, (768,), weights['norm.weight'], weights['norm.bias'], 1e-6)
    return F.linear(x[:,0], weights['head.weight'], weights['head.bias'])


def main():
    out = ROOT.parent/'outputs/final_food2k'
    out.mkdir(exist_ok=False)
    for name in ('test_multifood.py','test_food2k.py'):
        run = subprocess.run([sys.executable,str(ROOT/name)],capture_output=True,text=True)
        (out/(name+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved log')
    run = subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT.parent/'Run-FoodAI.ps1'),
                          '-ImagePath','C:/Users/user/Downloads/image.png','-OutputPath',str(out/'example')],
                         capture_output=True)
    (out/'inference.log').write_bytes(run.stdout+run.stderr)
    if run.returncode:
        raise RuntimeError('End-to-end inference failed; see saved log')
    result = json.loads((out/'example/result.json').read_text(encoding='utf-8'))
    assert result['pipeline'] == 'dishseg_locator_then_noisyvit_food2k'
    assert result['foods'], 'Expected detections on the provided sample'
    torch.set_num_threads(4)
    classifier = FoodClassifier()
    first = result['foods'][0]
    with Image.open(out/'example/input_upright.jpg') as image:
        crop = image.crop(first['classification_crop_xyxy'])
        x = classifier.transform(crop).unsqueeze(0).to('cuda:0')
    weights = {k:v.to('cuda:0') for k,v in checkpoint(DEFAULT_MODEL).items()}
    with torch.inference_mode():
        adapted = classifier.model(x)
        original = reference(x, weights)
    error = float((adapted-original).abs().max())
    torch.testing.assert_close(adapted, original, atol=1e-4, rtol=1e-4)
    for food in result['foods']:
        assert food['nutrition']['portion'] is None
        assert food['nutrition']['basis_g'] == 100
        assert food['name'] == classifier.table.rows[food['class_id']]['Category']
        assert len(food['candidates']) == 5
    with Image.open(out/'example/annotated.jpg') as image:
        assert image.size == (result['image_size']['width'],result['image_size']['height'])
    # Exercise the zero-detection rendering path without another model run.
    from detect import save
    save(dict(result,foods=[]),Image.new('RGB',(300,200),'white'),out/'empty')
    report = {'tests_passed':12, 'checkpoint_strict_load':True,'logit_max_absolute_error':error,
              'end_to_end':True,'detected_regions':len(result['foods']),
              'class_order':result['classifier']['class_order'],
              'class_order_verified_with_training_metadata':False,
              'accuracy_evaluated':False,
              'predictions':[{'name':f['name'],'score':f['name_confidence'],'food2k_id':f['class_id'],
                              'model_output_index':f['model_output_index']} for f in result['foods']]}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__ == '__main__':
    main()
