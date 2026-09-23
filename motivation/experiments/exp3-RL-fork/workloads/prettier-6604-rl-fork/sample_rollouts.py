#!/usr/bin/env python3
"""Sample one adaptive code-repair trajectory and six BPO continuations.

The model sees real command output from an isolated copy of the pinned Prettier
image. The resulting commands and API conversation are frozen before the VM
comparison. No API key is written to the trace.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from plan import ROLLOUTS

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[4]
KEY_FILE = REPO / "deepseekAPI"
IMAGE = "mixfs/prettier-6604:exp2"
SYSTEM = """You are a code-repair agent working inside the pinned Prettier 1.18.2 repository at /testbed.
The real task is prettier/prettier#6603: formatting double-parenthesized TypeScript types can change semantics. Examples:
type C = ((number | string))[\"toString\"]; must remain (number | string)[\"toString\"];
type D = ((keyof T1))[\"foo\"]; must retain grouping around keyof T1;
conditional and intersection types also need correct grouping.
Use run_shell to inspect, edit, and check the repository, then finish_segment. You receive command output after each call.
Work like a normal repair agent: inspect relevant files, make a focused change, and run small checks. Never run npm/yarn install, npm/yarn build, full Jest suite, network commands, or synthetic file/page scans. Prefer rg/sed, the source CLI, and a focused Jest file. Commands run with bash in /testbed. A failing command is allowed and will be recorded. Do not touch Dockerfile or package.json. Do not use the issue's historical PR patch; solve from the checked-out code."""
TOOLS = [
    {"type": "function", "function": {"name": "run_shell", "description": "Run one shell action inside the isolated Prettier repository and inspect its output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "finish_segment", "description": "Finish the current segment when its goal is done or the action budget is exhausted.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]
STAGES = [
    ("backbone", "read_repo", "Inspect repository structure, task-specific tests, and reproduce the reported bug. Do not edit yet.", 5),
    ("backbone", "read_typescript", "Trace the TypeScript parser/printer logic and inspect nearby test conventions. Do not edit yet.", 6),
    ("backbone", "core_patch", "Implement a focused fix for the reported TypeScript grouping bug. Add a regression test if appropriate.", 7),
    ("backbone", "core_verify", "Check the candidate with direct CLI reproductions and a focused Jest test. Fix any resulting problem using small edits. No full build.", 6),
    ("backbone", "backbone_finish", "Review the patch and run final small checks; improve coverage for one edge case if needed.", 5),
    ("early_1", "early_inspect", "At the early checkpoint, independently inspect the union/intersection precedence path and reproduce it.", 4),
    ("early_1", "early_1", "Try a repair for union/intersection indexed access and test it locally.", 6),
    ("early_2", "early_inspect", "At the early checkpoint, independently inspect conditional type precedence and reproduce it.", 4),
    ("early_2", "early_2", "Try a repair for conditional type grouping and test it locally.", 6),
    ("early_3", "early_inspect", "At the early checkpoint, independently inspect keyof indexed access and reproduce it.", 4),
    ("early_3", "early_3", "Try a repair for keyof indexed access and test it locally.", 6),
    ("late_1", "late_inspect", "At the later candidate checkpoint, inspect remaining nested union/intersection behavior.", 4),
    ("late_1", "late_1", "Improve or verify nested union/intersection coverage with a focused regression and test.", 5),
    ("late_2", "late_inspect", "At the later candidate checkpoint, inspect conditional types in indexed access.", 4),
    ("late_2", "late_2", "Improve or verify conditional coverage with a focused regression and test.", 5),
    ("late_3", "late_inspect", "At the later candidate checkpoint, inspect keyof types in indexed access.", 4),
    ("late_3", "late_3", "Improve or verify keyof coverage with a focused regression and test.", 5),
]


def call(messages: list[dict], key: str) -> dict:
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({"model": "deepseek-chat", "messages": messages, "tools": TOOLS,
                         "tool_choice": "auto", "temperature": 0.7, "max_tokens": 1200}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["choices"][0]["message"]


def docker(*args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def run_command(container: str, command: str) -> tuple[int, str]:
    try:
        result = docker("exec", "--workdir", "/testbed", container, "bash", "-o", "pipefail", "-c", command, timeout=180)
        return result.returncode, result.stdout[-10000:]
    except subprocess.TimeoutExpired:
        return 124, "command exceeded 180 s"


def replay_command(command: str) -> str:
    if "\n" not in command and "\t" not in command:
        return command
    encoded = base64.b64encode(command.encode()).decode()
    return f"printf '%s' '{encoded}' | base64 -d | bash -o pipefail"


def save_segment(segment: str, actions: list[dict]) -> None:
    target = ROOT / "segments" / segment / "actions.tsv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        handle.write("step\tsha256\tcommand\n")
        for index, item in enumerate(actions, 1):
            command = replay_command(item["command"])
            handle.write(f"{index:03}\t{hashlib.sha256(command.encode()).hexdigest()}\t{command}\n")


def sample_segment(container: str, role: str, segment: str, goal: str, budget: int,
                   messages: list[dict], key: str, transcript: list[dict]) -> list[dict]:
    messages.append({"role": "user", "content": f"Segment {segment} ({role}). Goal: {goal} Use at least 2 meaningful tool actions, then finish_segment. Maximum {budget} run_shell calls."})
    actions: list[dict] = []
    for index in range(budget + 2):
        message = call(messages, key)
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            messages.append({"role": "user", "content": "Use run_shell or finish_segment now."})
            continue
        done = False
        for item in tool_calls:
            name = item["function"]["name"]
            arguments = json.loads(item["function"]["arguments"])
            if name == "finish_segment":
                result = arguments.get("summary", "finished")
                done = True
            elif name == "run_shell" and len(actions) < budget:
                command = arguments["command"]
                if any(x in command for x in ("npm run build", "yarn build", "npm install", "yarn install", "curl ", "wget ")):
                    status, output = 125, "command forbidden by experiment protocol"
                else:
                    status, output = run_command(container, command)
                    actions.append({"command": command, "exit_code": status, "output": output})
                    print(f"{role}/{segment} {len(actions)}/{budget}: exit {status}: {command[:130]}", flush=True)
                result = f"exit_code={status}\n{output[-5000:]}"
            else:
                result = "action budget exhausted; finish this segment"
            messages.append({"role": "tool", "tool_call_id": item["id"], "content": result})
        if done and len(actions) >= 2:
            break
        if len(actions) >= budget:
            break
    if not actions:
        raise RuntimeError(f"no tool actions sampled for {role}/{segment}")
    save_segment(segment, actions)
    transcript.append({"role": role, "segment": segment, "actions": actions,
                       "conversation": messages[-(2 * budget + 5):]})
    return messages


def start_container(name: str, image: str) -> None:
    result = docker("run", "-d", "--name", name, "--network", "none", "--workdir", "/testbed", image, "sleep", "infinity")
    if result.returncode:
        raise RuntimeError(result.stdout)


def main() -> None:
    if (ROOT / "agent-sampling.json").exists():
        raise RuntimeError("sample already frozen; archive it before starting a new sample")
    key = KEY_FILE.read_text().strip()
    if not key:
        raise RuntimeError("DeepSeek API key file is empty")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backbone = f"mixfs-exp5-agent-{stamp}"
    early_image = f"mixfs-exp5-early:{stamp.lower()}"
    late_image = f"mixfs-exp5-late:{stamp.lower()}"
    early_messages = late_messages = []
    transcript: list[dict] = []
    containers = [backbone]
    start_container(backbone, IMAGE)
    messages = [{"role": "system", "content": SYSTEM}]
    try:
        for role, segment, goal, budget in STAGES[:2]:
            sample_segment(backbone, role, segment, goal, budget, messages, key, transcript)
        early_messages = json.loads(json.dumps(messages))
        result = docker("commit", backbone, early_image, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stdout)
        for role, segment, goal, budget in STAGES[2:4]:
            sample_segment(backbone, role, segment, goal, budget, messages, key, transcript)
        late_messages = json.loads(json.dumps(messages))
        result = docker("commit", backbone, late_image, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stdout)
        role, segment, goal, budget = STAGES[4]
        sample_segment(backbone, role, segment, goal, budget, messages, key, transcript)
        for role in ("early_1", "early_2", "early_3", "late_1", "late_2", "late_3"):
            container = f"{backbone}-{role}"
            containers.append(container)
            start_container(container, early_image if role.startswith("early") else late_image)
            branch_messages = json.loads(json.dumps(early_messages if role.startswith("early") else late_messages))
            branch_messages.append({"role": "user", "content": f"You are continuation {role} from a saved checkpoint. Explore the specified edge case independently."})
            for item_role, item_segment, item_goal, item_budget in STAGES:
                if item_role == role:
                    sample_segment(container, role, item_segment, item_goal, item_budget, branch_messages, key, transcript)
        (ROOT / "rollouts.json").write_text(json.dumps(ROLLOUTS, indent=2) + "\n")
        (ROOT / "agent-sampling.json").write_text(json.dumps({
            "model": "deepseek-chat", "sampled_at_utc": stamp, "source_image": IMAGE,
            "task": "prettier/prettier#6603", "api": "chat/completions tool calls",
            "sampling": "one adaptive backbone and six checkpoint continuations",
            "segments": transcript,
        }, indent=2) + "\n")
        print("sampled all seven paths", flush=True)
    finally:
        for container in containers:
            docker("rm", "-f", container)


if __name__ == "__main__":
    main()
