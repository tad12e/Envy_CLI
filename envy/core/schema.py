import json
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model


class VariableSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "str"
    required: bool = True
    description: str = ""
    default: Any = None
    ge: Optional[float] = None
    le: Optional[float] = None
    regex: Optional[str] = None
    sensitive: bool = False


def _parse_template(template_path: Path) -> Dict[str, Any]:
    variables: Dict[str, Any] = {}
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        value_part = raw_value.strip()
        description = ""
        if "#" in value_part:
            value_part, comment = value_part.split("#", 1)
            description = comment.strip()
        value_part = value_part.strip()

        required = value_part == ""
        default = None if required else value_part
        variables[key] = {
            "type": "str",
            "required": required,
            "default": default,
            "description": description,
            "sensitive": False,
        }
    return {"variables": variables}


def load_schema_definition(schema_file: Optional[Path], required: bool = True) -> Optional[Dict[str, Any]]:
    candidates = []
    if schema_file is not None:
        candidates.append(schema_file)
    else:
        candidates.extend([Path("envy.schema.json"), Path(".env.template")])

    selected: Optional[Path] = None
    for candidate in candidates:
        if candidate.exists():
            selected = candidate
            break

    if selected is None:
        if required:
            raise FileNotFoundError("No schema found. Expected envy.schema.json or .env.template.")
        return None

    if selected.suffix.lower() == ".json":
        payload = json.loads(selected.read_text(encoding="utf-8"))
        if "variables" not in payload or not isinstance(payload["variables"], dict):
            raise ValueError("Schema file must include a 'variables' object.")
        return payload

    return _parse_template(selected)


def _build_dynamic_model(schema: Dict[str, Any]) -> type[BaseModel]:
    model_fields = {}
    variables = schema.get("variables", {})

    for key, raw_spec in variables.items():
        spec = VariableSpec.model_validate(raw_spec)

        field_type: Any = str
        if spec.type == "int":
            field_type = int
        elif spec.type == "float":
            field_type = float
        elif spec.type == "bool":
            field_type = bool

        annotation = field_type if spec.required and spec.default is None else Optional[field_type]

        field_kwargs: Dict[str, Any] = {"description": spec.description}
        if spec.ge is not None:
            field_kwargs["ge"] = spec.ge
        if spec.le is not None:
            field_kwargs["le"] = spec.le
        if spec.regex is not None:
            field_kwargs["pattern"] = spec.regex

        default_value = ... if spec.required and spec.default is None else spec.default
        model_fields[key] = (annotation, Field(default_value, **field_kwargs))

    return create_model("EnvSchemaModel", **model_fields)


def validate_env_file(env_file: Path, schema: Dict[str, Any]) -> Dict[str, Any]:
    if not env_file.exists():
        return {"ok": False, "issues": [f"Missing env file: {env_file}"]}

    values = dict(dotenv_values(env_file))
    
    # Use the Pydantic model logic you already built!
    model_cls = _build_dynamic_model(schema)
    
    try:
        model_cls.model_validate(values)
        return {"ok": True, "issues": []}
    except ValidationError as exc:
        issues = []
        for error in exc.errors():
            # Format Pydantic errors into readable strings
            loc = " -> ".join(str(e) for e in error["loc"])
            issues.append(f"{loc}: {error['msg']}")
        return {"ok": False, "issues": issues}