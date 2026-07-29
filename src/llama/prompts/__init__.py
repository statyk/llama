from importlib import resources


def load_prompt(name: str) -> str:
    return resources.files("llama.prompts").joinpath(f"{name}.md").read_text()
