#!/usr/bin/env python3
"""Generate and verify pytest tests with DSH. Run only inside an isolated sandbox."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

MAX_SOURCE = 100_000
MAX_LOG = 16_000
MAX_TEST = 100_000
REPORT_PLUGIN = '''import json
import os

passed = 0
def pytest_runtest_logreport(report):
    global passed
    if report.when == "call" and report.passed and not hasattr(report, "wasxfail"):
        passed += 1

def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["ORCH_PYTEST_REPORT"], "w", encoding="utf-8") as output:
        json.dump({"passed": passed}, output)
'''


def clipped(text, limit=MAX_LOG):
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def signal_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def dsh_final(stdout):
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "final":
            return event
    return {}


def dsh_error(final):
    allowed = {"AUTH", "MISSING_CREDENTIAL", "UNKNOWN_MODEL", "TRANSPORT", "UNSUPPORTED_REASONING_EFFORT"}
    reason = final.get("reason")
    error = reason.get("error") if isinstance(reason, dict) and reason.get("kind") == "error" else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if code in allowed else None


def passed_count(report):
    data = json.loads(report.read_text(encoding="utf-8"))
    count = data.get("passed") if isinstance(data, dict) else None
    if type(count) is not int or count < 0:
        raise ValueError("invalid pytest passed count")
    return count


def run_process(argv, cwd, env, deadline, stdout_json=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out, tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            signal_group(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                signal_group(process.pid, signal.SIGKILL)
                process.wait()
            raise TimeoutError
        finally:
            # The CLI may leave background subprocesses after it exits.
            signal_group(process.pid, signal.SIGKILL)
        out.seek(0)
        err.seek(0)
        if stdout_json:
            final = {}
            for line in out:
                event = dsh_final(line)
                if event:
                    reason = event.get("reason")
                    text = event.get("text")
                    final = {"type": "final", "reason": reason, "text": clipped(text) if isinstance(text, str) else ""}
            stdout = json.dumps(final, ensure_ascii=False)
        else:
            stdout = clipped(out.read(MAX_LOG + 1))
        return process.returncode, stdout, clipped(err.read(MAX_LOG + 1))


def make_patch(url, model):
    # JSON scalars are valid YAML scalars and avoid interpolation into YAML syntax.
    q = lambda value: json.dumps(value, ensure_ascii=False)
    return ("- id: llm-pi-ai\n  config:\n    providers:\n      nosana:\n"
            "        apiKeyEnv: NOSANA_API_KEY\n        api: openai-completions\n"
            f"        baseURL: {q(url)}\n        models:\n          - id: {q(model)}\n"
            "- id: agent-default-model\n  config:\n    provider: nosana\n"
            f"    model: {q(model)}\n")


def execute(source, url, model, dsh, attempts, timeout, on_event=lambda _: None):
    started = time.monotonic()
    deadline = started + timeout
    result = {"status": "failed", "attempts": 0, "test_code": "", "logs": [], "message": ""}
    def log(text):
        text = clipped(text)
        result["logs"].append(text)
        on_event({"type": "log", "message": text})
    with tempfile.TemporaryDirectory(prefix="dsh-task-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "solution.py").write_text(source, encoding="utf-8")
        patch = root / "nosana.patch.yml"
        patch.write_text(make_patch(url, model), encoding="utf-8")
        env = os.environ.copy()
        # Each job has a separate DSH home: no saved profile/model settings leak in.
        env["DSH_HOME"] = str(root / "dsh-home")
        test_path = workspace / "test_solution.py"
        feedback = ""
        try:
            for attempt in range(1, attempts + 1):
                result["attempts"] = attempt
                log(f"Attempt {attempt}/{attempts}: requesting tests from DSH")
                prompt = ("You are in an isolated Python workspace. Read solution.py, then create "
                          "or update test_solution.py with meaningful pytest tests for its public "
                          "behavior, including edge cases. Import the solution module. Do not modify "
                          "solution.py. Do not install packages or use the network. "
                          "When done, briefly explain what you tested.\n" + feedback)
                code, stdout, stderr = run_process([dsh, "--profile", "headless", "--patch", str(patch), "--json", prompt], workspace, env, deadline, stdout_json=True)
                final = dsh_final(stdout)
                if isinstance(final.get("text"), str) and final["text"]:
                    log("DSH: " + final["text"])
                if stderr:
                    # DSH stderr may contain reasoning or secrets. Do not forward it to callers.
                    log("DSH reported diagnostics on stderr (not included in logs).")
                if code != 0:
                    error_code = dsh_error(final)
                    result["error_code"] = error_code or "DSH_ERROR"
                    result["message"] = f"DSH exited with code {code} ({result['error_code']})."
                    break
                if not isinstance(final.get("reason"), dict) or final["reason"].get("kind") != "completed":
                    result["message"] = "DSH did not return a completed final event."
                    break
                if (workspace / "solution.py").is_symlink() or (workspace / "solution.py").read_text(encoding="utf-8") != source:
                    result["message"] = "DSH changed the source file; refusing to judge the result."
                    break
                if not test_path.is_file() or test_path.is_symlink():
                    feedback = "Previous attempt did not create a regular test_solution.py file. Create it."
                    log(feedback)
                    continue
                if test_path.stat().st_size > MAX_TEST:
                    result["message"] = "Generated test file exceeds size limit."
                    break
                result["test_code"] = test_path.read_text(encoding="utf-8")
                # Do not pass the model credential to the independently run tests.
                test_env = env.copy()
                test_env.pop("NOSANA_API_KEY", None)
                report = root / "pytest-result.json"
                report.unlink(missing_ok=True)
                (root / "orch_report_plugin.py").write_text(REPORT_PLUGIN, encoding="utf-8")
                test_env["ORCH_PYTEST_REPORT"] = str(report)
                test_env["PYTHONPATH"] = str(root)
                code, stdout, stderr = run_process([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "orch_report_plugin", "test_solution.py"], workspace, test_env, deadline)
                test_output = clipped(stdout + ("\n" + stderr if stderr else ""))
                log(f"pytest exited {code}:\n{test_output}")
                if (workspace / "solution.py").is_symlink() or (workspace / "solution.py").read_text(encoding="utf-8") != source:
                    result["message"] = "Test execution changed the source file; refusing to judge the result."
                    break
                if code == 0:
                    try:
                        passed = passed_count(report)
                    except (OSError, ValueError):
                        result["message"] = "pytest result report is missing or invalid."
                        break
                    if passed > 0:
                        result.update(status="succeeded", message="pytest passed; review the generated assertions.")
                        break
                    test_output += "\nAll collected tests were skipped; no test passed."
                    log("No test passed; requesting a revision.")
                feedback = ("The previous pytest run did not pass. Update test_solution.py based on "
                            f"this exit code and log, then leave the updated test file: exit={code}\n{test_output}")
            else:
                result["message"] = "Attempt limit reached without passing tests."
        except TimeoutError:
            result.update(status="timed_out", message="Overall time limit reached.")
        except (OSError, UnicodeError) as exc:
            result["message"] = f"Execution error: {type(exc).__name__}: {exc}"
    result["duration_seconds"] = round(time.monotonic() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to one Python source file")
    parser.add_argument("--attempts", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--timeout", type=int, default=180, choices=range(1, 1801), metavar="SECONDS")
    parser.add_argument("--dsh", default="dsh", help="Path to installed dsh executable")
    args = parser.parse_args()
    try:
        source_path = Path(args.source)
        if source_path.stat().st_size > MAX_SOURCE:
            raise ValueError("source file exceeds size limit")
        source = source_path.read_text(encoding="utf-8")
        if not source.strip():
            raise ValueError("source file is empty")
        url = os.environ["NOSANA_BASE_URL"]
        model = os.environ["NOSANA_MODEL"]
        if not url.startswith(("https://", "http://")) or not model:
            raise ValueError("invalid NOSANA_BASE_URL or NOSANA_MODEL")
        if not os.environ.get("NOSANA_API_KEY"):
            raise ValueError("NOSANA_API_KEY is required")
        result = execute(source, url, model, args.dsh, args.attempts, args.timeout)
    except (OSError, UnicodeError, KeyError, ValueError) as exc:
        result = {"status": "failed", "attempts": 0, "test_code": "", "logs": [], "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
