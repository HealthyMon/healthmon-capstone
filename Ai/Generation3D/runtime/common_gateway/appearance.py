"""Qualitative rendering of the already-validated shared v2.2 appearance decision.

No thresholds, game scores, species changes or model parameters are decided here.
Legacy body formulas and prompt functions remain unchanged for legacy callers.
"""
BODY_CONDITIONS = {
    'adipose': 'Visibly soft adipose body with a large projecting rounded abdomen, a wide soft waist, broad rounded flanks and soft thighs. Make the belly and flank volume unmistakably fuller than the ordinary or athletic form. Use low muscle definition; the mass is soft body fat rather than a muscular chest or thick fur.',
    'lean_athletic': 'Lean athletic body with a flat taut abdomen, a narrow waist, firm well-developed supporting muscles and clearly defined shoulders and hindquarters. Keep the silhouette lean without soft abdominal or flank bulges.',
    'lean': 'Visibly slim lightly built body with a narrow torso, flat abdomen, slender waist and modest muscle volume. Keep the supporting limbs complete and the stance stable; avoid both bulky muscles and rounded adipose flanks.',
    'bulky_athletic': 'Broad densely muscular athletic body with a thick firm chest, powerful shoulders, substantial hindquarters and strong supporting limbs. Show solid muscle volume rather than a hanging soft belly or adipose waist.',
    'rounded_general': 'Moderately rounded softly built body with a gently projecting abdomen, soft waist and rounded flanks. Show more soft body volume than the ordinary form, but less abdominal and flank mass than the strongly adipose form.',
    'upper_developed': 'Emphasize developed upper and front-body musculature: broad firm shoulders, chest and upper supporting limbs, visibly more developed than the lower and rear quarters. Keep the whole body connected and proportionate with complete supporting limbs.',
    'lower_developed': 'Emphasize developed lower and rear-body musculature: substantial pelvis, haunches, thighs and supporting rear limbs, visibly more developed than the chest and upper quarters. Keep the whole body connected and proportionate with complete supporting limbs.',
    'balanced_athletic': 'Balanced athletic body with evenly developed front and rear musculature, firm supporting limbs and a taut abdomen. Make the whole-body silhouette fit and proportionate with visible muscle development and a defined waist, without a soft projecting belly.',
    'developed_general': 'Well-developed generally strong body with firm supporting muscles and substantial connected body volumes. Show more physical development than the ordinary form while keeping a smooth proportionate silhouette and moderate abdomen.',
    'ordinary': 'Ordinary proportionate body with average supporting muscle development, a modest abdomen and an everyday balanced silhouette. Keep the body distinct from both a highly muscular athletic form and a strongly adipose rounded form.',
    'undertrained': 'Lightly developed supporting musculature with narrow softly defined shoulders, modest haunches and slender complete limbs. Show less muscle development than the ordinary form while retaining a stable connected body and the same species identity.',
}


def body_condition(profile):
    if profile.get('rule_version') != 'healthmon.v2.2':
        raise ValueError('An authoritative shared v2.2 profile is required')
    appearance=profile.get('appearance')
    if appearance not in BODY_CONDITIONS:
        raise ValueError('Unsupported authoritative appearance')
    return 'AUTHORITATIVE V2.2 APPEARANCE ['+appearance+']: '+BODY_CONDITIONS[appearance]


def apply_to_prompt(prompt,profile):
    """Replace the legacy condition line only in the explicit v2.2 adapter branch."""
    instruction=body_condition(profile)
    lines=prompt.splitlines()
    indexes=[index for index,line in enumerate(lines) if line.startswith('SCORE-DERIVED BODY CONDITION: ')]
    if len(indexes)!=1:
        raise ValueError('Expected exactly one explicit body condition in the existing prompt')
    lines[indexes[0]]='SCORE-DERIVED BODY CONDITION: '+instruction
    return '\n'.join(lines)+'\nFINAL AUTHORITATIVE BODY CONDITION: '+instruction+(
        ' Apply this condition to the actual abdomen, waist, flanks and supporting body masses, '
        'rather than changing only pose, colors, coat or decorative motifs. Preserve the specified '
        'species, evolution-stage anatomy and all complete supporting limbs.\n')
