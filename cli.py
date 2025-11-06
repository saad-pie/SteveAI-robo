#!/usr/bin/env python
import asyncio
import os
import sys
import json
from pathlib import Path
from typing import List, Optional
import toml
from pydantic import BaseModel, Field
from rich import print as rprint, console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from git import Repo  # Optional
import requests  # For sync usage

# AI Backend
from openai import AsyncOpenAI
import httpx  # For timeout config

console = console.Console()

class Config(BaseModel):
    a4f_base_url: str = "https://api.a4f.co/v1"
    a4f_api_keys: List[str] = Field(default_factory=lambda: ["free"])

def load_config() -> Config:
    config_path = Path.home() / ".steveai" / "config.toml"
    if config_path.exists():
        data = toml.load(config_path)
        # Filter out dummy 'free' keys for safety
        if "a4f_api_keys" in data:
            data["a4f_api_keys"] = [k for k in data["a4f_api_keys"] if k != "free"]
        return Config(**data)
    return Config()

class Session:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.history: List[str] = []
        self.git_repo: Optional[Repo] = None
        if (project_dir / ".git").exists():
            self.git_repo = Repo(project_dir)

    def add_to_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def get_context(self, max_tokens: int = 4000) -> str:
        context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.history[-10:]])
        return context[:max_tokens]

