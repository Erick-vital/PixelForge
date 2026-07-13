from app.schemas.sprite import AssetSpec, SpriteBlueprint, SpriteOutlineSpec, SpritePrimitive
from app.sprite_engine.character.side_skeleton import build_humanoid_side_skeleton
from app.sprite_engine.character.spec import CharacterSpec, PoseSpec
from app.sprite_engine.grammar.models import GrammarCapabilities


class HumanoidSideGrammar:
    name = "humanoid_side"
    skeleton_name = "HumanoidSideSkeleton"
    capabilities = GrammarCapabilities(
        "humanoid",
        frozenset({"side-view"}),
        frozenset({"generic", "warrior"}),
        frozenset({"side_neutral"}),
    )

    def supports(self, spec: AssetSpec) -> bool:
        stance = spec.character.pose.stance if spec.character else "side_neutral"
        return (
            spec.family == "humanoid"
            and spec.game_view == "side-view"
            and spec.archetype in self.capabilities.archetypes
            and stance in self.capabilities.poses
        )

    def compile(self, spec: AssetSpec, *, seed: int) -> SpriteBlueprint:
        character = spec.character or CharacterSpec(pose=PoseSpec(stance="side_neutral"))
        s = build_humanoid_side_skeleton(character.pose.direction)
        palette = {
            "outline": "#202020",
            "skin": "#d49a6a",
            "cloth": "#4267a8",
            "metal": "#aebcca",
            "leather": "#4c3024",
            "highlight": "#eef5ff",
        }
        torso_fill = "metal" if character.clothing.upper == "armor" or spec.archetype == "warrior" else "cloth"
        primitives = [
            SpritePrimitive(
                op="line", fill="cloth", layer="back_equipment", points=[s.shoulder_back, s.hand_back], width=5
            ),
            SpritePrimitive(op="line", fill="cloth", layer="pants", points=[s.hip, s.knee_back, s.foot_back], width=6),
            SpritePrimitive(
                op="polygon",
                fill=torso_fill,
                layer="torso",
                points=[(27, 29), (38, 30), (37, 45), (27, 44)],
            ),
            SpritePrimitive(op="ellipse", fill="skin", layer="head", bbox=(23, 7, 41, 28)),
            SpritePrimitive(op="polygon", fill="skin", layer="head", points=[(39, 14), s.nose_anchor, (39, 21)]),
            SpritePrimitive(op="line", fill="cloth", layer="arms", points=[s.shoulder_front, s.hand_front], width=5),
            SpritePrimitive(
                op="line", fill="cloth", layer="pants", points=[s.hip, s.knee_front, s.foot_front], width=6
            ),
        ]
        if spec.archetype == "warrior" or character.equipment.hand == "sword":
            sign = 1 if character.pose.direction == "right" else -1
            primitives.append(
                SpritePrimitive(
                    op="line",
                    fill="metal",
                    layer="front_equipment",
                    points=[s.hand_front, (s.hand_front[0] + sign * 12, 24)],
                    width=3,
                )
            )
        return SpriteBlueprint(
            recipe=f"humanoid_side/{spec.archetype}",
            subject=spec.subject,
            palette=palette,
            primitives=primitives,
            material_roles={"skin": "skin", "cloth": "cloth", "metal": "metal"},
            lighting_direction=character.lighting.direction,
            outline=SpriteOutlineSpec(enabled=True),
            notes=["profile skeleton", "rear limbs occluded"],
        )
