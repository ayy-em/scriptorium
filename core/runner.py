from core.registry import discover


def run(script_key: str) -> None:
    scripts = discover()
    if script_key not in scripts:
        available = ", ".join(sorted(scripts)) or "none"
        raise KeyError(f"Unknown script {script_key!r}. Available: {available}")
    scripts[script_key].run()
