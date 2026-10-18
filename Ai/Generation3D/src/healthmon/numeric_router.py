"""Dispatch numerical requests by registered species anatomy."""
from .numeric_evolution import IDENTITIES, compile_numeric_evolution
from .biped_evolution import compile_biped_evolution


def compile_for_species(profile):
    if profile['species'] in IDENTITIES:
        return compile_numeric_evolution(profile)
    return compile_biped_evolution(profile)
