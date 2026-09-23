#!/usr/bin/env python3
"""Sample and freeze one BPO repair trace for a configured workload."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
KEY_FILE = REPO / "deepseekAPI"
TOOLS = [
    {"type": "function", "function": {"name": "run_shell", "description": "Run one shell action in /testbed and inspect its output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "finish_segment", "description": "Finish this segment when its goal is complete.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]


def api_call(messages: list[dict], key: str) -> dict:
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({"model": "deepseek-chat", "messages": messages, "tools": TOOLS,
                         "tool_choice": "auto", "temperature": 0.7, "max_tokens": 1400}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)["choices"][0]["message"]


def docker(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def run_command(container: str, command: str) -> tuple[int, str]:
    forbidden = ("pip install", "conda install", "apt-get", "curl ", "wget ", "git fetch", "git pull")
    if any(item in command for item in forbidden):
        return 125, "command forbidden by experiment protocol"
    try:
        result = docker("exec", "--workdir", "/testbed", container, "bash", "-o", "pipefail", "-c", command, timeout=600)
        return result.returncode, result.stdout[-12000:]
    except subprocess.TimeoutExpired:
        return 124, "command exceeded 600 s"


def replay_command(command: str) -> str:
    if "\n" not in command and "\t" not in command:
        return command
    encoded = base64.b64encode(command.encode()).decode()
    return f"printf '%s' '{encoded}' | base64 -d | bash -o pipefail"


def save_segment(workload: Path, segment: str, actions: list[dict]) -> None:
    target = workload / "segments" / segment / "actions.tsv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        handle.write("step\tsha256\tcommand\n")
        for index, item in enumerate(actions, 1):
            command = replay_command(item["command"])
            handle.write(f"{index:03}\t{hashlib.sha256(command.encode()).hexdigest()}\t{command}\n")


def sample_segment(workload: Path, container: str, stage: dict, messages: list[dict],
                   key: str, transcript: list[dict]) -> None:
    role, segment, goal, budget = (stage[key] for key in ("role", "segment", "goal", "budget"))
    messages.append({"role": "user", "content":
                     f"Segment {segment} ({role}). Goal: {goal} Use at least 2 meaningful run_shell actions, "
                     f"then finish_segment. Maximum {budget} run_shell calls."})
    actions: list[dict] = []
    segment_messages: list[dict] = []
    for _ in range(budget + 3):
        message = api_call(messages, key)
        messages.append(message)
        segment_messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            messages.append({"role": "user", "content": "Use run_shell or finish_segment now."})
            continue
        done = False
        for item in calls:
            name = item["function"]["name"]
            arguments = json.loads(item["function"]["arguments"])
            if name == "finish_segment":
                result = arguments.get("summary", "finished")
                done = True
            elif name == "run_shell" and len(actions) < budget:
                command = arguments["command"]
                status, output = run_command(container, command)
                actions.append({"command": command, "exit_code": status, "output": output})
                print(f"{role}/{segment} {len(actions)}/{budget}: exit {status}: {command[:150]}", flush=True)
                result = f"exit_code={status}\n{output[-6000:]}"
            else:
                result = "action budget exhausted; finish this segment"
            tool_message = {"role": "tool", "tool_call_id": item["id"], "content": result}
            messages.append(tool_message)
            segment_messages.append(tool_message)
        if done and len(actions) >= 2:
            break
        if len(actions) >= budget:
            break
    if len(actions) < 2:
        raise RuntimeError(f"too few tool actions sampled for {role}/{segment}")
    save_segment(workload, segment, actions)
    transcript.append({"role": role, "segment": segment, "goal": goal,
                       "actions": actions, "conversation": segment_messages})


def start_container(name: str, image: str) -> None:
    result = docker("run", "-d", "--name", name, "--network", "none", "--workdir", "/testbed",
                    "--entrypoint", "sleep", image, "infinity")
    if result.returncode:
        raise RuntimeError(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workload", type=Path)
    args = parser.parse_args()
    workload = args.workload.resolve()
    task = json.loads((workload / "task.json").read_text())
    if (workload / "agent-sampling.json").exists():
        raise RuntimeError("sample already frozen; remove only if intentionally resampling")
    stages = task["stages"]
    backbone_stages = [stage for stage in stages if stage["role"] == "backbone"]
    if len(backbone_stages) != 5:
        raise RuntimeError("expected five backbone stages")
    by_role = {role: [stage for stage in stages if stage["role"] == role]
               for role in ("early_1", "early_2", "early_3", "late_1", "late_2", "late_3")}
    if any(len(items) != 2 for items in by_role.values()):
        raise RuntimeError("each branch must have two stages")
    rollouts = {"backbone": [stage["segment"] for stage in backbone_stages]}
    for role, items in by_role.items():
        prefix = backbone_stages[:2] if role.startswith("early") else backbone_stages[:4]
        rollouts[role] = [stage["segment"] for stage in prefix + items]

    key = KEY_FILE.read_text().strip()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stem = task["instance_id"].replace("__", "-").lower()
    backbone = f"mixfs-exp5-sample-{stem}-{stamp}"
    early_image = f"mixfs-exp5-sample-{stem}-early:{stamp.lower()}"
    late_image = f"mixfs-exp5-sample-{stem}-late:{stamp.lower()}"
    containers: list[str] = [backbone]
    transcript: list[dict] = []
    messages = [{"role": "system", "content": task["system_prompt"]}]
    early_messages: list[dict] = []
    late_messages: list[dict] = []
    start_container(backbone, task["source_image"])
    try:
        for stage in backbone_stages[:2]:
            sample_segment(workload, backbone, stage, messages, key, transcript)
        early_messages = json.loads(json.dumps(messages))
        result = docker("commit", backbone, early_image, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stdout)
        for stage in backbone_stages[2:4]:
            sample_segment(workload, backbone, stage, messages, key, transcript)
        late_messages = json.loads(json.dumps(messages))
        result = docker("commit", backbone, late_image, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stdout)
        sample_segment(workload, backbone, backbone_stages[4], messages, key, transcript)
        for role, branch_stages in by_role.items():
            container = f"{backbone}-{role}"
            containers.append(container)
            start_container(container, early_image if role.startswith("early") else late_image)
            branch_messages = json.loads(json.dumps(early_messages if role.startswith("early") else late_messages))
            branch_messages.append({"role": "user", "content":
                                    f"You are continuation {role} from a saved checkpoint. Investigate its assigned facet independently."})
            for stage in branch_stages:
                sample_segment(workload, container, stage, branch_messages, key, transcript)
        (workload / "rollouts.json").write_text(json.dumps(rollouts, indent=2) + "\n")
        (workload / "agent-sampling.json").write_text(json.dumps({
            "model": "deepseek-chat", "sampled_at_utc": stamp,
            "source_image": task["source_image"], "task": task["instance_id"],
            "api": "chat/completions tool calls",
            "sampling": "one adaptive backbone and six checkpoint continuations",
            "segments": transcript,
        }, indent=2) + "\n")
    finally:
        for container in reversed(containers):
            docker("rm", "-f", container)
        docker("image", "rm", "-f", early_image)
        docker("image", "rm", "-f", late_image)


if __name__ == "__main__":
    main()
