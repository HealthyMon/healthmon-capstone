"""The game's 2511 adapter evolves the actual slime, never a legacy wolf seed."""
from Ai.Generation3D.src.healthmon.species_contract import validate_contract


def require_slime_parent(parent):
    if parent.get('species') != 'slime':
        raise ValueError('evolution_2511_requires_slime_parent: legacy animal parent was not migrated')
    return validate_contract(parent.get('species_contract'), 'slime')
