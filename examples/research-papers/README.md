# Example: Research papers shelf

You've collected 200 PDFs from arXiv / NeurIPS / your favourite preprint server, and Claude's chat-project upload limit isn't going to cover them. Make a shelf instead.

## Setup

```python
from docshelf_mcp import Shelf

shelf = Shelf("~/Documents/papers").init(
    name="Research Papers",
    remote="https://github.com/me/papers",
    default_categories=[
        "diffusion",
        "transformers",
        "rl",
        "interpretability",
        "agents",
        "evaluation",
    ],
)
```

## Adding papers

For dense academic PDFs, use `quality="high"` if you can afford the marker-pdf install — it preserves equations and tables much better than the fast path.

```python
shelf.add_document(
    "papers/attention-is-all-you-need.pdf",
    category="transformers",
    title="Attention is all you need",
    description="Vaswani et al., 2017. Foundational transformer paper.",
    quality="high",  # requires `pip install docshelf-mcp[high-quality]`
)

shelf.add_document(
    "papers/ddpm.pdf",
    category="diffusion",
    title="Denoising Diffusion Probabilistic Models",
    description="Ho et al., 2020. DDPM training objective.",
    quality="fast",  # default; pymupdf4llm — requires `pip install docshelf-mcp[pdf]`
)
```

## Use the description aggressively

For papers, the description is the *abstract*. Stuff it with keywords; the model reads it before deciding which paper to fetch:

```python
shelf.add_document(
    "papers/rlhf.pdf",
    category="rl",
    title="Deep RL from human preferences",
    description=(
        "Christiano et al., 2017. Train an agent from pairwise human comparisons. "
        "Reward model learned from preference labels. Atari + simulated robotics. "
        "Precursor to RLHF for language models."
    ),
)
```

When you ask "what's the original paper on learning rewards from human preferences?", Claude finds it from the description alone — no PDF fetch needed.

## Then

Push to GitHub, attach `INDEX.md` to a Claude project, and ask:

- "Summarise the key insight of the DDPM paper."
- "Which paper introduced the RLHF technique used in InstructGPT?"
- "Compare the loss function in DDPM and DDIM."

Claude will fetch only the section it needs (e.g. `003-method.md`) instead of swallowing a 30-page PDF.
