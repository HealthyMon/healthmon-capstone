"""Select one decoded FPB weight proposal per crop, without detection filtering."""
import numpy as np


def select_weight(proposals, content):
    p = np.asarray(proposals)
    valid = np.isfinite(p).all(axis=1) & (p[:,4]>0) & (p[:,2]>0) & (p[:,3]>0)
    p = p[valid]
    if not len(p):
        raise RuntimeError('No finite positive FPB mass; cannot fabricate a weight')
    boxes = np.column_stack((p[:,0]-p[:,2]/2,p[:,1]-p[:,3]/2,p[:,0]+p[:,2]/2,p[:,1]+p[:,3]/2))
    intersection = np.maximum(0,np.minimum(boxes[:,2:],content[2:])-np.maximum(boxes[:,:2],content[:2])).prod(axis=1)
    area = (content[2]-content[0])*(content[3]-content[1])
    iou = intersection / np.maximum(p[:,2]*p[:,3]+area-intersection,1e-9)
    classes = p[:,5:].argmax(axis=1)
    confidence = p[:,5:].max(axis=1)
    # Prefer a candidate representing the entire crop, rather than a small garnish.
    rank = confidence * iou
    index = int(rank.argmax())
    weak = bool(confidence[index]<.35 or iou[index]<.5)
    return {'weight_g':float(p[index,4]),
            'weight_status':'estimated_fpb_crop_low_confidence' if weak else 'estimated_fpb_crop',
            'needs_weight_confirmation':weak,
            'fpb_confidence':float(confidence[index]), 'crop_iou':float(iou[index]),
            'fpb_class_id':int(classes[index]),
            'proposal_bbox_letterbox_xyxy':boxes[index].tolist(),
            'selection':'max(class_score * crop_iou), no detection confidence cutoff'}
