import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AssetClassification:
    family: str
    archetype: str

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return (self.family, self.archetype) == other
        if isinstance(other, AssetClassification):
            return (self.family, self.archetype) == (other.family, other.archetype)
        return NotImplemented


_VOCABULARY = {
    "warrior": ("humanoid", "warrior"),
    "knight": ("humanoid", "warrior"),
    "caballero": ("humanoid", "warrior"),
    "wizard": ("humanoid", "wizard"),
    "blacksmith": ("humanoid", "blacksmith"),
    "human": ("humanoid", "generic"),
    "person": ("humanoid", "generic"),
    "chibi": ("humanoid", "generic"),
    "pig": ("quadruped", "pig"),
    "boar": ("quadruped", "pig"),
    "wolf": ("quadruped", "wolf"),
    "dog": ("quadruped", "dog"),
    "dragon": ("dragon", "dragon"),
    "potion": ("prop", "potion"),
    "sword": ("prop", "sword"),
}


def classify_subject(subject: str) -> AssetClassification:
    normalized = subject.lower().replace("_", " ")
    tokens = set(re.findall(r"[a-z]+", normalized))
    for token, result in _VOCABULARY.items():
        if token in tokens:
            return AssetClassification(*result)
    return AssetClassification("unknown", "generic")
