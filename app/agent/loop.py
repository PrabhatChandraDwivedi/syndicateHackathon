import json
import re
import ast
from dataclasses import dataclass
from typing import List

from app.harness.tools import ToolRegistry, ToolCall, ToolError
from app.harness.modelrouter import ModelRouter
from app.harness.tracing import span, child_span, detect, event, flush

MAX_STEPS_DEFAULT = 10


@dataclass
class Step:
    n: int
    thought: str
    tool: str | None
    args: dict
    observation: dict | None
    error: str | None


def build_system_prompt(registry: ToolRegistry, goal: str) -> str:
    lines: List[str] = [
        "You are a reconciliation agent.",
        f"Goal: {goal}",
        "The OUTPUT CONTRACT is a single JSON object and nothing else: "
        '{"thought": "...", "tool": "<tool name>", "args": {...}} '
        'or, when finished, '
        '{"thought": "...", "done": true, "summary": "..."}',
        "Available tools:",
        registry.describe(),
    ]
    return "\n".join(lines)


def parse_action(text: str) -> dict:
    m = re.search(r'\{.*\}', text, flags=re.S)
    if not m:
        return {
            'thought': '',
            'tool': None,
            'args': {},
            'done': False,
            'summary': '',
            'parse_error': 'unparseable agent response',
        }
    block = m.group(0)
    obj = None
    try:
        obj = json.loads(block)
    except Exception:
        try:
            obj = ast.literal_eval(block)
        except Exception:
            return {
                'thought': '',
                'tool': None,
                'args': {},
                'done': False,
                'summary': '',
                'parse_error': 'unparseable agent response',
            }

    if not isinstance(obj, dict):
        return {
            'thought': '',
            'tool': None,
            'args': {},
            'done': False,
            'summary': '',
            'parse_error': 'unparseable agent response',
        }

    thought = obj.get('thought', '')
    tool = obj.get('tool')
    args = obj.get('args', {})
    if not isinstance(args, dict):
        args = {}
    done = bool(obj.get('done', False))
    summary = obj.get('summary', '')

    # Coerce defensively
    if not isinstance(thought, str):
        thought = '' if thought is None else str(thought)

    if tool is not None and not isinstance(tool, str):
        tool = str(tool)

    return {'thought': thought, 'tool': tool, 'args': args, 'done': done, 'summary': summary}


class ReconciliationAgent:
    def __init__(self, registry: ToolRegistry, router: ModelRouter | None = None, max_steps: int = MAX_STEPS_DEFAULT):
        self.registry = registry
        self.router = router
        self.max_steps = max_steps

    @span('agent_run', kind='WORKFLOW')
    def run(self, goal: str, context: dict | None = None) -> dict:
        steps: List[Step] = []
        parse_error_streak = 0
        tool_calls = 0
        completed = False
        stopped_reason = ''
        final_summary = ''

        if context is None:
            context = {}

        for i in range(1, self.max_steps + 1):
            with child_span(name=f'agent_step_{i}', kind='AGENT'):
                system_prompt = build_system_prompt(self.registry, goal)
                transcript_parts: List[str] = []
                for s in steps:
                    transcript_parts.append(
                        f"Step {s.n}: thought={s.thought}, tool={s.tool}, args={s.args}, error={s.error}, observation={s.observation}"
                    )
                transcript = "\n".join(transcript_parts)

                context_json = json.dumps(context) if isinstance(context, dict) else "{}"
                prompt = system_prompt
                if transcript:
                    prompt += "\nTranscript:\n" + transcript
                prompt += "\nContext: " + context_json

                if self.router is None:
                    stopped_reason = 'no_router'
                    completed = False
                    break

                try:
                    resp = self.router.complete(prompt, max_tokens=1000)
                except Exception as e:
                    stopped_reason = 'router_error'
                    completed = False
                    detect('model call failed', step=i, error=str(e))
                    break

                text = resp.get('text', '') if isinstance(resp, dict) else ''
                action = parse_action(text)

                thought = action.get('thought', '') if isinstance(action, dict) else ''
                thought_trunc = thought[:200] if isinstance(thought, str) else ''
                tool_name = action.get('tool')
                event('agent step', step=i, tool=tool_name, thought=thought_trunc)

                if 'parse_error' in action:
                    steps.append(
                        Step(
                            n=i,
                            thought=action.get('thought', ''),
                            tool=action.get('tool'),
                            args=action.get('args', {}),
                            observation=None,
                            error=action.get('parse_error'),
                        )
                    )
                    parse_error_streak += 1
                    if parse_error_streak >= 2:
                        stopped_reason = 'parse_failures'
                        completed = False
                        break
                    # After a parse error, continue to next iteration
                    detect('agent response unparseable', step=i)
                    continue

                parse_error_streak = 0

                if action.get('done', False):
                    steps.append(
                        Step(
                            n=i,
                            thought=action.get('thought', ''),
                            tool=None,
                            args=action.get('args', {}),
                            observation=None,
                            error=None,
                        )
                    )
                    completed = True
                    stopped_reason = 'done'
                    final_summary = action.get('summary', '')
                    break

                tool_name = action.get('tool')
                tool_args = action.get('args', {})
                step = Step(n=i, thought=action.get('thought', ''), tool=tool_name, args=tool_args, observation=None, error=None)
                steps.append(step)

                if tool_name is None:
                    # No tool to call; proceed to next iteration
                    continue

                tool_calls += 1
                call = self.registry.call(tool_name, tool_args)
                if call.ok:
                    step.observation = call.result
                else:
                    step.observation = {'error': call.error}
                    step.error = call.error
                    # Ensure the tool field remains the requested tool name even on failure
                    step.tool = tool_name

                # After a tool call, proceed to next iteration
                # If this was the last allowed step, fall through to max_steps
                if i == self.max_steps:
                    stopped_reason = 'max_steps'
                    completed = False
                    detect('agent hit max steps without finishing', steps=self.max_steps)
                    break
        else:
            stopped_reason = 'max_steps'
            completed = False

        result = {
            'goal': goal,
            'completed': completed,
            'summary': final_summary,
            'steps': [
                {
                    'n': s.n,
                    'thought': s.thought,
                    'tool': s.tool,
                    'args': s.args,
                    'observation': s.observation,
                    'error': s.error,
                }
                for s in steps
            ],
            'step_count': len(steps),
            'tool_calls': tool_calls,
            'stopped_reason': stopped_reason,
        }

        if completed:
            summary_trunc = final_summary[:200] if isinstance(final_summary, str) else ''
            event('agent completed', steps=len(steps), tool_calls=tool_calls, summary=summary_trunc)

        try:
            flush()
        except Exception:
            pass
        return result
