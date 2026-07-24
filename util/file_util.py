from pathlib import Path

# 往上兩層到專案根目錄
BASE_DIR = Path(__file__).parent.parent


def load_prompt(name: str, **kwargs) -> tuple[str, str]:
    prompt_template = (BASE_DIR / "prompts" / f"{name}.txt").read_text(encoding="utf-8")

    system = ""
    prompt = prompt_template

    if "# system instruction" in prompt_template and "# prompt" in prompt_template:
        parts = prompt_template.split("# prompt", 1)
        system = parts[0].replace("# system instruction", "").strip()
        prompt = parts[1].strip()

    return system, prompt.format(**kwargs)


def load_character_content(character: str, name: str):
    path = BASE_DIR / "data" / character / f"{name}.txt"
    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8").strip()


def load_all_scenarios(character: str):
    scenario_dir = BASE_DIR / "data" / character / "scenarios"

    if not scenario_dir.exists():
        return ""

    contents = []
    for file in sorted(scenario_dir.glob("*.txt")):
        contents.append(file.read_text(encoding="utf-8"))

    return "\n\n".join(contents)


def write_debug_file(content: str, timestamp: str, name: str = "prompt_log"):
    path = BASE_DIR / "data" / "debug_log" / f"{timestamp}" / f"{name}.log"
    # 路徑不存在就新建
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(mode="a", encoding="utf-8") as f:
        f.write(content)


def write_response(content: str, timestamp: str, name: str = "response"):
    path = BASE_DIR / "data" / "api_response" / f"{timestamp}" / f"{name}.txt"
    # 路徑不存在就新建
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
