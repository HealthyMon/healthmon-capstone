"""Shared evolution quality requirements, independent of identity and body scores.

An approved image establishes artistic quality, not a compulsory silhouette.
This contract is a generation instruction, never evidence of visual success.
"""
import hashlib
from pathlib import Path

VERSION = 'structural_evolution_20261010_v2'
STAGE_DESIGNS = Path(__file__).resolve().parents[2] / 'configs/web_stage_designs.json'


def stage_design(species, stage, seed):
    """Concrete design intent; sampling seed chooses structure, never fat or health."""
    import json
    config = json.loads(STAGE_DESIGNS.read_text())
    choices = config['species'].get(species, {}).get(str(stage))
    if not choices:
        return None
    index = seed % len(choices)
    name, brief = choices[index]
    return dict(design_id=f'{species}_s{stage}_{name}', variant=index, brief=brief,
                status=config['status'], config_sha256=hashlib.sha256(STAGE_DESIGNS.read_bytes()).hexdigest())


def evolution_structure(source_stage, target_stage):
    if source_stage == target_stage:
        return ('SAME-STAGE BODY EDIT: retain this exact evolved design, its head and limb '
                'structure, core organs and silhouette landmarks. Apply the requested body '
                'fat and muscle distribution without inventing another evolution stage.')
    return f'''PRIMARY TASK: DESIGN A NEW EVOLVED CREATURE, Stage {source_stage} -> Stage {target_stage}.
The source supplies ancestry and core motifs, not a fixed face, body plan or outline. Invent an iconic, appealing monster-collecting-game creature with confident character and beautiful coherent shapes. Artistic quality references are a quality bar, never a design to duplicate.
Redesign the connected body as a whole: head-to-body ratio and skull/beak profile, how the neck meets the shoulders, ribcage relative to hips and back line, functional limb shapes and feet, and a species-specific tail or innate organ. At least three of these structural relationships must change together. Choose a small number of purposeful, harmonious large shapes; anatomical novelty alone is not success. Keep animal anatomy coherent and the silhouette attractive.
Stage {target_stage} must be unmistakably a new evolution even at the same displayed height, in black silhouette, with colors and adornments removed. Larger size, added muscle/fat, longer fur, an older expression or ornaments alone are insufficient. Do not turn every species into the same spiky wolf guardian, do not add costumes, weapons or armor, and do not force lanky or humanoid proportions to manufacture novelty.
Stage 1 is already a new creature with a distinct body construction. Stage 2 is a substantial redesign of Stage 1, with mature character and a new arrangement of major body masses. Stage 3 is a further definitive transformation of Stage 2, not the same guardian with more fur or decoration. Keep room for the remaining stages.
At Stage 3, make a magnificent fully realized sacred creature: numinous presence, a noble expressive face, a memorable powerful silhouette and spectacular species-specific biological structures. Sacredness belongs to the evolved body, not a crown, armor, weapon or decorative clutter. A lean final form and a genuinely fat final form are equally complete sacred evolutions; retain the same final-stage anatomy while changing visible fat and training development.
First establish the target-stage anatomy; then apply the recorded body-development and fat conditions to that anatomy. Low activity and high fat retain the full evolved structure and presence. Do not substitute muscles for fat or aggression for personality. Within a fixed evolved design, numeric body edits must preserve its structural landmarks.'''


def web_design_direction(species, source_stage, target_stage, form):
    """Reuse established quality/form policy without importing legacy wrong species."""
    import json
    from .prompts import ART_DIRECTION_CONFIG
    policy = json.loads(ART_DIRECTION_CONFIG.read_text())['shared_design_policy']
    return (evolution_structure(source_stage, target_stage) + '\nSHARED ARTISTIC QUALITY: ' +
            policy['principle'] + '\nSAME-STAGE FORM EXPRESSION: ' + policy['form_features'][form] +
            '\nThe separate species identity below is authoritative; do not borrow another species anatomy.')


def provenance():
    from .prompts import ART_DIRECTION_CONFIG
    return dict(version=VERSION, contract_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                shared_art_direction_sha256=hashlib.sha256(ART_DIRECTION_CONFIG.read_bytes()).hexdigest(),
                visual_success='REQUIRES_ACTUAL_IMAGE_REVIEW', target_image_template=False)
