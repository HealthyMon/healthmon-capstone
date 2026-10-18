"""Explicit visual roles, evolutionary stage, physical condition and personality."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "evolution.json"
ART_DIRECTION_CONFIG = ROOT / "configs" / "evolution_art_direction.json"


def settings():
    return json.loads(CONFIG.read_text())


def form_for(scenario, stage):
    return settings()["scenario_forms"][scenario][stage]


def health_history(scenario, target_form):
    """Condition follows the selected Form even at an earlier scenario stage."""
    if target_form == 'HEAVY':
        return {'exercise': 'Previously active, then prolonged inactivity' if scenario == 'A_fit_then_heavy' else 'Prolonged low activity during early development',
                'diet': 'Sustained excess energy intake', 'prolonged_low_activity': True,
                'sustained_energy_excess': True}
    return {
        'FIT': {'exercise':'Regular species-appropriate exercise','diet':'Appropriate regular meals'},
        'BALANCED': {'exercise':'Regular walking or moderate daily activity','diet':'Reasonably balanced meals'},
        'INACTIVE': {'exercise':'Prolonged low activity','diet':'No established sustained excess energy intake'},
        'RECOVERY': {'exercise':'Previously heavy or inactive; exercise has gradually resumed consistently',
                     'diet':'Improved regular meals and reduced excess energy intake'}
    }[target_form] | {'prolonged_low_activity':target_form=='INACTIVE', 'sustained_energy_excess':False}


def evolution_art_direction(species, source_stage, target_stage, target_form):
    """Apply the shared design policy without conflating evolutionary stage and Form."""
    from .design_contract import evolution_structure
    policy = json.loads(ART_DIRECTION_CONFIG.read_text())['shared_design_policy']
    stage_brief = (
        "Retain the current stage's developed anatomy and signature motifs during this Form change."
        if source_stage == target_stage else policy['stages'][str(target_stage)]
    )
    return f"""EVOLUTION DESIGN DIRECTION:
{evolution_structure(source_stage, target_stage)}
{policy['principle']}
Stage design: {stage_brief}
Species design language: {policy['species_features'][species]}
Form design language: {policy['form_features'][target_form]}
Expression follows the requested personality independently. Every Form at this target stage shares its degree of evolutionary development. Preserve inherited body-history traits while developing the species' own anatomy and overall silhouette.
"""


def clean_prompt(species, stage, form):
    c = settings()
    return f"""Reconstruct one clean full-body HEALTHMON {species} creature, Stage {stage}, Form {form}.
