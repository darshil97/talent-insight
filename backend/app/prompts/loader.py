"""Render packaged Markdown prompts with Jinja; missing templates or variables fail loudly."""

from jinja2 import Environment, PackageLoader, StrictUndefined

_environment = Environment(
    loader=PackageLoader("app", "prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    # Keep each partial's final newline so included lines do not run together.
    keep_trailing_newline=True,
)


def load_prompt(category: str, name: str, **context: object) -> str:
    """Render `prompts/<category>/<name>.md` with the given variables."""
    template = _environment.get_template(f"{category}/{name.removesuffix('.md')}.md")
    return template.render(**context).strip()
