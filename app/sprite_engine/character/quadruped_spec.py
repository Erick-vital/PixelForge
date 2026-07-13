from typing import Literal

from pydantic import BaseModel, ConfigDict


class QuadrupedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_length: Literal["short", "average", "long"] = "average"
    body_depth: Literal["slim", "average", "heavy"] = "average"
    leg_length: Literal["short", "average", "long"] = "average"
    head_shape: Literal["round", "wedge"] = "round"
    snout_length: Literal["short", "average", "long"] = "short"
    ear_shape: Literal["floppy", "triangular", "upright"] = "triangular"
    tail_shape: Literal["curly", "straight", "bushy"] = "curly"
    pose: Literal["side_neutral"] = "side_neutral"
    direction: Literal["left", "right"] = "right"
