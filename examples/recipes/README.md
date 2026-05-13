# Example: Recipes shelf

A cookbook for your kitchen — one recipe per Markdown file, organised by category (mains, sides, desserts, …).

## Setup

```python
from docshelf_mcp import Shelf

shelf = Shelf("~/Documents/recipes").init(
    name="My Recipes",
    remote="https://github.com/me/recipes",
    default_categories=[
        "breakfast",
        "lunch",
        "dinner",
        "sides",
        "desserts",
        "drinks",
        "sauces",
    ],
)
```

## Adding recipes

Recipes are small enough that splitting is off by default for the .md case.

```python
shelf.add_document(
    "drafts/sourdough.md",
    category="breakfast",
    title="Sourdough bread",
    description="Three-day cold-ferment loaf, 80% hydration.",
    split=False,
)

shelf.add_document(
    "drafts/dal-tadka.md",
    category="dinner",
    title="Dal tadka",
    description="Yellow lentils with cumin/garlic tempering. 30 min total.",
    split=False,
)
```

## Why this works for cooking

The model loves explicit ingredient lists. INDEX.md gives Claude an at-a-glance map; when you ask "what's a quick lentil dinner I can make in under an hour?", it scans the descriptions and pulls only the relevant recipe.

You can also batch-ingest existing Markdown notes:

```python
from pathlib import Path

for md in Path("~/Notes/recipes/dinner").expanduser().glob("*.md"):
    first_line = md.read_text().splitlines()[0].lstrip("# ").strip()
    shelf.add_document(md, category="dinner", title=first_line, split=False)
```

## Tips

- Tag with a `description` like `"vegan, 20 min, one pot"` — the model uses descriptions heavily.
- Keep recipe files short. If you're consistently > 50 KB per recipe, you're writing a book, not a recipe.
- Use the `sauces` category for things you keep referring to ("the chimichurri from last week") — descriptions make them discoverable.