Image 1 is an isolated region from the primary HEALTHMON concept poster. It is the MAIN VISIBLE DESIGN reference, not clean artwork.
Image 2 is the archive's mechanically extracted stage candidate. It is a secondary location/detail hint and may cut off appendages or contain text.
Use only the creature in these images, with the primary poster region taking priority where the candidate is cut off.
{c['species'][species]}
Preserve original visible proportions, color pattern, facial character, appendages and recognizable motifs. Remove ALL arrows, labels, lettering, chart lines, neighboring creatures, scenery and ground objects.
Restore any cropped body parts only as conservative, anatomically coherent continuations of what is visible. Do not invent exact canonical details on unseen surfaces. Keep uncertain rear details minimal.
Physical condition: {c['form_prompts'][form]}
Produce a high-quality original illustration suitable for textured 3D reconstruction: one complete creature, neutral standing pose, front-three-quarter view, feet separated, every visible ear, horn, limb and tail inside the frame with generous margin.
Use a transparent background and output an RGBA image. No cast scenery, no diagrams, no additional creature, no text. Do not copy any existing commercial creature franchise.
"""


def evolution_prompt(species, source_stage, target_stage, source_form, target_form,
                     identity_roles, personality=None):
    c = settings()
    art_direction = evolution_art_direction(species, source_stage, target_stage, target_form)
    stage_instruction = (
        "Change only the physical Form while retaining this evolutionary Stage. Do not introduce an extra stage."
        if source_stage == target_stage else
        "Create a genuinely more mature evolutionary stage. Develop the face, proportions and silhouette with species-appropriate anatomical changes guided by the target concept; do not merely enlarge or decorate the original."
    )
    roles = [f"Image {i+1}: PRIMARY IDENTITY reference — actual current textured 3D model, {v} view."
             for i, v in enumerate(identity_roles)]
    roles.append(f"Image {len(roles)+1}: DESIGN ONLY for the SAME INDIVIDUAL at its future Stage {target_stage} {target_form} — cleaned concept from the supplied ZIP; never an additional subject.")
    heavy_instruction = ('A HEAVY result must visibly contain fat and a rounder abdomen, not just muscle or armor.'
                         if target_form == 'HEAVY' else '')
    if species == 'lucan' and target_form == 'HEAVY':
        return f"""This is an RGBA image with transparency. Transform the ONE Lucan in Image 1 from Stage {source_stage} {source_form} into Stage {target_stage} HEAVY after prolonged inactivity and sustained overeating.
{chr(10).join(roles)}
Image 1 is the primary identity reference. The final image guides only the mature face, larger white mane and final-stage styling of that SAME individual.
{stage_instruction}
Completely change the body silhouette with clearly increased BODY FAT: give it a much wider, deep oval torso with a large soft furry potbelly hanging low between its four legs. The abdomen visibly bulges outward and downward, filling the formerly tucked-up gap beneath the body. Show rounded fat flanks and a broad waist. Keep the head similar in scale so the body looks unmistakably heavier.
Shift the near foreleg slightly forward so the bulging belly is clearly visible behind it. Reduce flank armor coverage enough to expose the soft abdomen. Do not hide fat under plates or add muscle bulk. Freely change torso anatomy and armor arrangement to achieve this transformation.
Preserve charcoal fur, amber eyes, gold-edged dark accents and appealing beast identity. Mature the muzzle and mane toward the design guide. Personality: {personality or c['personality']}; it affects expression, never body fat.
{art_direction}
Output exactly ONE complete quadruped in ONE slightly side-biased three-quarter standing view, with all paws and ears inside generous margins. No panels, contact sheets, duplicates or text. The image has alpha channel and the background is transparent.
"""
    return f"""This is an RGBA image with transparency. Edit Image 1 into ONE single evolved full-body HEALTHMON {species} creature.
Image 1 is the sole subject and editing base: the actual current creature's 3D render. All other images are references for this SAME individual, not additional subjects.
Fuse the references into ONE individual. The entire output is one uninterrupted image with exactly ONE creature, ONE body and ONE head, in a single front-three-quarter standing view.
Do not create a contact sheet, before/after comparison, grid, panels, duplicated subjects or multiple viewpoints. Never copy the input images into separate areas of the output.
Current Stage: {source_stage}; Target Stage: {target_stage}.
Current Form: {source_form}; Target Form: {target_form}.
Stage is progression/EXP. Form is long-term exercise/diet. Personality controls expression and posture, NEVER body fat.
Input order and reference roles:
{chr(10).join(roles)}
Use the actual current 3D renders as the primary identity. The target illustration supplies evolutionary direction; it must not overwrite the current creature's lineage.
{c['species'][species]}
{stage_instruction}
Target physical condition: {c['form_prompts'][target_form]}
{('Make the increased BODY FAT unmistakable: a large soft rounded abdomen protrudes below the chest and between the forelegs and hindlegs, with a broad waist and rounded furry flanks. Leave this soft belly clearly visible; torso armor must not conceal it. Retain four strong legs.' if target_form == 'HEAVY' and species == 'lucan' else '')}
Personality: {personality or c['personality']}.
Keep species lineage, signature colors, core motifs and appeal. The face may mature; it need not be identical. {heavy_instruction}
{art_direction}
Generate only that ONE complete evolved creature, centered and filling most of the frame, in one front-three-quarter neutral standing pose with separated feet for reconstruction. Keep all appendages visible with generous clear margin. The image has an alpha channel and the background is transparent. No labels, Korean lettering, arrows, chart layout, props, extra creatures or copied commercial creature designs.
"""
