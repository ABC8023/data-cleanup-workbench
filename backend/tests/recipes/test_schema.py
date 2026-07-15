from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from data_workbench.domain.recipe import (
    CastNumberStep,
    NormalizeTextStep,
    ParseDateStep,
    Recipe,
    RenameColumnStep,
    ReplaceValueStep,
)

SOURCE = "a" * 43


def test_recipe_rejects_unknown_operation_and_arbitrary_expression() -> None:
    with pytest.raises(ValidationError):
        Recipe.model_validate(
            {
                "recipe_version": 1,
                "source_fingerprint": SOURCE,
                "steps": [{"operation": "python", "code": "open('x')"}],
            }
        )
    with pytest.raises(ValidationError):
        Recipe.model_validate(
            {
                "recipe_version": 1,
                "source_fingerprint": SOURCE,
                "steps": [
                    {
                        "id": "n",
                        "operation": "normalize_text",
                        "columns": ["name"],
                        "on_error": "preserve",
                        "expression": "1; DROP TABLE data",
                    }
                ],
            }
        )


def test_duplicate_step_ids_fail() -> None:
    step = NormalizeTextStep(id="same", columns=["name"], on_error="preserve")
    with pytest.raises(ValidationError, match="unique"):
        Recipe(source_fingerprint=SOURCE, steps=[step, step])


def test_rename_requires_exactly_one_column() -> None:
    with pytest.raises(ValidationError, match="exactly one column"):
        RenameColumnStep(
            id="r", columns=["a", "b"], on_error="preserve", new_name="c"
        )


def test_parse_date_requires_formats() -> None:
    with pytest.raises(ValidationError):
        ParseDateStep(id="d", columns=["a"], on_error="preserve", formats=[])


def test_recipe_yaml_round_trip_preserves_model_and_order() -> None:
    recipe = Recipe(
        source_fingerprint=SOURCE,
        steps=[
            NormalizeTextStep(
                id="n", columns=["currency", "name"], case="upper", on_error="preserve"
            ),
            ReplaceValueStep(
                id="r", columns=["name"], old="N/A", new=None, on_error="preserve"
            ),
            CastNumberStep(
                id="c", columns=["amount"], target="decimal", on_error="quarantine"
            ),
        ],
    )

    encoded = yaml.safe_dump(recipe.model_dump(mode="json"), sort_keys=False)
    decoded = Recipe.model_validate(yaml.safe_load(encoded))

    assert decoded == recipe
    assert [step.id for step in decoded.steps] == ["n", "r", "c"]
    assert decoded.steps[0].columns == ["currency", "name"]