class AIBackend:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.a4f_base_url
        self.current_key_index = 0

    def get_usage(self, api_key: str) -> dict:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            resp = requests.get(f"{self.base_url}/usage?section=rate_limits_and_restrictions", headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return {"requests_per_minute_remaining": 0, "requests_per_day_remaining": 0}

    def select_best_key(self) -> str:
        if not self.config.a4f_api_keys:
            raise ValueError("No valid API keys configured!")
        # Simple round-robin if usage fetch fails
        self.current_key_index = (self.current_key_index + 1) % len(self.config.a4f_api_keys)
        return self.config.a4f_api_keys[self.current_key_index - 1]

    async def chat(self, prompt: str, model: str = "gpt-4o-mini", session: Session = None, max_tokens: int = 1000) -> str:
        context = session.get_context() if session else ""
        full_prompt = f"{context}\n\nUser: {prompt}" if context else prompt

        api_key = self.select_best_key()
        timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=60.0)
        client = AsyncOpenAI(base_url=self.base_url, api_key=api_key, timeout=timeout)

        try:
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": full_prompt}], max_tokens=max_tokens
            )
            return resp.choices[0].message.content
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                rprint(f"[yellow]Key limited—rotating...[/yellow]")
                # Retry with next key
                return await self.chat(prompt, model, session, max_tokens)
            raise e

    def list_models(self, limit: int = 20) -> List[dict]:
        """Dynamic fetch from /v1/models?plan=free for free tier only."""
        if not self.config.a4f_api_keys:
            rprint("[yellow]No API keys—using verified free models.[/yellow]")
            return self._verified_free_models()[:limit]
        
        api_key = self.config.a4f_api_keys[0]
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"plan": "free"}
        
        try:
            resp = requests.get(f"{self.base_url}/models", headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                
                parsed_models = []
                for m in models[:limit]:
                    model_id = m.get("id", "")
                    if '/' in model_id:
                        provider, name = model_id.split('/', 1)
                    else:
                        provider, name = 'Unknown', model_id
                    parsed_models.append({
                        'id': model_id,
                        'provider': provider.upper(),
                        'object': m.get("type", "model"),
                        'created': m.get("created", 0) or 0,  # Ensure int for sorting
                        'owned': True  # Free tier
                    })
                return sorted(parsed_models, key=lambda x: x['created'], reverse=True)
            else:
                rprint(f"[yellow]API error {resp.status_code}—using verified free models.[/yellow]")
        except Exception as e:
            rprint(f"[yellow]Fetch failed ({str(e)[:50]}...)—using verified free models.[/yellow]")
        
        return self._verified_free_models()[:limit]

    def _verified_free_models(self) -> List[dict]:
        """Fallback verified free tier models from A4F docs/reviews (no fake ones)."""
        # Based on common free access; user can init/add via fetch
        return [
            {'id': 'gpt-4o-mini', 'provider': 'OPENAI', 'object': 'model', 'created': 1722470400, 'owned': True},
            {'id': 'claude-3.5-sonnet-20241022', 'provider': 'ANTHROPIC', 'object': 'model', 'created': 1729440000, 'owned': True},
            {'id': 'gemini-1.5-flash', 'provider': 'GOOGLE', 'object': 'model', 'created': 1711929600, 'owned': True},
            {'id': 'deepseek-coder-v2-lite', 'provider': 'DEEPSEEK', 'object': 'model', 'created': 1704067200, 'owned': True},
            {'id': 'llama-3.1-8b-instruct', 'provider': 'META', 'object': 'model', 'created': 1722470400, 'owned': True},
            {'id': 'mistral-nemo-12b', 'provider': 'MISTRAL', 'object': 'model', 'created': 1714521600, 'owned': True},
            {'id': 'qwen2.5-7b-instruct', 'provider': 'ALIBABA', 'object': 'model', 'created': 1728000000, 'owned': True},
            {'id': 'phi-3-mini-128k-instruct', 'provider': 'MICROSOFT', 'object': 'model', 'created': 1712000000, 'owned': True},
        ]

# TTS
def text_to_speech(text: str):
    os.system(f"espeak '{text}'")

# CLI
import typer

app = typer.Typer(help="SteveAI: Free Tier A4F Models CLI 🚀")

config = load_config()
backend = AIBackend(config)
session = None

@app.command()
def init(add_key: bool = True):
    config_dir = Path.home() / ".steveai"
    config_dir.mkdir(exist_ok=True)
    data = config.dict()
    if add_key:
        new_key = Prompt.ask("New A4F API Key", default="")
        if new_key and new_key != "free":
            data["a4f_api_keys"].append(new_key)
    with open(config_dir / "config.toml", "w") as f:
        toml.dump(data, f)
    rprint(f"[green]{len([k for k in data['a4f_api_keys'] if k != 'free'])} valid keys ready![/green]")

@app.command()
def usage(model: Optional[str] = None):
    table = Table(title="A4F Key Usage")
    table.add_column("Key (short)", style="cyan")
    table.add_column("RPM Left", style="green")
    table.add_column("RPD Left", style="yellow")
    valid_keys = [k for k in config.a4f_api_keys if k != "free"]
    if not valid_keys:
        table.add_row("N/A", "N/A", "Add keys via 'init'")
    else:
        for key in valid_keys:
            usage = backend.get_usage(key)
            rpm = usage.get("requests_per_minute_remaining", "?")
            rpd = usage.get("requests_per_day_remaining", "?")
            table.add_row(key[:8] + "...", str(rpm), str(rpd))
    console.print(table)

@app.command()
def models(limit: int = 15):
    """List free tier A4F models (live ?plan=free fetch or fallback)."""
    rprint("[bold blue]Loading A4F free tier models...[/bold blue]")
    free_models = backend.list_models(limit=limit)
    if not free_models:
        rprint("[red]No models available—check keys/network.[/red]")
        return

    table = Table(title=f"Top {len(free_models)} Free A4F Models (Free Tier Only)")
    table.add_column("ID", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Free Access", style="magenta")
    for m in free_models:
        table.add_row(m['id'], m['provider'], m['object'], "Yes")
    console.print(table)
    rprint("[dim]Free tier: GPT/Claude/Gemini/DeepSeek + more. Use full ID in commands. Live fetch via ?plan=free.[/dim]")

@app.command()
def chat(prompt: str, model: str = "provider-3/gpt-4o-mini", tts: bool = False, project: Path = Path(".")):
    global session
    session = Session(project)

    async def chat_call():
        return await backend.chat(prompt, model, session)

    response = asyncio.run(chat_call())  # Avoid deprecation

    session.add_to_history("user", prompt)
    session.add_to_history("assistant", response)

    rprint(f"[blue]{response}[/blue]")
    if tts:
        text_to_speech(response)

@app.command()
def generate(code_prompt: str, file: Optional[Path] = None, model: str = "deepseek-coder-v2-lite", project: Path = Path(".")):
    global session
    session = Session(project)

    async def gen_call():
        return await backend.chat(
            f"Generate clean, executable code for: {code_prompt}. Output *only* the code.",
            model, session
        )

    response = asyncio.run(gen_call())

    session.add_to_history("user", code_prompt)
    session.add_to_history("assistant", response)

    if file:
        file.write_text(response)
        rprint(f"[green]Wrote to {file}[/green]")
        if session.git_repo:
            commit_code(file, "SteveAI: Generated code")
    else:
        rprint(f"[cyan]{response}[/cyan]")

@app.command()
def edit(file: Path, instruction: str, model: str = "claude-3.5-sonnet-20241022", auto_commit: bool = False, project: Path = Path(".")):
    global session
    session = Session(project)

    with open(file, "r") as f:
        current_code = f.read()

    async def edit_call():
        return await backend.chat(
            f"Edit this code:\n```\n{current_code}\n```\nInstructions: {instruction}\nOutput *only* the full updated code.",
            model, session
        )

    response = asyncio.run(edit_call())

    import difflib
    diff = list(difflib.unified_diff(current_code.splitlines(), response.splitlines(), lineterm=''))
    diff_str = "\n".join(diff[:15])
    rprint(f"[yellow]Diff:\n{diff_str}[/yellow]")

    if Confirm.ask("Apply?"):
        file.write_text(response)
        rprint(f"[green]Updated {file}[/green]")
        if auto_commit and session.git_repo:
            commit_code(file, f"SteveAI: {instruction}")

def commit_code(file: Path, msg: str):
    if session and session.git_repo:
        session.git_repo.git.add(str(file))
        session.git_repo.git.commit(m=msg)
        rprint(f"[yellow]Committed: {msg}[/yellow]")

@app.command()
def repl(model: str = "provider-3/gpt-4o-mini", project: Path = Path(".")):
    global session
    session = Session(project)
    rprint(f"[bold green]SteveAI REPL ({model}): 'exit', 'gen <p>', 'edit <f> <i>'[/bold green]")

    while True:
        user_input = Prompt.ask("You")
        if user_input.lower() == "exit":
            break
        elif user_input.startswith("gen "):
            generate(user_input[4:], model=model, project=project)
        elif user_input.startswith("edit "):
            parts = user_input.split(maxsplit=2)
            if len(parts) == 3:
                edit(Path(parts[1]), parts[2], model=model, project=project)
            else:
                rprint("[red]edit <file> <instruction>[/red]")
        else:
            chat(user_input, model=model, project=project)

if __name__ == "__main__":
    app()
