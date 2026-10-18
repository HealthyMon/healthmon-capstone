"""Optional same-stage edits for score attributes weakened in a long body prompt."""
from .numeric_evolution import compile_numeric_evolution, digest_json


def compile_appearance_refinement(profile, attribute='nutrition'):
    compiled=compile_numeric_evolution(profile)
    if compiled is None:
        raise ValueError('A base milestone request is required')
    h=compiled['decision']['health_summary']
    if attribute=='nutrition':
        if h['Nutrition']>=70:
            appearance=('Keep a smooth, lustrous, well-organized cream-and-apricot coat. '+
                'Make the innate gold cloud-whorl or green vein markings clearly continuous, bright and crisply legible over the torso and legs. '+
                'Give the mane and tail clean flowing shapes with polished warm apricot or vibrant green edges.')
        elif h['Nutrition']>=40:
            appearance=('Give the cream-and-apricot coat or ivory woodland coat a soft satin finish. '+
                'Use gently visible innate whorl or vein markings and moderately organized mane and tail edges.')
        else:
            appearance=('Replace the shiny surface with visibly matte, coarse, tousled natural wool or fur. '+
                'Remove the bright gold decorative whorl lines or bright green vein highlights from the torso and legs: keep those surfaces plain softly mottled cream, ivory and muted warm oatmeal/apricot. '+
                'Give the mane and tail irregular softly tufted edges while retaining their exact developed cloud or leaf anatomy. '+
                'This is an appealing rugged guardian with subdued innate markings, equal in evolutionary development and dignity to the polished guardian.')
        attribute_input={'Nutrition':h['Nutrition']}
        instruction=f'EDIT THE COAT AND INNATE MARKINGS ONLY. Game meal-quality score is {h["Nutrition"]:g}/100. {appearance}'
    elif attribute=='personality':
        p=compiled['decision']['personality']
        instruction=f'EDIT THE FACIAL EXPRESSION AND HEAD CARRIAGE ONLY. {compiled["visual_controls"]["personality"]} Affinity {p["Affinity"]}/100, Initiative {p["Initiative"]}/100, Mood {p["Mood"]}/100.'
        attribute_input=p
    else:raise ValueError('Unknown refinement attribute')
    prompt=f'''{instruction}
Image1 is the actual already evolved HEALTHMON {profile['species']} Stage{compiled['transition']['target_stage']} body. Edit that same individual, preserving its exact body proportions, waist, abdomen, muscle distribution, legs, paws, tail and developed head/shoulder anatomical structures. Preserve the species palette and same evolutionary stage. Preserve the camera, composition, body pose and white background. For a coat edit, preserve the original face expression and head carriage. For a facial edit, preserve the original coat and body shape. Food quality alone must not add body fat or reverse its evolution. Exactly one complete creature. Render the actual requested edit, no panels, lettering or additional objects.'''
    return {'prompt':prompt,'attribute':attribute,'attribute_inputs':attribute_input,
        'numeric_input_sha256':compiled['numeric_input_sha256'],
        'attribute_input_sha256':digest_json(attribute_input),
        'decision':compiled['decision'],'numeric_inputs':profile,
        'rule_status':'Explicit game appearance mapping, not a medical or learned physiology model'}
